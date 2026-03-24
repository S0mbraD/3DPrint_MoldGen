"""Phase 4 测试 — ToolRegistry, BaseAgent, ExecutionEngine, 6大Agent"""

import pytest

from moldgen.ai.agent_base import AgentContext, AgentRole
from moldgen.ai.agents import (
    CreativeAgent,
    InsertAgent,
    MasterAgent,
    ModelAgent,
    MoldDesignAgent,
    SimOptAgent,
)
from moldgen.ai.execution_engine import (
    PIPELINE_TEMPLATES,
    AgentExecutionEngine,
    ExecutionPlan,
    PlanStep,
)
from moldgen.ai.tool_registry import ToolDef, ToolParam, ToolRegistry

# ── ToolRegistry ─────────────────────────────────────────────────────

class TestToolRegistry:
    def test_singleton(self):
        r1 = ToolRegistry()
        r2 = ToolRegistry()
        assert r1 is r2

    def test_builtin_tools_registered(self):
        registry = ToolRegistry()
        tools = registry.list_tools()
        assert len(tools) > 10
        names = [t.name for t in tools]
        assert "model_load" in names
        assert "mold_analyze_orientation" in names
        assert "sim_run" in names

    def test_categories(self):
        registry = ToolRegistry()
        cats = registry.list_categories()
        assert "model" in cats
        assert "mold" in cats
        assert "sim" in cats
        assert "export" in cats

    def test_get_tool(self):
        registry = ToolRegistry()
        tool = registry.get("model_repair")
        assert tool is not None
        assert tool.category == "model"

    def test_openai_schema(self):
        registry = ToolRegistry()
        tool = registry.get("model_simplify")
        assert tool is not None
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "model_simplify"
        assert "parameters" in schema["function"]

    def test_list_by_category(self):
        registry = ToolRegistry()
        model_tools = registry.list_tools("model")
        assert len(model_tools) >= 5
        for t in model_tools:
            assert t.category == "model"

    def test_custom_tool_registration(self):
        registry = ToolRegistry()
        custom = ToolDef(
            name="test_custom_tool",
            description="A test tool",
            category="test",
            parameters=[ToolParam("x", "number", "test param")],
            handler=lambda x: x * 2,
        )
        registry.register(custom)
        assert registry.get("test_custom_tool") is not None

    @pytest.mark.asyncio
    async def test_execute_with_handler(self):
        registry = ToolRegistry()
        tool = ToolDef(
            name="test_sync_handler",
            description="test",
            category="test",
            handler=lambda: {"result": 42},
        )
        registry.register(tool)
        result = await registry.execute("test_sync_handler")
        assert result.success
        assert result.data["result"] == 42

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("nonexistent_tool")
        assert not result.success
        assert "Unknown" in result.error


# ── BaseAgent & Agents ───────────────────────────────────────────────

class TestAgents:
    def test_model_agent_properties(self):
        agent = ModelAgent()
        assert agent.role == AgentRole.MODEL
        assert agent.name == "ModelAgent"
        assert len(agent.get_available_tools()) >= 5
        assert "model_repair" in agent.get_available_tools()

    def test_mold_agent_properties(self):
        agent = MoldDesignAgent()
        assert agent.role == AgentRole.MOLD
        assert len(agent.get_available_tools()) >= 4

    def test_simopt_agent_properties(self):
        agent = SimOptAgent()
        assert agent.role == AgentRole.SIM
        assert "sim_run" in agent.get_available_tools()

    def test_creative_agent_properties(self):
        agent = CreativeAgent()
        assert agent.role == AgentRole.CREATIVE

    def test_insert_agent_properties(self):
        agent = InsertAgent()
        assert agent.role == AgentRole.INSERT

    def test_tool_schemas(self):
        agent = ModelAgent()
        schemas = agent.get_tool_schemas()
        assert len(schemas) > 0
        assert all(s["type"] == "function" for s in schemas)

    @pytest.mark.asyncio
    async def test_model_agent_execute_no_model(self):
        agent = ModelAgent()
        ctx = AgentContext()
        result = await agent.execute("检查模型", ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_mold_agent_execute_no_model(self):
        agent = MoldDesignAgent()
        ctx = AgentContext()
        result = await agent.execute("分析方向", ctx)
        assert not result.success
        assert "No model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_simopt_agent_no_context(self):
        agent = SimOptAgent()
        ctx = AgentContext()
        result = await agent.execute("运行仿真", ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_creative_agent_execute(self):
        agent = CreativeAgent()
        ctx = AgentContext()
        result = await agent.execute("生成心脏模型", ctx)
        assert result.success
        assert "optimized_prompt" in result.output

    @pytest.mark.asyncio
    async def test_creative_prompt_optimization(self):
        agent = CreativeAgent()
        prompt = agent._optimize_prompt("生成一个肝脏模型")
        assert "liver" in prompt.lower()

    @pytest.mark.asyncio
    async def test_insert_agent_no_model(self):
        agent = InsertAgent()
        ctx = AgentContext()
        result = await agent.execute("生成支撑板", ctx)
        assert not result.success
        assert "模型" in (result.error or "")


# ── MasterAgent ──────────────────────────────────────────────────────

class TestMasterAgent:
    def test_intent_classification(self):
        engine = AgentExecutionEngine()
        master = MasterAgent(engine=engine)

        result = master.classify_intent("修复模型")
        assert result["target_agent"] == "model"

        result = master.classify_intent("分析脱模方向")
        assert result["target_agent"] == "mold"

        result = master.classify_intent("运行仿真")
        assert result["target_agent"] == "sim"

    def test_pipeline_matching(self):
        engine = AgentExecutionEngine()
        master = MasterAgent(engine=engine)

        result = master.classify_intent("全自动模具设计")
        assert result["pipeline"] == "full_from_model"

        result = master.classify_intent("从头开始做一个模型")
        assert result["pipeline"] == "full_from_text"

    @pytest.mark.asyncio
    async def test_master_routing_fallback(self):
        engine = AgentExecutionEngine()
        master = MasterAgent(engine=engine)
        ctx = AgentContext()
        result = await master.execute("你好", ctx)
        assert result.success
        assert "available_agents" in result.output


# ── ExecutionEngine ──────────────────────────────────────────────────

class TestExecutionEngine:
    def test_register_agents(self):
        engine = AgentExecutionEngine()
        engine.register_agent(ModelAgent())
        engine.register_agent(MoldDesignAgent())
        agents = engine.list_agents()
        assert len(agents) == 2

    def test_create_plan(self):
        engine = AgentExecutionEngine()
        plan = engine.create_plan("full_from_model")
        assert plan is not None
        assert len(plan.steps) >= 3
        d = plan.to_dict()
        assert d["n_steps"] >= 3

    def test_create_plan_unknown(self):
        engine = AgentExecutionEngine()
        assert engine.create_plan("nonexistent") is None

    def test_pipeline_templates(self):
        assert "full_from_model" in PIPELINE_TEMPLATES
        assert "mold_only" in PIPELINE_TEMPLATES
        assert "sim_only" in PIPELINE_TEMPLATES

    def test_list_pipelines(self):
        engine = AgentExecutionEngine()
        pipelines = engine.get_pipeline_templates()
        assert len(pipelines) >= 4

    @pytest.mark.asyncio
    async def test_execute_single_no_agent(self):
        engine = AgentExecutionEngine()
        result = await engine.execute_single(AgentRole.MODEL, "test", AgentContext())
        assert not result.success
        assert "not registered" in result.error

    @pytest.mark.asyncio
    async def test_execute_single_with_agent(self):
        engine = AgentExecutionEngine()
        engine.register_agent(CreativeAgent())
        result = await engine.execute_single(
            AgentRole.CREATIVE, "生成心脏模型", AgentContext(),
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_plan_with_agents(self):
        engine = AgentExecutionEngine()
        engine.register_agent(MoldDesignAgent())
        engine.register_agent(SimOptAgent())

        plan = ExecutionPlan(
            name="test_plan",
            steps=[
                PlanStep(AgentRole.MOLD, "分析方向"),
            ],
        )
        ctx = AgentContext(model_id=None)
        result = await engine.execute_plan(plan, ctx)
        assert result.steps_total == 1
        assert result.elapsed_seconds >= 0

    def test_custom_plan(self):
        engine = AgentExecutionEngine()
        plan = engine.create_custom_plan("my_plan", [
            {"agent": "model", "task": "load model"},
            {"agent": "mold", "task": "build mold", "depends_on": [0]},
        ])
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == [0]
