"""MasterAgent — 总控调度，意图路由 + 任务编排"""

from __future__ import annotations

from moldgen.ai.agent_base import AgentContext, AgentRole, BaseAgent, StepResult
from moldgen.ai.execution_engine import PIPELINE_TEMPLATES, AgentExecutionEngine

KEYWORD_ROUTES: dict[str, AgentRole] = {
    "导入": AgentRole.MODEL, "加载": AgentRole.MODEL, "上传": AgentRole.MODEL,
    "修复": AgentRole.MODEL, "简化": AgentRole.MODEL, "细化": AgentRole.MODEL,
    "编辑": AgentRole.MODEL, "变换": AgentRole.MODEL, "布尔": AgentRole.MODEL,
    "脱模": AgentRole.MOLD, "方向": AgentRole.MOLD, "分型": AgentRole.MOLD,
    "模具": AgentRole.MOLD, "壳体": AgentRole.MOLD,
    "插板": AgentRole.INSERT, "支撑": AgentRole.INSERT, "锚固": AgentRole.INSERT,
    "仿真": AgentRole.SIM, "灌注": AgentRole.SIM, "优化": AgentRole.SIM,
    "浇注": AgentRole.SIM, "材料": AgentRole.SIM,
    "生成": AgentRole.CREATIVE, "创建": AgentRole.CREATIVE, "设计": AgentRole.CREATIVE,
    "图像": AgentRole.CREATIVE, "图片": AgentRole.CREATIVE,
}

PIPELINE_KEYWORDS: dict[str, str] = {
    "全自动": "full_from_model",
    "从头开始": "full_from_text",
    "一键": "full_from_model",
    "完整流程": "full_from_model",
    "只做模具": "mold_only",
    "只仿真": "sim_only",
}


class MasterAgent(BaseAgent):
    def __init__(self, engine: AgentExecutionEngine | None = None):
        super().__init__(AgentRole.MASTER)
        self.engine = engine

    @property
    def name(self) -> str:
        return "MasterAgent"

    @property
    def description(self) -> str:
        return "总控调度Agent — 意图识别、任务规划、Agent路由"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 MoldGen 的总控 Agent。你的职责是理解用户意图，"
            "将任务分解并分配给专业 Agent 执行。可用Agent: "
            "ModelAgent(模型处理), MoldDesignAgent(模具设计), "
            "InsertAgent(支撑板), SimOptAgent(仿真优化), "
            "CreativeAgent(创意生成)。"
        )

    def get_available_tools(self) -> list[str]:
        return []

    async def execute(self, task: str, context: AgentContext) -> StepResult:
        self.logger.info("MasterAgent routing: %s", task[:80])

        # 1. Check for pipeline keywords
        pipeline = self._match_pipeline(task)
        if pipeline and self.engine:
            plan = self.engine.create_plan(pipeline)
            if plan:
                result = await self.engine.execute_plan(plan, context)
                return StepResult(
                    step_name=f"Pipeline: {pipeline}",
                    success=result.success,
                    output=result.to_dict(),
                )

        # 2. Keyword routing
        target = self._route_by_keyword(task)
        if target and self.engine:
            agent = self.engine.get_agent(target)
            if agent:
                return await agent.execute(task, context)

        # 3. Fallback: describe capabilities
        return StepResult(
            step_name="route",
            success=True,
            output={
                "message": "已理解您的需求，请告诉我更具体的操作。",
                "available_agents": [r.value for r in AgentRole if r != AgentRole.MASTER],
                "available_pipelines": list(PIPELINE_TEMPLATES.keys()),
            },
        )

    def _match_pipeline(self, task: str) -> str | None:
        for keyword, pipeline in PIPELINE_KEYWORDS.items():
            if keyword in task:
                return pipeline
        return None

    def _route_by_keyword(self, task: str) -> AgentRole | None:
        for keyword, role in KEYWORD_ROUTES.items():
            if keyword in task:
                return role
        return None

    def classify_intent(self, task: str) -> dict:
        """Classify user intent without executing (for UI preview)."""
        pipeline = self._match_pipeline(task)
        target = self._route_by_keyword(task)
        return {
            "task": task,
            "pipeline": pipeline,
            "target_agent": target.value if target else None,
            "confidence": 0.9 if (pipeline or target) else 0.3,
        }
