"""Agent 自动执行引擎 — 调度 Agent 完成复杂多步任务，支持事件流和回滚"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from moldgen.ai.agent_base import (
    AgentConfig,
    AgentContext,
    AgentEvent,
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
    """Agent 执行引擎 — 管理多 Agent 协作，支持事件流、回滚和配置"""

    def __init__(self) -> None:
        self._agents: dict[AgentRole, BaseAgent] = {}
        self._current_plan: ExecutionPlan | None = None
        self._event_listeners: list[Callable[[AgentEvent], Any]] = []
        self._global_config: dict[str, Any] = {
            "default_mode": "semi_auto",
            "thinking_style": "balanced",
            "enable_memory": True,
            "enable_self_reflection": True,
            "max_retries": 2,
            "auto_confirm_threshold": 0.85,
        }

    def register_agent(self, agent: BaseAgent) -> None:
        self._agents[agent.role] = agent
        logger.info("Registered agent: %s (%s)", agent.name, agent.role.value)

    def get_agent(self, role: AgentRole) -> BaseAgent | None:
        return self._agents.get(role)

    def list_agents(self) -> list[dict]:
        return [agent.get_full_info() for agent in self._agents.values()]

    def add_event_listener(self, listener: Callable[[AgentEvent], Any]) -> None:
        self._event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[AgentEvent], Any]) -> None:
        self._event_listeners.discard(listener) if hasattr(self._event_listeners, 'discard') else None
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)

    async def _emit(self, event: AgentEvent) -> None:
        for listener in self._event_listeners:
            try:
                await _maybe_await(listener(event))
            except Exception:
                logger.debug("Event listener error", exc_info=True)

    # ── Configuration ──────────────────────────────────────────────────

    def get_global_config(self) -> dict[str, Any]:
        return dict(self._global_config)

    def update_global_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        for key, value in updates.items():
            if key in self._global_config:
                self._global_config[key] = value
        self._apply_config_to_agents()
        return self.get_global_config()

    def get_agent_config(self, role: AgentRole) -> AgentConfig | None:
        agent = self._agents.get(role)
        return agent.config if agent else None

    def update_agent_config(self, role: AgentRole, updates: dict) -> AgentConfig | None:
        agent = self._agents.get(role)
        if not agent:
            return None
        agent.config = AgentConfig.from_dict({**agent.config.to_dict(), **updates})
        return agent.config

    def _apply_config_to_agents(self) -> None:
        from moldgen.ai.agent_base import ExecutionMode, ThinkingStyle
        for agent in self._agents.values():
            if "thinking_style" in self._global_config:
                try:
                    agent.config.thinking_style = ThinkingStyle(self._global_config["thinking_style"])
                except ValueError:
                    pass
            if "enable_memory" in self._global_config:
                agent.config.enable_memory = bool(self._global_config["enable_memory"])
            if "enable_self_reflection" in self._global_config:
                agent.config.enable_self_reflection = bool(self._global_config["enable_self_reflection"])
            if "max_retries" in self._global_config:
                agent.config.max_retries = int(self._global_config["max_retries"])

    # ── Plan Management ────────────────────────────────────────────────

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

    # ── Execution ──────────────────────────────────────────────────────

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

        await self._emit(AgentEvent(
            event_type="plan_start", agent_role="engine",
            data={"plan": plan.name, "steps": len(plan.steps)},
        ))

        result = ExecutionResult(
            plan_name=plan.name,
            success=True,
            steps_total=len(plan.steps),
        )

        for i, step in enumerate(plan.steps):
            deps_failed = any(
                dep_idx < len(plan.steps) and plan.steps[dep_idx].status == "failed"
                for dep_idx in step.depends_on
            )
            if deps_failed:
                step.status = "skipped"
                result.steps.append(step.to_dict())
                await self._emit(AgentEvent(
                    event_type="step_skipped", agent_role=step.agent.value,
                    data={"step": i, "task": step.task, "reason": "dependency_failed"},
                ))
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

            if not agent.config.enabled:
                step.status = "skipped"
                result.steps.append(step.to_dict())
                continue

            step.status = "running"
            await self._emit(AgentEvent(
                event_type="step_start", agent_role=step.agent.value,
                data={"step": i, "task": step.task, "total": len(plan.steps)},
            ))
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

            await self._emit(AgentEvent(
                event_type="step_complete", agent_role=step.agent.value,
                data={"step": i, "task": step.task, "success": step.status == "done"},
            ))
            if on_step_complete:
                await _maybe_await(on_step_complete(i, step))

        result.elapsed_seconds = time.time() - start_time
        self._current_plan = None

        await self._emit(AgentEvent(
            event_type="plan_complete", agent_role="engine",
            data={"plan": plan.name, "success": result.success, "elapsed": result.elapsed_seconds},
        ))

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
        if not agent.config.enabled:
            return StepResult(
                step_name=task, success=False,
                error=f"Agent {role.value} is disabled",
            )

        await self._emit(AgentEvent(
            event_type="single_start", agent_role=role.value,
            data={"task": task[:80]},
        ))

        result = await agent.execute(task, context)

        await self._emit(AgentEvent(
            event_type="single_complete", agent_role=role.value,
            data={"task": task[:80], "success": result.success},
        ))

        return result

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
