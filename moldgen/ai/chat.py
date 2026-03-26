"""LLM 对话 — 支持多 Provider 流式/非流式对话

Providers: DeepSeek (主力) / Qwen / Kimi (备选)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PROVIDER_ORDER = ["deepseek", "qwen", "kimi"]


@dataclass
class ChatResult:
    success: bool
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: dict = field(default_factory=dict)
    error: str | None = None


class ChatService:
    """LLM 对话服务 — 自动降级"""

    _instance: ChatService | None = None

    def __new__(cls) -> ChatService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

    async def chat(
        self,
        messages: list[dict],
        provider: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: str | None = None,
    ) -> ChatResult:
        """非流式对话 — 支持自动降级"""
        from moldgen.ai.service_manager import AIServiceManager
        svc = AIServiceManager()

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}, *messages]

        providers = [provider] if provider else self._get_available_providers()

        for p in providers:
            try:
                result = await svc.chat_completion(
                    messages=messages, model=p,
                    temperature=temperature, max_tokens=max_tokens,
                )
                if result:
                    return ChatResult(
                        success=True,
                        content=result["content"],
                        model=result.get("model", ""),
                        provider=p,
                        usage=result.get("usage", {}),
                    )
            except Exception as e:
                logger.warning("Chat provider %s failed: %s", p, e)
                continue

        return ChatResult(success=False, error="所有 AI 服务不可用。请检查 API Key 配置。")

    async def chat_stream(
        self,
        messages: list[dict],
        provider: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """流式对话 — 逐 token 返回"""
        from moldgen.ai.service_manager import AIServiceManager
        svc = AIServiceManager()

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}, *messages]

        provider = provider or self._get_available_providers()[0]

        try:
            stream = await svc.chat_completion(
                messages=messages, model=provider,
                temperature=temperature, max_tokens=max_tokens,
                stream=True,
            )
            if stream is None:
                yield "[ERROR] 无响应"
                return

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error("Stream chat failed: %s", e)
            yield f"[ERROR] {e}"

    async def optimize_prompt(self, user_prompt: str, target_lang: str = "en") -> str:
        """优化用户提示词用于 AI 图像/3D 生成"""
        system = (
            "你是一个专业的 AI 图像生成提示词优化专家。\n"
            "将用户的中文描述优化为适合 Stable Diffusion / FLUX 的英文提示词。\n"
            "规则:\n"
            "- 翻译为英文并添加质量修饰词\n"
            "- 添加医学专业术语 (如有器官相关内容)\n"
            "- 添加: highly detailed, medical grade, anatomically accurate, clean background\n"
            "- 添加: studio lighting, 3D render style, suitable for silicone casting mold\n"
            "- 只返回优化后的提示词，不要任何解释"
        )

        result = await self.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system,
            temperature=0.3,
            max_tokens=300,
        )
        return result.content if result.success else user_prompt

    def _get_available_providers(self) -> list[str]:
        from moldgen.config import get_config
        cfg = get_config().ai
        available = []
        if cfg.deepseek_api_key:
            available.append("deepseek")
        if cfg.qwen_api_key:
            available.append("qwen")
        if cfg.kimi_api_key:
            available.append("kimi")
        return available or ["deepseek"]
