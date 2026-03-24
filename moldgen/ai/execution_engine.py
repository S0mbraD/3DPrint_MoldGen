"""Agent 自动执行引擎 — 调度 Agent 完成复杂多步任务"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from moldgen.ai.agent_base import (
    AgentContext,
    AgentRole,
    BaseAgent,
    StepResult,
)

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    agent: AgentRole
    task: str
    depends_on: list[int] = field(default_factory=list)
    status: str = "pending"  # pending | running | done | failed | skipped
    result: StepResult | None = None

    def to_dict(self) -> dict:
        return {
            "agent": self.agent.value,
            "task": self.task,
            "depends_on": self.depends_on,
            "status": self.status,
            "result": self.result.to_dict() if self.result else None,
        }


@dataclass
class ExecutionPlan:
    name: str
    steps: list[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "n_steps": len(self.steps),
            "completed": sum(1 for s in self.steps if s.status == "done"),
            "failed": sum(1 for s in self.steps if s.status == "failed"),
        }


@dataclass
class ExecutionResult:
    plan_name: str
    success: bool
    steps_completed: int = 0
    steps_total: int = 0
    steps: list[dict] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "plan_name": self.plan_name,
            "success": self.success,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "steps": self.steps,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "error": self.error,
        }


# ── Pre-defined Pipeline Templates ──────────────────────────────────

PIPELINE_TEMPLATES: dict[str, list[PlanStep]] = {
    "full_from_model": [
        PlanStep(AgentRole.MODEL, "加载并检查模型质量，必要时修复"),
        PlanStep(AgentRole.MOLD, "分析最优脱模方向", depends_on=[0]),
        PlanStep(AgentRole.MOLD, "生成分型面和模具壳体", depends_on=[1]),
        PlanStep(AgentRole.SIM, "设计浇注系统", depends_on=[2]),
        PlanStep(AgentRole.SIM, "运行灌注仿真并优化", depends_on=[3]),
    ],
    "mold_only": [
        PlanStep(AgentRole.MOLD, "分析最优脱模方向"),
        PlanStep(AgentRole.MOLD, "生成分型面和模具壳体", depends_on=[0]),
    ],
    "sim_only": [
        PlanStep(AgentRole.SIM, "设计浇注系统"),
        PlanStep(AgentRole.SIM, "运行灌注仿真", depends_on=[0]),
        PlanStep(AgentRole.SIM, "自动优化", depends_on=[1]),
    ],
    "full_from_text": [
        PlanStep(AgentRole.CREATIVE, "根据描述生成3D模型"),
        PlanStep(AgentRole.MODEL, "模型质量检查与修复", depends_on=[0]),
        PlanStep(AgentRole.MOLD, "全自动模具设计", depends_on=[1]),
        PlanStep(AgentRole.SIM, "浇注仿真与优化", depends_on=[2]),
    ],
}


class AgentExecutionEngine:
    """Agent 执行引擎 — 管理多 Agent 协作"""

    def __init__(self) -> None:
        self._agents: dict[AgentRole, BaseAgent] = {}
        self._current_plan: ExecutionPlan | None = None

    def register_agent(self, agent: BaseAgent) -> None:
        self._agents[agent.role] = agent
        logger.info("Registered agent: %s (%s)", agent.name, agent.role.value)

    def get_agent(self, role: AgentRole) -> BaseAgent | None:
        return self._agents.get(role)

    def list_agents(self) -> list[dict]:
        return [
            {
                "role": agent.role.value,
                "name": agent.name,
                "description": agent.description,
                "tools": agent.get_available_tools(),
            }
            for agent in self._agents.values()
        ]

    def create_plan(self, template_name: str) -> ExecutionPlan | None:
        template = PIPELINE_TEMPLATES.get(template_name)
        if not template:
            return None
        steps = [
            PlanStep(
                agent=s.agent,
                task=s.task,
                depends_on=list(s.depends_on),
            )
            for s in template
        ]
        return ExecutionPlan(name=template_name, steps=steps)

    def create_custom_plan(self, name: str, steps: list[dict]) -> ExecutionPlan:
        plan_steps = []
        for s in steps:
            role = AgentRole(s["agent"])
            plan_steps.append(PlanStep(
                agent=role,
                task=s["task"],
                depends_on=s.get("depends_on", []),
            ))
        return ExecutionPlan(name=name, steps=plan_steps)

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: AgentContext,
        on_step_start: Any | None = None,
        on_step_complete: Any | None = None,
    ) -> ExecutionResult:
        start_time = time.time()
        self._current_plan = plan
        logger.info("Executing plan: %s (%d steps)", plan.name, len(plan.steps))

        result = ExecutionResult(
            plan_name=plan.name,
            success=True,
            steps_total=len(plan.steps),
        )

        for i, step in enumerate(plan.steps):
            # Check dependencies
            for dep_idx in step.depends_on:
                if dep_idx < len(plan.steps) and plan.steps[dep_idx].status == "failed":
                    step.status = "skipped"
                    result.steps.append(step.to_dict())
                    continue

            agent = self._agents.get(step.agent)
            if not agent:
                step.status = "failed"
                step.result = StepResult(
                    step_name=step.task, success=False,
                    error=f"Agent {step.agent.value} not registered",
                )
                result.success = False
                result.steps.append(step.to_dict())
                continue

            step.status = "running"
            if on_step_start:
                await _maybe_await(on_step_start(i, step))

            try:
                step_result = await agent.execute(step.task, context)
                step.result = step_result
                step.status = "done" if step_result.success else "failed"

                if not step_result.success:
                    result.success = False
                else:
                    result.steps_completed += 1

            except Exception as e:
                logger.exception("Step %d failed: %s", i, step.task)
                step.status = "failed"
                step.result = StepResult(
                    step_name=step.task, success=False, error=str(e),
                )
                result.success = False

            result.steps.append(step.to_dict())
            if on_step_complete:
                await _maybe_await(on_step_complete(i, step))

        result.elapsed_seconds = time.time() - start_time
        self._current_plan = None

        logger.info(
            "Plan '%s' finished: %d/%d steps, success=%s, %.1fs",
            plan.name, result.steps_completed, result.steps_total,
            result.success, result.elapsed_seconds,
        )
        return result

    async def execute_single(
        self, role: AgentRole, task: str, context: AgentContext,
    ) -> StepResult:
        """Execute a single task with a specific agent."""
        agent = self._agents.get(role)
        if not agent:
            return StepResult(
                step_name=task, success=False,
                error=f"Agent {role.value} not registered",
            )
        return await agent.execute(task, context)

    @property
    def current_plan(self) -> ExecutionPlan | None:
        return self._current_plan

    def get_pipeline_templates(self) -> dict[str, list[dict]]:
        return {
            name: [{"agent": s.agent.value, "task": s.task} for s in steps]
            for name, steps in PIPELINE_TEMPLATES.items()
        }


async def _maybe_await(val: Any) -> None:
    import inspect
    if inspect.isawaitable(val):
        await val
