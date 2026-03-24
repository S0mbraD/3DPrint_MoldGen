"""ModelAgent — 模型导入、修复、编辑、变换"""

from __future__ import annotations

from moldgen.ai.agent_base import AgentContext, AgentRole, BaseAgent, StepResult


class ModelAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentRole.MODEL)

    @property
    def name(self) -> str:
        return "ModelAgent"

    @property
    def description(self) -> str:
        return "模型处理Agent — 导入/修复/简化/细化/编辑/变换"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 MoldGen 的模型处理 Agent。你负责3D模型的导入、质量检查、"
            "自动修复、简化、细化、变换和布尔运算。"
            "当模型面数>100K时建议简化，非水密时自动修复。"
        )

    def get_available_tools(self) -> list[str]:
        return [
            "model_load", "model_quality_check", "model_repair",
            "model_simplify", "model_subdivide", "model_transform",
            "model_boolean", "model_get_info",
        ]

    async def execute(self, task: str, context: AgentContext) -> StepResult:
        self.logger.info("ModelAgent executing: %s", task[:80])

        tool_calls = []

        if "加载" in task or "导入" in task or "检查" in task:
            if context.model_id:
                result = await self.call_tool("model_quality_check", model_id=context.model_id)
                tool_calls.append({"tool": "model_quality_check", "result": result.to_dict()})

                if result.success and result.data:
                    quality = result.data
                    if isinstance(quality, dict) and not quality.get("is_watertight", True):
                        repair_result = await self.call_tool("model_repair", model_id=context.model_id)
                        tool_calls.append({"tool": "model_repair", "result": repair_result.to_dict()})

        elif "修复" in task:
            if context.model_id:
                result = await self.call_tool("model_repair", model_id=context.model_id)
                tool_calls.append({"tool": "model_repair", "result": result.to_dict()})

        elif "简化" in task:
            if context.model_id:
                result = await self.call_tool("model_simplify", model_id=context.model_id, ratio=0.5)
                tool_calls.append({"tool": "model_simplify", "result": result.to_dict()})

        elif "居中" in task or "center" in task.lower():
            if context.model_id:
                result = await self.call_tool(
                    "model_transform", model_id=context.model_id, operation="center",
                )
                tool_calls.append({"tool": "model_transform", "result": result.to_dict()})

        else:
            return StepResult(
                step_name=task, success=True,
                output={"message": f"ModelAgent 已准备好处理: {task}",
                        "available_tools": self.get_available_tools()},
            )

        success = all(tc["result"]["success"] for tc in tool_calls) if tool_calls else True
        return StepResult(
            step_name=task,
            success=success,
            tool_calls=tool_calls,
            output={"n_tool_calls": len(tool_calls)},
        )
