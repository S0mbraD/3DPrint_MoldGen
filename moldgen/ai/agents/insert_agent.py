"""InsertAgent — 内嵌支撑板设计（AI辅助位置分析+自动生成+装配验证）"""

from __future__ import annotations

from moldgen.ai.agent_base import AgentContext, AgentRole, BaseAgent, StepResult


class InsertAgent(BaseAgent):
    ORGAN_STRATEGIES = {
        "肝": ("solid", "mesh_holes", "中央横断面板"),
        "肾": ("solid", "mesh_holes", "中央横断面板"),
        "脑": ("solid", "mesh_holes", "中央横断面板"),
        "胃": ("hollow", "grooves", "内壁支撑环"),
        "膀胱": ("hollow", "grooves", "内壁支撑环"),
        "血管": ("tubular", "bumps", "轴向骨架"),
        "肠": ("tubular", "bumps", "轴向骨架"),
        "皮肤": ("sheet", "diamond", "底板"),
        "肌肉": ("sheet", "diamond", "底板"),
    }

    def __init__(self):
        super().__init__(AgentRole.INSERT)

    @property
    def name(self) -> str:
        return "InsertAgent"

    @property
    def description(self) -> str:
        return "支撑板设计Agent — 位置分析/自动生成/锚固结构/装配验证"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 MoldGen 的支撑板设计专家。你结合解剖学知识和工程经验，"
            "为硅胶模具设计内嵌支撑板。核心能力：分析模型几何结构确定位置、"
            "根据器官类型选择锚固结构、确保可一体置入模具并被硅胶包裹、验证装配。"
            "器官策略：实质性器官→网孔锚固，空腔器官→沟槽锚固，"
            "管道结构→凸起锚固，组织片→菱形纹锚固。"
        )

    def get_available_tools(self) -> list[str]:
        return [
            "insert_analyze_positions",
            "insert_generate",
            "insert_add_anchor",
            "insert_validate",
            "insert_get_info",
        ]

    async def execute(self, task: str, context: AgentContext) -> StepResult:
        self.logger.info("InsertAgent executing: %s", task[:80])

        if not context.model_id:
            return StepResult(step_name=task, success=False, error="未加载模型")

        organ_type, anchor_type = self._detect_organ(task)

        if "分析" in task or "位置" in task:
            return await self._analyze(context, organ_type)

        if "生成" in task or "添加" in task or "支撑" in task:
            return await self._full_pipeline(context, organ_type, anchor_type)

        if "验证" in task or "检查" in task:
            return await self._validate(context)

        return await self._full_pipeline(context, organ_type, anchor_type)

    def _detect_organ(self, task: str) -> tuple[str, str | None]:
        for keyword, (organ_type, anchor, _desc) in self.ORGAN_STRATEGIES.items():
            if keyword in task:
                return organ_type, anchor
        return "general", None

    async def _analyze(self, ctx: AgentContext, organ_type: str) -> StepResult:
        r = await self.call_tool(
            "insert_analyze_positions",
            model_id=ctx.model_id, organ_type=organ_type,
        )
        return StepResult(
            step_name="analyze_positions", success=r.success,
            tool_calls=[{"tool": "insert_analyze_positions", "result": r.to_dict()}],
            output=r.data,
        )

    async def _full_pipeline(
        self, ctx: AgentContext, organ_type: str, anchor_type: str | None,
    ) -> StepResult:
        tool_calls = []
        r = await self.call_tool(
            "insert_generate",
            model_id=ctx.model_id,
            organ_type=organ_type,
            anchor_type=anchor_type,
            mold_id=ctx.mold_id,
        )
        tool_calls.append({"tool": "insert_generate", "result": r.to_dict()})

        if r.success and isinstance(r.data, dict) and r.data.get("insert_id"):
            val = await self.call_tool(
                "insert_validate",
                model_id=ctx.model_id,
                insert_id=r.data["insert_id"],
                mold_id=ctx.mold_id,
            )
            tool_calls.append({"tool": "insert_validate", "result": val.to_dict()})

        return StepResult(
            step_name="insert_pipeline", success=r.success,
            tool_calls=tool_calls,
            output={"message": "支撑板生成完成" if r.success else "生成失败"},
        )

    async def _validate(self, ctx: AgentContext) -> StepResult:
        return StepResult(
            step_name="validate", success=True,
            output={"message": "请先通过 insert_generate 生成支撑板后再验证"},
        )
