"""Agent 执行引擎接口 — 6大内置Agent"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from moldgen.ai.agent_base import AgentContext, AgentRole, ExecutionMode
from moldgen.ai.agents import (
    CreativeAgent,
    InsertAgent,
    MasterAgent,
    ModelAgent,
    MoldDesignAgent,
    SimOptAgent,
)
from moldgen.ai.execution_engine import AgentExecutionEngine
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


# ── Endpoints ─────────────────────────────────────────────────────────

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
    }


@router.get("/classify")
async def classify_intent(task: str):
    """分析用户意图（不执行）"""
    return _master.classify_intent(task)


@router.get("/agents")
async def list_agents():
    """列出所有内置Agent"""
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
