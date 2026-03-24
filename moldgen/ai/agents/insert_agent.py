"""InsertAgent — 内嵌支撑板设计（AI辅助板型分析+锚固+立柱+装配验证）"""

from __future__ import annotations

from moldgen.ai.agent_base import AgentContext, AgentRole, BaseAgent, StepResult


class InsertAgent(BaseAgent):
    ORGAN_STRATEGIES = {
        "肝": ("solid", "conformal", "mesh_holes", "仿形板+贯穿孔"),
        "肾": ("solid", "conformal", "mesh_holes", "仿形板+贯穿孔"),
        "脑": ("solid", "conformal", "grooves", "仿形板+沟槽"),
        "胃": ("hollow", "flat", "bumps", "平板+凸起互锁"),
        "膀胱": ("hollow", "flat", "bumps", "平板+凸起互锁"),
        "血管": ("tubular", "flat", "mesh_holes", "平板+贯穿孔"),
        "肠": ("tubular", "flat", "grooves", "平板+沟槽"),
        "手臂": ("limb", "ribbed", "mesh_holes", "加强筋板+贯穿孔"),
        "腿": ("limb", "ribbed", "mesh_holes", "加强筋板+贯穿孔"),
        "皮肤": ("sheet", "lattice", "diamond", "格栅板+菱形纹"),
        "肌肉": ("sheet", "ribbed", "bumps", "加强筋板+凸起"),
    }

    def __init__(self):
        super().__init__(AgentRole.INSERT)

    @property
    def name(self) -> str:
        return "InsertAgent"

    @property
    def description(self) -> str:
        return "内嵌支撑板设计Agent — 板型分析/锚固设计/立柱布置/装配验证"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 MoldGen 的支撑板设计专家。你结合解剖学知识和工程经验，"
            "为硅胶教具设计内嵌结构加固板。核心概念：支撑板是置于硅胶教具"
            "内部的刚性结构板，通过锚固特征（贯穿孔/凸起/沟槽/燕尾榫）与"
            "硅胶结合，并通过细小支撑立柱穿过模具壁定位。"
            "板型：平板(截面挤出)、仿形板(曲面跟随)、加强筋板(平板+肋条)、"
            "格栅板(轻量点阵)。"
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

        organ_type, insert_type, anchor_type = self._detect_organ(task)

        if "分析" in task or "位置" in task or "推荐" in task:
            return await self._analyze(context, organ_type)

        if "生成" in task or "添加" in task or "支撑" in task or "板" in task:
            return await self._full_pipeline(context, organ_type, insert_type, anchor_type)

        if "验证" in task or "检查" in task:
            return await self._validate(context)

        return await self._full_pipeline(context, organ_type, insert_type, anchor_type)

    def _detect_organ(self, task: str) -> tuple[str, str | None, str | None]:
        for keyword, (organ_type, ins_type, anc_type, _desc) in self.ORGAN_STRATEGIES.items():
            if keyword in task:
                return organ_type, ins_type, anc_type
        return "general", None, None

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
        self, ctx: AgentContext, organ_type: str,
        insert_type: str | None, anchor_type: str | None,
    ) -> StepResult:
        tool_calls = []
        params: dict = {
            "model_id": ctx.model_id,
            "organ_type": organ_type,
            "mold_id": ctx.mold_id,
        }
        if insert_type:
            params["insert_type"] = insert_type
        if anchor_type:
            params["anchor_type"] = anchor_type

        r = await self.call_tool("insert_generate", **params)
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
            output={"message": "请先生成支撑板后再验证装配"},
        )
