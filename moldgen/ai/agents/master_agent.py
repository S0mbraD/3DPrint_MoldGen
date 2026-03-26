"""MasterAgent — 总控调度，支持关键字路由 + LLM 智能推理 + 自省"""

from __future__ import annotations

import logging
import time

from moldgen.ai.agent_base import (
    AgentConfig,
    AgentContext,
    AgentEvent,
    AgentRole,
    BaseAgent,
    StepResult,
    ThinkingStyle,
)
from moldgen.ai.execution_engine import PIPELINE_TEMPLATES, AgentExecutionEngine
from moldgen.ai.memory import AgentMemoryManager

logger = logging.getLogger(__name__)

KEYWORD_ROUTES: dict[str, AgentRole] = {
    "导入": AgentRole.MODEL, "加载": AgentRole.MODEL, "上传": AgentRole.MODEL,
    "修复": AgentRole.MODEL, "简化": AgentRole.MODEL, "细化": AgentRole.MODEL,
    "编辑": AgentRole.MODEL, "变换": AgentRole.MODEL, "布尔": AgentRole.MODEL,
    "导出": AgentRole.MODEL, "export": AgentRole.MODEL,
    "脱模": AgentRole.MOLD, "方向": AgentRole.MOLD, "分型": AgentRole.MOLD,
    "模具": AgentRole.MOLD, "壳体": AgentRole.MOLD,
    "插板": AgentRole.INSERT, "支撑": AgentRole.INSERT, "锚固": AgentRole.INSERT,
    "仿真": AgentRole.SIM, "灌注": AgentRole.SIM, "优化": AgentRole.SIM,
    "浇注": AgentRole.SIM, "材料": AgentRole.SIM,
    "生成": AgentRole.CREATIVE, "创建": AgentRole.CREATIVE, "设计": AgentRole.CREATIVE,
    "图像": AgentRole.CREATIVE, "图片": AgentRole.CREATIVE,
}

PIPELINE_KEYWORDS: dict[str, str] = {
    "全自动": "full_from_model",
    "从头开始": "full_from_text",
    "一键": "full_from_model",
    "完整流程": "full_from_model",
    "只做模具": "mold_only",
    "只仿真": "sim_only",
}

INTENT_CLASSIFICATION_PROMPT = """\
你是 MoldGen 的意图分析器。分析用户请求并给出结构化判断。

可用 Agent: model(模型处理), mold(模具设计), insert(支撑板), sim(仿真优化), creative(创意生成)
可用流水线: full_from_model(已有模型完整流程), full_from_text(从零开始), mold_only(仅模具), sim_only(仅仿真)

用户请求: {task}
当前上下文: {context}

请用以下 JSON 格式回答（不要多余文字）:
{{
  "intent": "描述用户意图(10字内)",
  "target_agent": "agent名称或null",
  "pipeline": "流水线名称或null",
  "confidence": 0.0-1.0,
  "reasoning": "简短推理过程(30字内)",
  "suggested_params": {{}},
  "needs_clarification": false,
  "clarification_question": ""
}}"""

SELF_REFLECTION_PROMPT = """\
你是 MoldGen Agent 系统的自省模块。评估刚完成的操作并给出改进建议。

操作: {step_name}
结果: {result_summary}
耗时: {elapsed}秒

请简短评估（50字内）：这次操作{success_text}，原因可能是什么？下次有什么改进方向？"""


class MasterAgent(BaseAgent):
    def __init__(
        self,
        engine: AgentExecutionEngine | None = None,
        config: AgentConfig | None = None,
    ):
        super().__init__(AgentRole.MASTER, config)
        self.engine = engine
        self._memory = AgentMemoryManager()
        self._ai_service = None
        self._execution_history: list[dict] = []

    @property
    def name(self) -> str:
        return "MasterAgent"

    @property
    def description(self) -> str:
        return "总控调度Agent — 意图识别、任务规划、Agent路由、自省优化"

    @property
    def system_prompt(self) -> str:
        base = (
            "你是 MoldGen 的总控 Agent。你的职责是理解用户意图，"
            "将任务分解并分配给专业 Agent 执行。可用Agent: "
            "ModelAgent(模型处理), MoldDesignAgent(模具设计), "
            "InsertAgent(支撑板), SimOptAgent(仿真优化), "
            "CreativeAgent(创意生成)。"
        )
        memory_ctx = self._memory.build_context_summary()
        if memory_ctx:
            base += f"\n\n记忆上下文:\n{memory_ctx}"
        return base

    def get_available_tools(self) -> list[str]:
        return []

    def _get_ai_service(self):
        if self._ai_service is None:
            try:
                from moldgen.ai.service_manager import AIServiceManager
                self._ai_service = AIServiceManager()
            except Exception:
                pass
        return self._ai_service

    async def execute(self, task: str, context: AgentContext) -> StepResult:
        start = time.time()
        self.logger.info("MasterAgent routing: %s", task[:80])

        if self.config.enable_memory:
            prefs = self._memory.extract_preferences(task)
            if prefs:
                context.user_preferences.update(prefs)

        context.memory_context = self._memory.build_context_summary()

        events: list[AgentEvent] = []
        events.append(self.emit_event("thinking", {"message": f"分析任务: {task[:60]}"}))

        style = self.config.thinking_style

        if style == ThinkingStyle.DEEP:
            result = await self._deep_reasoning(task, context, events)
        elif style == ThinkingStyle.BALANCED:
            result = await self._balanced_reasoning(task, context, events)
        else:
            result = await self._fast_routing(task, context, events)

        result.events = events
        result.elapsed_seconds = time.time() - start

        if self.config.enable_self_reflection and result.success:
            reflection = await self._self_reflect(result)
            if reflection:
                result.thinking += f"\n[自省] {reflection}"

        self._record_history(task, result)
        return result

    async def _fast_routing(
        self, task: str, context: AgentContext, events: list[AgentEvent],
    ) -> StepResult:
        """快速关键字匹配路由"""
        events.append(self.emit_event("decision", {"style": "fast", "method": "keyword"}))

        pipeline = self._match_pipeline(task)
        if pipeline and self.engine:
            plan = self.engine.create_plan(pipeline)
            if plan:
                result = await self.engine.execute_plan(plan, context)
                return StepResult(
                    step_name=f"Pipeline: {pipeline}",
                    success=result.success,
                    output=result.to_dict(),
                    thinking=f"关键字匹配流水线: {pipeline}",
                )

        target = self._route_by_keyword(task)
        if target and self.engine:
            agent = self.engine.get_agent(target)
            if agent:
                r = await agent.execute(task, context)
                r.thinking = f"关键字路由到: {target.value}"
                return r

        return self._fallback_result(task)

    async def _balanced_reasoning(
        self, task: str, context: AgentContext, events: list[AgentEvent],
    ) -> StepResult:
        """平衡模式：先尝试 LLM 分析，失败则降级为关键字路由"""
        ai = self._get_ai_service()
        if ai:
            try:
                classification = await self._llm_classify(task, context)
                events.append(self.emit_event("thinking", {
                    "message": f"LLM 分析: {classification.get('reasoning', '')}",
                    "classification": classification,
                }))

                if classification.get("needs_clarification"):
                    return StepResult(
                        step_name="clarification",
                        success=True,
                        needs_confirmation=True,
                        confirmation_message=classification.get("clarification_question", "请提供更多信息"),
                        thinking=f"需要澄清: {classification.get('reasoning', '')}",
                    )

                confidence = classification.get("confidence", 0)
                if confidence >= self.config.auto_confirm_threshold:
                    return await self._execute_classification(classification, task, context, events)

                events.append(self.emit_event("decision", {
                    "message": f"置信度 {confidence:.2f} 低于阈值，降级为关键字路由",
                }))
            except Exception as e:
                self.logger.warning("LLM classification failed, falling back: %s", e)
                events.append(self.emit_event("error", {"message": f"LLM 降级: {e}"}))

        return await self._fast_routing(task, context, events)

    async def _deep_reasoning(
        self, task: str, context: AgentContext, events: list[AgentEvent],
    ) -> StepResult:
        """深度 CoT 推理模式"""
        ai = self._get_ai_service()
        if not ai:
            events.append(self.emit_event("decision", {"message": "无 AI 服务，降级快速路由"}))
            return await self._fast_routing(task, context, events)

        try:
            classification = await self._llm_classify(task, context)
            events.append(self.emit_event("thinking", {
                "message": f"深度分析: {classification.get('reasoning', '')}",
                "classification": classification,
            }))

            result = await self._execute_classification(classification, task, context, events)

            if self.config.enable_self_reflection and not result.success:
                events.append(self.emit_event("thinking", {"message": "执行失败，尝试备选方案..."}))
                fallback = await self._fast_routing(task, context, events)
                if fallback.success:
                    fallback.thinking += " [深度推理失败后关键字兜底成功]"
                    return fallback
                return result

            return result

        except Exception as e:
            self.logger.exception("Deep reasoning failed")
            events.append(self.emit_event("error", {"message": str(e)}))
            return await self._fast_routing(task, context, events)

    async def _llm_classify(self, task: str, context: AgentContext) -> dict:
        """使用 LLM 进行意图分类"""
        ai = self._get_ai_service()
        if not ai:
            raise RuntimeError("AI service not available")

        ctx_summary = f"model={context.model_id}, mold={context.mold_id}, mode={context.mode.value}"
        prompt = INTENT_CLASSIFICATION_PROMPT.format(task=task, context=ctx_summary)

        result = await ai.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="deepseek",
            temperature=0.1,
            max_tokens=300,
        )

        import json
        content = result.get("content", "{}") if result else "{}"
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(content)

    async def _execute_classification(
        self, classification: dict, task: str, context: AgentContext, events: list[AgentEvent],
    ) -> StepResult:
        """根据 LLM 分类结果执行"""
        pipeline = classification.get("pipeline")
        if pipeline and self.engine:
            plan = self.engine.create_plan(pipeline)
            if plan:
                events.append(self.emit_event("decision", {"pipeline": pipeline}))
                result = await self.engine.execute_plan(plan, context)
                return StepResult(
                    step_name=f"Pipeline: {pipeline}",
                    success=result.success,
                    output=result.to_dict(),
                    thinking=f"LLM 推荐流水线: {pipeline} ({classification.get('reasoning', '')})",
                )

        target_str = classification.get("target_agent")
        if target_str and self.engine:
            role_map = {
                "model": AgentRole.MODEL, "mold": AgentRole.MOLD,
                "insert": AgentRole.INSERT, "sim": AgentRole.SIM,
                "creative": AgentRole.CREATIVE,
            }
            role = role_map.get(target_str)
            if role:
                agent = self.engine.get_agent(role)
                if agent:
                    events.append(self.emit_event("decision", {"target": target_str}))
                    r = await agent.execute(task, context)
                    r.thinking = f"LLM 路由: {target_str} ({classification.get('reasoning', '')})"
                    return r

        return self._fallback_result(task)

    async def _self_reflect(self, result: StepResult) -> str | None:
        """执行后自省 — 评估执行质量并学习"""
        ai = self._get_ai_service()
        if not ai:
            return None

        try:
            prompt = SELF_REFLECTION_PROMPT.format(
                step_name=result.step_name,
                result_summary=str(result.output)[:200] if result.output else "无输出",
                elapsed=f"{result.elapsed_seconds:.1f}",
                success_text="成功" if result.success else "失败",
            )

            resp = await ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="deepseek",
                temperature=0.3,
                max_tokens=100,
            )
            return resp.get("content", "") if resp else None
        except Exception:
            return None

    def _fallback_result(self, task: str) -> StepResult:
        return StepResult(
            step_name="route",
            success=True,
            output={
                "message": "已理解您的需求，请告诉我更具体的操作。",
                "available_agents": [r.value for r in AgentRole if r != AgentRole.MASTER],
                "available_pipelines": list(PIPELINE_TEMPLATES.keys()),
            },
            thinking="未能确定路由目标",
        )

    def _match_pipeline(self, task: str) -> str | None:
        for keyword, pipeline in PIPELINE_KEYWORDS.items():
            if keyword in task:
                return pipeline
        return None

    def _route_by_keyword(self, task: str) -> AgentRole | None:
        for keyword, role in KEYWORD_ROUTES.items():
            if keyword in task:
                return role
        return None

    def classify_intent(self, task: str) -> dict:
        """Classify user intent without executing (for UI preview)."""
        pipeline = self._match_pipeline(task)
        target = self._route_by_keyword(task)
        return {
            "task": task,
            "pipeline": pipeline,
            "target_agent": target.value if target else None,
            "confidence": 0.9 if (pipeline or target) else 0.3,
            "thinking_style": self.config.thinking_style.value,
        }

    def _record_history(self, task: str, result: StepResult) -> None:
        self._execution_history.append({
            "task": task[:100],
            "step_name": result.step_name,
            "success": result.success,
            "elapsed": result.elapsed_seconds,
            "timestamp": time.time(),
        })
        if len(self._execution_history) > 100:
            self._execution_history = self._execution_history[-100:]

        if self.config.enable_memory and result.success:
            self._memory.long_term.record_usage(
                self.role.value, result.step_name, result.success,
            )

    def get_execution_history(self) -> list[dict]:
        return list(self._execution_history)
