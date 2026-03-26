"""图像生成 — 云端 (通义万相 DashScope) + 本地 (Diffusers)

支持双后端透明切换:
  cloud:  通义万相 wanx2.1-t2i-plus (DashScope API)
  local:  SDXL / FLUX.1-schnell / SD 1.5 / Kolors (HuggingFace diffusers)
"""

from __future__ import annotations

import base64
import io
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ImageGenResult:
    success: bool
    images: list[dict] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    elapsed_seconds: float = 0.0
    error: str | None = None
    prompt_used: str = ""


class ImageGenerator:
    """图像生成器 — 云端/本地双后端"""

    _instance: ImageGenerator | None = None

    def __new__(cls) -> ImageGenerator:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._output_dir: Path | None = None

    @property
    def output_dir(self) -> Path:
        if self._output_dir is None:
            from moldgen.config import get_config
            self._output_dir = get_config().data_dir / "generated_images"
            self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        num_images: int = 1,
        width: int = 1024,
        height: int = 1024,
        steps: int | None = None,
        cfg_scale: float | None = None,
        seed: int | None = None,
        provider: str | None = None,
        model_id: str | None = None,
    ) -> ImageGenResult:
        """统一生成接口"""
        from moldgen.config import get_config
        cfg = get_config().ai
        provider = provider or cfg.image_provider

        t0 = time.time()

        if provider == "local":
            result = await self._generate_local(
                prompt, negative_prompt, num_images,
                width, height, steps, cfg_scale, seed,
                model_id or cfg.image_local_model,
            )
        else:
            result = await self._generate_cloud(
                prompt, negative_prompt, num_images,
                width, height, cfg.wanxiang_model,
            )

        result.elapsed_seconds = round(time.time() - t0, 2)
        return result

    # ── 云端: 通义万相 ────────────────────────────────────────────────

    async def _generate_cloud(
        self,
        prompt: str,
        negative_prompt: str,
        num_images: int,
        width: int,
        height: int,
        model: str,
    ) -> ImageGenResult:
        from moldgen.config import get_config
        api_key = get_config().ai.wanxiang_api_key
        if not api_key:
            return ImageGenResult(
                success=False,
                error="通义万相 API Key 未配置。请在设置中填入 MOLDGEN_AI_WANXIANG_API_KEY",
                provider="cloud",
                model=model,
                prompt_used=prompt,
            )

        try:
            import dashscope
            from dashscope import ImageSynthesis

            dashscope.api_key = api_key

            size_str = f"{width}*{height}"

            rsp = ImageSynthesis.call(
                model=model,
                input={"prompt": prompt, "negative_prompt": negative_prompt},
                parameters={
                    "size": size_str,
                    "n": min(num_images, 4),
                },
            )

            if rsp.status_code != 200:
                return ImageGenResult(
                    success=False,
                    error=f"万相 API 错误: {rsp.code} - {rsp.message}",
                    provider="cloud",
                    model=model,
                    prompt_used=prompt,
                )

            images = []
            for i, result in enumerate(rsp.output.results):
                image_url = result.get("url", "")
                img_id = str(uuid.uuid4())[:8]
                saved = await self._download_and_save(image_url, img_id)
                images.append({
                    "id": img_id,
                    "url": image_url,
                    "local_path": saved,
                    "index": i,
                })

            return ImageGenResult(
                success=True,
                images=images,
                provider="cloud",
                model=model,
                prompt_used=prompt,
            )

        except ImportError:
            return ImageGenResult(
                success=False,
                error="dashscope 包未安装。请运行: pip install dashscope",
                provider="cloud",
                model=model,
                prompt_used=prompt,
            )
        except Exception as e:
            logger.error("Cloud image generation failed: %s", e)
            return ImageGenResult(
                success=False,
                error=str(e),
                provider="cloud",
                model=model,
                prompt_used=prompt,
            )

    # ── 本地: Diffusers ───────────────────────────────────────────────

    async def _generate_local(
        self,
        prompt: str,
        negative_prompt: str,
        num_images: int,
        width: int,
        height: int,
        steps: int | None,
        cfg_scale: float | None,
        seed: int | None,
        model_id: str,
    ) -> ImageGenResult:
        from moldgen.ai.local_models import LocalModelManager, AVAILABLE_MODELS

        mgr = LocalModelManager()
        info = AVAILABLE_MODELS.get(model_id)
        if not info:
            return ImageGenResult(
                success=False,
                error=f"未知本地模型: {model_id}",
                provider="local",
                model=model_id,
                prompt_used=prompt,
            )

        pipe = mgr.get_loaded_model(model_id)
        if pipe is None:
            load_result = await mgr.load_model(model_id)
            if not load_result["success"]:
                return ImageGenResult(
                    success=False,
                    error=load_result.get("error", "加载失败"),
                    provider="local",
                    model=model_id,
                    prompt_used=prompt,
                )
            pipe = mgr.get_loaded_model(model_id)

        extra = info.extra_config
        steps = steps or extra.get("default_steps", 30)
        cfg_scale = cfg_scale or extra.get("default_cfg", 7.5)
        default_size = extra.get("default_size", 1024)
        if width > default_size:
            width = default_size
        if height > default_size:
            height = default_size

        try:
            import torch
            generator = None
            if seed is not None:
                generator = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu")
                generator.manual_seed(seed)

            gen_kwargs: dict[str, Any] = {
                "prompt": prompt,
                "num_inference_steps": steps,
                "width": width,
                "height": height,
                "num_images_per_prompt": num_images,
            }

            if cfg_scale > 0:
                gen_kwargs["guidance_scale"] = cfg_scale
            if negative_prompt:
                gen_kwargs["negative_prompt"] = negative_prompt
            if generator:
                gen_kwargs["generator"] = generator

            if "max_sequence_length" in extra:
                gen_kwargs["max_sequence_length"] = extra["max_sequence_length"]

            output = pipe(**gen_kwargs)
            pil_images = output.images

            images = []
            for i, pil_img in enumerate(pil_images):
                img_id = str(uuid.uuid4())[:8]
                save_path = self.output_dir / f"{img_id}.png"
                pil_img.save(save_path)

                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()

                images.append({
                    "id": img_id,
                    "local_path": str(save_path),
                    "base64_thumbnail": b64[:200] + "...",
                    "width": pil_img.width,
                    "height": pil_img.height,
                    "index": i,
                })

            from moldgen.config import get_config
            if get_config().ai.auto_unload_after_gen:
                mgr.unload_model(model_id)

            return ImageGenResult(
                success=True,
                images=images,
                provider="local",
                model=model_id,
                prompt_used=prompt,
            )

        except Exception as e:
            logger.error("Local image generation failed: %s", e)
            return ImageGenResult(
                success=False,
                error=str(e),
                provider="local",
                model=model_id,
                prompt_used=prompt,
            )

    # ── 工具函数 ──────────────────────────────────────────────────────

    async def _download_and_save(self, url: str, img_id: str) -> str:
        """下载远程图片到本地"""
        save_path = self.output_dir / f"{img_id}.png"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                save_path.write_bytes(resp.content)
            return str(save_path)
        except Exception as e:
            logger.warning("Failed to download image %s: %s", url, e)
            return ""

    def get_generated_images(self, limit: int = 20) -> list[dict]:
        """列出已生成的图片"""
        images = []
        for p in sorted(self.output_dir.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            images.append({
                "id": p.stem,
                "path": str(p),
                "filename": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "created": p.stat().st_mtime,
            })
        return images
