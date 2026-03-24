"""CreativeAgent — AI 图像/3D模型生成（需要 AI API，提供框架）"""

from __future__ import annotations

from moldgen.ai.agent_base import AgentContext, AgentRole, BaseAgent, StepResult


class CreativeAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentRole.CREATIVE)

    @property
    def name(self) -> str:
        return "CreativeAgent"

    @property
    def description(self) -> str:
        return "创意生成Agent — AI图像生成/AI 3D模型生成/需求转化"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 MoldGen 的创意生成 Agent。你负责将用户的文字描述转化为"
            "参考图像和3D模型。流程：优化提示词→生成图像→选择→生成3D模型→审查。"
            "擅长将中文描述优化为英文提示词并添加专业医学术语。"
        )

    def get_available_tools(self) -> list[str]:
        return []

    async def execute(self, task: str, context: AgentContext) -> StepResult:
        self.logger.info("CreativeAgent: %s", task[:80])

        optimized_prompt = self._optimize_prompt(task)

        return StepResult(
            step_name=task,
            success=True,
            output={
                "message": "创意生成已准备就绪。需要配置 AI API（通义万相/Tripo3D）后使用。",
                "optimized_prompt": optimized_prompt,
                "pipeline": [
                    "1. 提示词优化 (中文→英文+专业术语)",
                    "2. 生成参考图像 (通义万相)",
                    "3. 用户选择最佳图像",
                    "4. 图像→3D模型 (Tripo3D)",
                    "5. 模型质量审查",
                ],
            },
        )

    def _optimize_prompt(self, task: str) -> str:
        """Simple prompt optimization for medical model generation."""
        medical_terms = {
            "心脏": "anatomical human heart with chambers and vessels",
            "肝脏": "anatomical human liver with hepatic veins and portal system",
            "肾脏": "anatomical human kidney cross-section with cortex and medulla",
            "大脑": "anatomical human brain with gyri and sulci",
            "肺": "anatomical human lung with bronchial tree",
            "脊柱": "anatomical human spine vertebral column",
            "骨骼": "anatomical human skeleton",
            "器官": "anatomical organ model",
        }

        prompt = task
        for cn, en in medical_terms.items():
            if cn in task:
                prompt = f"{en}, highly detailed, medical education model, "
                prompt += "smooth surface, clean topology, suitable for silicone casting"
                break

        return prompt
