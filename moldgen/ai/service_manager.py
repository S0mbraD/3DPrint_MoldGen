"""AI 服务统一管理 — 提供对所有 AI API 的统一访问接口"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from moldgen.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class AIServiceStatus:
    deepseek: bool = False
    qwen: bool = False
    kimi: bool = False
    wanxiang: bool = False
    tripo3d: bool = False
    local_image: bool = False
    local_mesh: bool = False
    image_provider: str = "cloud"
    mesh_provider: str = "cloud"


class AIServiceManager:
    """AI 服务管理器 — 统一管理所有 AI API 连接"""

    _instance: AIServiceManager | None = None

    def __new__(cls) -> AIServiceManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._config = get_config().ai

    def get_status(self) -> AIServiceStatus:
        local_image = False
        local_mesh = False
        try:
            from moldgen.ai.local_models import LocalModelManager
            mgr = LocalModelManager()
            for m in mgr.list_models():
                if m["is_loaded"] and m["category"] == "image_gen":
                    local_image = True
                if m["is_loaded"] and m["category"] == "mesh_gen":
                    local_mesh = True
        except Exception:
            pass

        return AIServiceStatus(
            deepseek=bool(self._config.deepseek_api_key),
            qwen=bool(self._config.qwen_api_key),
            kimi=bool(self._config.kimi_api_key),
            wanxiang=bool(self._config.wanxiang_api_key),
            tripo3d=bool(self._config.tripo_api_key),
            local_image=local_image,
            local_mesh=local_mesh,
            image_provider=self._config.image_provider,
            mesh_provider=self._config.mesh_provider,
        )

    def _get_client_config(self, model: str) -> tuple[str, str, str]:
        """Returns (api_key, base_url, model_name) for the given model alias."""
        cfg = self._config
        configs = {
            "deepseek": (cfg.deepseek_api_key, cfg.deepseek_base_url, cfg.deepseek_model),
            "qwen": (cfg.qwen_api_key, cfg.qwen_base_url, cfg.qwen_chat_model),
            "qwen-vl": (cfg.qwen_api_key, cfg.qwen_base_url, cfg.qwen_vl_model),
            "kimi": (cfg.kimi_api_key, cfg.kimi_base_url, cfg.kimi_model),
        }
        if model not in configs:
            raise ValueError(f"Unknown model: {model}. Available: {list(configs.keys())}")
        api_key, base_url, model_name = configs[model]
        if not api_key:
            raise ValueError(f"{model} API key not configured")
        return api_key, base_url, model_name

    async def chat_completion(
        self,
        messages: list[dict],
        model: str = "deepseek",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
    ) -> dict | None:
        from openai import AsyncOpenAI

        api_key, base_url, model_name = self._get_client_config(model)
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        if stream:
            return await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return {
            "content": response.choices[0].message.content,
            "model": model_name,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }

    async def test_connection(self, model: str = "deepseek") -> dict:
        try:
            result = await self.chat_completion(
                messages=[{"role": "user", "content": "Hello, respond with exactly: CONNECTED"}],
                model=model,
                temperature=0,
                max_tokens=20,
            )
            success = result is not None and "CONNECTED" in (result.get("content", "") or "")
            return {
                "model": model,
                "success": success,
                "response": result.get("content", "") if result else None,
                "usage": result.get("usage") if result else None,
            }
        except Exception as e:
            return {"model": model, "success": False, "error": str(e)}
