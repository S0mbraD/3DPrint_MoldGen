"""Agent 执行引擎接口 — 6大内置Agent + 配置管理 + 记忆 + 执行历史"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from moldgen.ai.agent_base import AgentConfig, AgentContext, AgentRole, ExecutionMode
from moldgen.ai.agents import (
    CreativeAgent,
    InsertAgent,
    MasterAgent,
    ModelAgent,
    MoldDesignAgent,
    SimOptAgent,
)
from moldgen.ai.execution_engine import AgentExecutionEngine
from moldgen.ai.memory import AgentMemoryManager
from moldgen.ai.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Initialize Engine & Agents ────────────────────────────────────────

_engine = AgentExecutionEngine()
_master = MasterAgent(engine=_engine)
_engine.register_agent(_master)
_engine.register_agent(ModelAgent())
_engine.register_agent(MoldDesignAgent())
_engine.register_agent(InsertAgent())
_engine.register_agent(SimOptAgent())
_engine.register_agent(CreativeAgent())
_memory = AgentMemoryManager()


# ── API Models ────────────────────────────────────────────────────────

class AgentExecuteRequest(BaseModel):
    request: str
    mode: str = "auto"  # auto | semi_auto | step
    model_id: str | None = None
    mold_id: str | None = None
    gating_id: str | None = None
    material: str = "silicone_a30"


class PlanExecuteRequest(BaseModel):
    template: str
    model_id: str | None = None
    mold_id: str | None = None
    gating_id: str | None = None
    material: str = "silicone_a30"


class SingleAgentRequest(BaseModel):
    agent: str  # master | model | mold | insert | sim | creative
    task: str
    model_id: str | None = None
    mold_id: str | None = None
    gating_id: str | None = None
    material: str = "silicone_a30"


class GlobalConfigUpdate(BaseModel):
    default_mode: str | None = None
    thinking_style: str | None = None
    enable_memory: bool | None = None
    enable_self_reflection: bool | None = None
    max_retries: int | None = None
    auto_confirm_threshold: float | None = None


class AgentConfigUpdate(BaseModel):
    enabled: bool | None = None
    thinking_style: str | None = None
    max_retries: int | None = None
    retry_delay: float | None = None
    auto_confirm_threshold: float | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    enable_memory: bool | None = None
    enable_self_reflection: bool | None = None
    verbose_logging: bool | None = None


class UserDefaultUpdate(BaseModel):
    key: str
    value: str | float | int | bool


# ── Execution Endpoints ───────────────────────────────────────────────

@router.post("/execute")
async def execute_agent_task(req: AgentExecuteRequest):
    """通过 MasterAgent 智能路由执行任务"""
    context = AgentContext(
        model_id=req.model_id,
        mold_id=req.mold_id,
        gating_id=req.gating_id,
        material=req.material,
        mode=ExecutionMode(req.mode) if req.mode in ("auto", "semi_auto", "step") else ExecutionMode.AUTO,
    )

    try:
        result = await _master.execute(req.request, context)
    except Exception as e:
        logger.exception("Agent execution failed")
        raise HTTPException(500, f"Agent execution error: {e}") from e

    return {
        "success": result.success,
        "step_name": result.step_name,
        "output": result.output,
        "tool_calls": result.tool_calls,
        "thinking": result.thinking,
        "events": [ev.to_dict() for ev in result.events[-20:]],
        "elapsed_seconds": result.elapsed_seconds,
        "context": context.to_dict(),
    }


@router.post("/execute/plan")
async def execute_plan(req: PlanExecuteRequest):
    """执行预定义流水线"""
    plan = _engine.create_plan(req.template)
    if not plan:
        available = list(_engine.get_pipeline_templates().keys())
        raise HTTPException(400, f"Unknown template: {req.template}. Available: {available}")

    context = AgentContext(
        model_id=req.model_id,
        mold_id=req.mold_id,
        gating_id=req.gating_id,
        material=req.material,
    )

    try:
        result = await _engine.execute_plan(plan, context)
    except Exception as e:
        logger.exception("Plan execution failed")
        raise HTTPException(500, f"Plan execution error: {e}") from e

    return {"result": result.to_dict(), "context": context.to_dict()}


@router.post("/execute/single")
async def execute_single_agent(req: SingleAgentRequest):
    """直接调用单个Agent执行任务"""
    role_map = {
        "master": AgentRole.MASTER, "model": AgentRole.MODEL,
        "mold": AgentRole.MOLD, "insert": AgentRole.INSERT,
        "sim": AgentRole.SIM, "creative": AgentRole.CREATIVE,
    }
    role = role_map.get(req.agent)
    if not role:
        raise HTTPException(400, f"Unknown agent: {req.agent}")

    context = AgentContext(
        model_id=req.model_id,
        mold_id=req.mold_id,
        gating_id=req.gating_id,
        material=req.material,
    )

    try:
        result = await _engine.execute_single(role, req.task, context)
    except Exception as e:
        logger.exception("Single agent execution failed")
        raise HTTPException(500, str(e)) from e

    return {
        "agent": req.agent,
        "success": result.success,
        "step_name": result.step_name,
        "output": result.output,
        "tool_calls": result.tool_calls,
        "thinking": result.thinking,
        "elapsed_seconds": result.elapsed_seconds,
    }


@router.get("/classify")
async def classify_intent(task: str):
    """分析用户意图（不执行）"""
    return _master.classify_intent(task)


# ── Agent & Tool Listing ──────────────────────────────────────────────

@router.get("/agents")
async def list_agents():
    """列出所有内置Agent（含配置信息）"""
    return {"agents": _engine.list_agents()}


@router.get("/pipelines")
async def list_pipelines():
    """列出所有预定义流水线"""
    return {"pipelines": _engine.get_pipeline_templates()}


@router.get("/tools")
async def list_tools(category: str | None = None):
    """列出所有注册工具"""
    registry = ToolRegistry()
    tools = registry.list_tools(category)
    return {
        "categories": registry.list_categories(),
        "tools": [
            {"name": t.name, "description": t.description,
             "category": t.category, "requires_confirmation": t.requires_confirmation}
            for t in tools
        ],
        "total": len(tools),
    }


# ── Configuration Endpoints ───────────────────────────────────────────

@router.get("/config")
async def get_global_config():
    """获取 Agent 系统全局配置"""
    return {"config": _engine.get_global_config()}


@router.put("/config")
async def update_global_config(req: GlobalConfigUpdate):
    """更新 Agent 系统全局配置"""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    config = _engine.update_global_config(updates)
    return {"config": config}


@router.get("/config/{agent_role}")
async def get_agent_config(agent_role: str):
    """获取单个 Agent 的配置"""
    role_map = {
        "master": AgentRole.MASTER, "model": AgentRole.MODEL,
        "mold": AgentRole.MOLD, "insert": AgentRole.INSERT,
        "sim": AgentRole.SIM, "creative": AgentRole.CREATIVE,
    }
    role = role_map.get(agent_role)
    if not role:
        raise HTTPException(400, f"Unknown agent: {agent_role}")
    cfg = _engine.get_agent_config(role)
    if not cfg:
        raise HTTPException(404, f"Agent {agent_role} not registered")
    return {"agent": agent_role, "config": cfg.to_dict()}


@router.put("/config/{agent_role}")
async def update_agent_config(agent_role: str, req: AgentConfigUpdate):
    """更新单个 Agent 的配置"""
    role_map = {
        "master": AgentRole.MASTER, "model": AgentRole.MODEL,
        "mold": AgentRole.MOLD, "insert": AgentRole.INSERT,
        "sim": AgentRole.SIM, "creative": AgentRole.CREATIVE,
    }
    role = role_map.get(agent_role)
    if not role:
        raise HTTPException(400, f"Unknown agent: {agent_role}")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    cfg = _engine.update_agent_config(role, updates)
    if not cfg:
        raise HTTPException(404, f"Agent {agent_role} not registered")
    return {"agent": agent_role, "config": cfg.to_dict()}


# ── Memory Endpoints ──────────────────────────────────────────────────

@router.get("/memory")
async def get_memory_status():
    """获取 Agent 记忆系统状态"""
    return _memory.to_dict()


@router.post("/memory/defaults")
async def set_user_default(req: UserDefaultUpdate):
    """设置用户默认参数"""
    _memory.long_term.set_default(req.key, req.value)
    return {"key": req.key, "value": req.value, "saved": True}


@router.get("/memory/defaults")
async def get_user_defaults():
    """获取所有用户默认参数"""
    return {"defaults": _memory.long_term.get_all_defaults()}


@router.delete("/memory/short-term")
async def clear_short_term_memory():
    """清空短期记忆"""
    _memory.short_term.clear()
    return {"cleared": True}


@router.get("/memory/usage-stats")
async def get_usage_stats():
    """获取 Agent 使用统计"""
    return {"stats": _memory.long_term.get_usage_stats()}


# ── Execution History ─────────────────────────────────────────────────

@router.get("/history")
async def get_execution_history():
    """获取执行历史"""
    return {"history": _master.get_execution_history()}
