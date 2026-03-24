"""MoldDesignAgent — 脱模分析、分型面、模具壳体"""

from __future__ import annotations

from moldgen.ai.agent_base import AgentContext, AgentRole, BaseAgent, StepResult


class MoldDesignAgent(BaseAgent):
    AUTO_PIPELINE = [
        ("mold_analyze_orientation", "分析脱模方向"),
        ("mold_generate_parting", "生成分型面"),
        ("mold_build_two_part", "构建双片壳模具"),
    ]

    def __init__(self):
        super().__init__(AgentRole.MOLD)

    @property
    def name(self) -> str:
        return "MoldDesignAgent"

    @property
    def description(self) -> str:
        return "模具设计Agent — 脱模方向/分型面/壳体构建/浇注系统"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 MoldGen 的模具设计 Agent。你负责分析最优脱模方向、"
            "生成分型面、构建模具壳体。当方向评分<0.7时需用户确认，"
            "复杂模型可能需要多片壳模具。"
        )

    def get_available_tools(self) -> list[str]:
        return [
            "mold_analyze_orientation", "mold_evaluate_direction",
            "mold_generate_parting", "mold_build_two_part", "mold_build_multi_part",
        ]

    async def execute(self, task: str, context: AgentContext) -> StepResult:
        self.logger.info("MoldDesignAgent executing: %s", task[:80])

        if "全自动" in task or "自动" in task or "模具壳体" in task or "全流程" in task:
            return await self._run_auto_pipeline(context)

        if "方向" in task or "脱模" in task:
            return await self._analyze_orientation(context)

        if "分型" in task:
            return await self._generate_parting(context)

        if "壳体" in task or "模具" in task:
            return await self._build_mold(context)

        return await self._run_auto_pipeline(context)

    async def _run_auto_pipeline(self, context: AgentContext) -> StepResult:
        tool_calls = []
        if not context.model_id:
            return StepResult(step_name="auto_mold", success=False, error="No model loaded")

        # Step 1: Orientation
        ori = await self.call_tool("mold_analyze_orientation", model_id=context.model_id)
        tool_calls.append({"tool": "mold_analyze_orientation", "result": ori.to_dict()})
        if not ori.success:
            return StepResult(step_name="auto_mold", success=False, tool_calls=tool_calls, error=ori.error)

        # Step 2: Parting
        part = await self.call_tool("mold_generate_parting", model_id=context.model_id)
        tool_calls.append({"tool": "mold_generate_parting", "result": part.to_dict()})

        # Step 3: Build
        build = await self.call_tool("mold_build_two_part", model_id=context.model_id)
        tool_calls.append({"tool": "mold_build_two_part", "result": build.to_dict()})

        success = all(tc["result"]["success"] for tc in tool_calls)
        return StepResult(
            step_name="auto_mold_pipeline", success=success, tool_calls=tool_calls,
            output={"message": "模具设计全流程完成" if success else "部分步骤失败"},
        )

    async def _analyze_orientation(self, ctx: AgentContext) -> StepResult:
        if not ctx.model_id:
            return StepResult(step_name="orientation", success=False, error="No model")
        r = await self.call_tool("mold_analyze_orientation", model_id=ctx.model_id)
        return StepResult(step_name="orientation", success=r.success,
                         tool_calls=[{"tool": "mold_analyze_orientation", "result": r.to_dict()}],
                         output=r.data)

    async def _generate_parting(self, ctx: AgentContext) -> StepResult:
        if not ctx.model_id:
            return StepResult(step_name="parting", success=False, error="No model")
        r = await self.call_tool("mold_generate_parting", model_id=ctx.model_id)
        return StepResult(step_name="parting", success=r.success,
                         tool_calls=[{"tool": "mold_generate_parting", "result": r.to_dict()}],
                         output=r.data)

    async def _build_mold(self, ctx: AgentContext) -> StepResult:
        if not ctx.model_id:
            return StepResult(step_name="build_mold", success=False, error="No model")
        r = await self.call_tool("mold_build_two_part", model_id=ctx.model_id)
        return StepResult(step_name="build_mold", success=r.success,
                         tool_calls=[{"tool": "mold_build_two_part", "result": r.to_dict()}],
                         output=r.data)
