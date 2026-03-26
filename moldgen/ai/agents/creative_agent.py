"""CreativeAgent — AI 图像/3D模型生成（云端 + 本地双后端）"""

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
        return "创意生成Agent — AI图像生成/AI 3D模型生成/需求转化（支持云端+本地模型切换）"

    @property
    def system_prompt(self) -> str:
        return (
            "你是 MoldGen 的创意生成 Agent。你负责将用户的文字描述转化为"
            "参考图像和3D模型。流程：优化提示词→生成图像→选择→生成3D模型→审查。"
            "擅长将中文描述优化为英文提示词并添加专业医学术语。"
            "你同时支持云端(通义万相+Tripo3D)和本地(SDXL/FLUX+TripoSR)两种后端。"
        )

    def get_available_tools(self) -> list[str]:
        return [
            "optimize_prompt",
            "generate_images",
            "generate_3d_from_text",
            "generate_3d_from_image",
            "review_model_quality",
            "list_local_models",
            "switch_provider",
        ]

    async def execute(self, task: str, context: AgentContext) -> StepResult:
        self.logger.info("CreativeAgent: %s", task[:80])
        events = []

        events.append(self.emit_event("thinking", {"message": "分析创意生成需求..."}))

        task_lower = task.lower()
        optimized_prompt = await self._smart_optimize(task)
        events.append(self.emit_event("tool_call", {
            "tool": "optimize_prompt",
            "input": task[:60],
            "output": optimized_prompt[:60],
        }))

        if any(kw in task_lower for kw in ["图像", "图片", "参考图", "渲染", "render"]):
            return await self._handle_image_gen(task, optimized_prompt, context, events)
        elif any(kw in task_lower for kw in ["3d", "三维", "模型", "重建", "mesh"]):
            return await self._handle_mesh_gen(task, optimized_prompt, context, events)
        elif any(kw in task_lower for kw in ["切换", "本地", "云端", "switch", "provider"]):
            return await self._handle_provider_switch(task, events)
        else:
            return await self._handle_full_pipeline(task, optimized_prompt, context, events)

    async def _smart_optimize(self, task: str) -> str:
        """智能提示词优化 — 尝试用 LLM, fallback 到规则"""
        try:
            from moldgen.ai.chat import ChatService
            result = await ChatService().optimize_prompt(task)
            if result and result != task:
                return result
        except Exception:
            pass
        return self._optimize_prompt_rules(task)

    async def _handle_image_gen(
        self, task: str, prompt: str, context: AgentContext, events: list
    ) -> StepResult:
        events.append(self.emit_event("step_start", {"task": "生成参考图像"}))

        try:
            from moldgen.ai.image_gen import ImageGenerator
            gen = ImageGenerator()
            result = await gen.generate(prompt=prompt, num_images=2)

            events.append(self.emit_event("tool_result", {
                "tool": "generate_images",
                "success": result.success,
                "provider": result.provider,
                "model": result.model,
                "count": len(result.images),
                "elapsed": result.elapsed_seconds,
            }))

            if result.success:
                return StepResult(
                    step_name=task,
                    success=True,
                    output={
                        "message": f"已生成 {len(result.images)} 张参考图像",
                        "images": result.images,
                        "provider": result.provider,
                        "model": result.model,
                        "prompt_used": result.prompt_used,
                        "elapsed_seconds": result.elapsed_seconds,
                    },
                    events=events,
                )
            else:
                return StepResult(
                    step_name=task,
                    success=False,
                    output={"message": f"图像生成失败: {result.error}"},
                    error=result.error,
                    events=events,
                )
        except Exception as e:
            return StepResult(
                step_name=task, success=False,
                output={"message": f"图像生成异常: {e}"},
                error=str(e), events=events,
            )

    async def _handle_mesh_gen(
        self, task: str, prompt: str, context: AgentContext, events: list
    ) -> StepResult:
        events.append(self.emit_event("step_start", {"task": "生成3D模型"}))

        try:
            from moldgen.ai.model_gen import MeshGenerator
            gen = MeshGenerator()

            if context.extra.get("image_path"):
                result = await gen.image_to_3d(image_path=context.extra["image_path"])
                method = "image-to-3D"
            else:
                result = await gen.text_to_3d(prompt=prompt)
                method = "text-to-3D"

            events.append(self.emit_event("tool_result", {
                "tool": f"generate_3d ({method})",
                "success": result.success,
                "provider": result.provider,
            }))

            if result.success:
                return StepResult(
                    step_name=task,
                    success=True,
                    output={
                        "message": f"3D模型已生成 ({method})",
                        "mesh_path": result.mesh_path,
                        "mesh_format": result.mesh_format,
                        "vertex_count": result.vertex_count,
                        "face_count": result.face_count,
                        "provider": result.provider,
                        "model": result.model,
                        "elapsed_seconds": result.elapsed_seconds,
                    },
                    events=events,
                )
            else:
                return StepResult(
                    step_name=task, success=False,
                    output={"message": f"3D生成失败: {result.error}"},
                    error=result.error, events=events,
                )
        except Exception as e:
            return StepResult(
                step_name=task, success=False,
                output={"message": f"3D生成异常: {e}"},
                error=str(e), events=events,
            )

    async def _handle_full_pipeline(
        self, task: str, prompt: str, context: AgentContext, events: list
    ) -> StepResult:
        """完整流水线: 优化提示词 → 生成图像 → 图像→3D"""
        events.append(self.emit_event("plan_start", {
            "message": "执行完整创意生成流水线",
            "steps": ["优化提示词", "生成参考图像", "选择最佳图像", "图像→3D模型"],
        }))

        try:
            from moldgen.ai.image_gen import ImageGenerator
            from moldgen.ai.model_gen import MeshGenerator

            img_gen = ImageGenerator()
            img_result = await img_gen.generate(prompt=prompt, num_images=2)

            if not img_result.success:
                return StepResult(
                    step_name=task, success=False,
                    output={"message": f"图像生成失败: {img_result.error}", "stage": "image"},
                    error=img_result.error, events=events,
                )

            events.append(self.emit_event("tool_result", {
                "tool": "generate_images",
                "success": True,
                "count": len(img_result.images),
            }))

            best_image = img_result.images[0]
            image_path = best_image.get("local_path", "")

            if not image_path:
                return StepResult(
                    step_name=task, success=True,
                    output={
                        "message": f"已生成 {len(img_result.images)} 张参考图。请选择一张用于3D重建。",
                        "images": img_result.images,
                        "stage": "awaiting_selection",
                    },
                    events=events,
                )

            mesh_gen = MeshGenerator()
            mesh_result = await mesh_gen.image_to_3d(image_path=image_path)

            events.append(self.emit_event("tool_result", {
                "tool": "image_to_3d",
                "success": mesh_result.success,
            }))

            if mesh_result.success:
                return StepResult(
                    step_name=task,
                    success=True,
                    output={
                        "message": "创意生成流水线完成: 图像→3D模型已就绪",
                        "images": img_result.images,
                        "mesh_path": mesh_result.mesh_path,
                        "vertex_count": mesh_result.vertex_count,
                        "face_count": mesh_result.face_count,
                        "pipeline": {
                            "image_provider": img_result.provider,
                            "mesh_provider": mesh_result.provider,
                            "total_elapsed": round(
                                img_result.elapsed_seconds + mesh_result.elapsed_seconds, 2
                            ),
                        },
                    },
                    events=events,
                )
            else:
                return StepResult(
                    step_name=task, success=False,
                    output={
                        "message": f"3D重建失败: {mesh_result.error}",
                        "images": img_result.images,
                        "stage": "mesh_failed",
                    },
                    error=mesh_result.error, events=events,
                )

        except Exception as e:
            return StepResult(
                step_name=task, success=False,
                output={"message": f"流水线异常: {e}"},
                error=str(e), events=events,
            )

    async def _handle_provider_switch(self, task: str, events: list) -> StepResult:
        """处理 provider 切换请求"""
        from moldgen.ai.local_models import LocalModelManager
        mgr = LocalModelManager()
        models = mgr.list_models()
        recommendation = mgr.recommend_models()

        return StepResult(
            step_name=task,
            success=True,
            output={
                "message": "本地模型管理信息",
                "available_models": models,
                "recommendation": recommendation,
                "vram_usage": mgr.get_vram_usage(),
            },
            events=events,
        )

    def _optimize_prompt_rules(self, task: str) -> str:
        """基于规则的提示词优化 (LLM 不可用时的 fallback)"""
        medical_terms = {
            "心脏": "anatomical human heart with chambers, valves and coronary vessels",
            "肝脏": "anatomical human liver with hepatic veins and portal system",
            "肾脏": "anatomical human kidney cross-section with cortex and medulla",
            "大脑": "anatomical human brain with gyri, sulci and cerebral hemispheres",
            "肺": "anatomical human lung with bronchial tree and alveoli",
            "脊柱": "anatomical human spine with vertebral column and intervertebral discs",
            "骨骼": "anatomical human skeleton with bone structure",
            "胃": "anatomical human stomach with gastric folds and pylorus",
            "眼球": "anatomical human eye with cornea, iris and retina",
            "耳朵": "anatomical human ear with cochlea and semicircular canals",
            "血管": "human vascular system with arteries and veins",
            "肠道": "anatomical human intestine with villi structure",
            "膀胱": "anatomical human urinary bladder cross-section",
            "子宫": "anatomical human uterus with fallopian tubes",
            "器官": "anatomical organ model for medical education",
        }

        prompt = task
        for cn, en in medical_terms.items():
            if cn in task:
                prompt = f"{en}, highly detailed, medical education model, "
                prompt += "smooth surface, clean topology, suitable for silicone casting, "
                prompt += "studio lighting, white background, 3D render"
                break
        else:
            if any(c >= "\u4e00" for c in task):
                prompt = f"{task}, medical model, highly detailed, 3D render, studio lighting"

        return prompt
