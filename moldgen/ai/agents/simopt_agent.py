"""SimOptAgent — 灌注仿真 + 自动优化"""

from __future__ import annotations

from moldgen.ai.agent_base import AgentContext, AgentRole, BaseAgent, StepResult


class SimOptAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentRole.SIM)

    @property
    def name(self) -> str:
        return "SimOptAgent"

    @property
    def description(self) -> str:
        return "仿真优化Agent — 灌注仿真/缺陷检测/自动优化"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 MoldGen 的仿真优化 Agent。你负责设计浇注系统、"
            "运行灌注仿真、检测缺陷并自动优化参数。"
            "小模型用L1启发式，大模型用L2达西流。"
        )

    def get_available_tools(self) -> list[str]:
        return [
            "sim_design_gating", "sim_run", "sim_optimize", "sim_list_materials",
        ]

    async def execute(self, task: str, context: AgentContext) -> StepResult:
        self.logger.info("SimOptAgent executing: %s", task[:80])

        if "浇注" in task or "浇口" in task:
            return await self._design_gating(context)

        if "仿真" in task or "模拟" in task:
            return await self._run_simulation(context)

        if "优化" in task:
            return await self._run_optimization(context)

        # Default: full sim pipeline
        return await self._full_pipeline(context)

    async def _design_gating(self, ctx: AgentContext) -> StepResult:
        if not ctx.model_id or not ctx.mold_id:
            return StepResult(step_name="gating", success=False, error="Need model and mold first")
        r = await self.call_tool(
            "sim_design_gating", model_id=ctx.model_id,
            mold_id=ctx.mold_id, material=ctx.material,
        )
        if r.success and isinstance(r.data, dict):
            ctx.gating_id = r.data.get("gating_id")
        return StepResult(step_name="gating", success=r.success,
                         tool_calls=[{"tool": "sim_design_gating", "result": r.to_dict()}],
                         output=r.data)

    async def _run_simulation(self, ctx: AgentContext) -> StepResult:
        if not ctx.model_id or not ctx.gating_id:
            return StepResult(step_name="simulate", success=False, error="Need model and gating first")
        r = await self.call_tool(
            "sim_run", model_id=ctx.model_id,
            gating_id=ctx.gating_id, material=ctx.material, level=1,
        )
        if r.success and isinstance(r.data, dict):
            ctx.sim_id = r.data.get("sim_id")
        return StepResult(step_name="simulate", success=r.success,
                         tool_calls=[{"tool": "sim_run", "result": r.to_dict()}],
                         output=r.data)

    async def _run_optimization(self, ctx: AgentContext) -> StepResult:
        if not ctx.model_id or not ctx.mold_id or not ctx.gating_id:
            return StepResult(step_name="optimize", success=False, error="Need model, mold and gating")
        r = await self.call_tool(
            "sim_optimize", model_id=ctx.model_id, mold_id=ctx.mold_id,
            gating_id=ctx.gating_id, material=ctx.material,
        )
        return StepResult(step_name="optimize", success=r.success,
                         tool_calls=[{"tool": "sim_optimize", "result": r.to_dict()}],
                         output=r.data)

    async def _full_pipeline(self, ctx: AgentContext) -> StepResult:
        tool_calls = []

        gating = await self._design_gating(ctx)
        tool_calls.extend(gating.tool_calls)
        if not gating.success:
            return StepResult(step_name="sim_pipeline", success=False,
                             tool_calls=tool_calls, error=gating.error)

        sim = await self._run_simulation(ctx)
        tool_calls.extend(sim.tool_calls)

        opt = await self._run_optimization(ctx)
        tool_calls.extend(opt.tool_calls)

        success = gating.success and sim.success
        return StepResult(
            step_name="sim_pipeline", success=success, tool_calls=tool_calls,
            output={"message": "仿真优化流程完成" if success else "部分步骤失败"},
        )
