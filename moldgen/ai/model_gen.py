"""3D 模型生成 — 云端 (Tripo3D API) + 本地 (TripoSR)

支持双后端透明切换:
  cloud:  Tripo3D API (text-to-3d / image-to-3d)
  local:  TripoSR (image-to-3d, 单图重建)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MeshGenResult:
    success: bool
    mesh_path: str = ""
    mesh_format: str = "glb"
    provider: str = ""
    model: str = ""
    elapsed_seconds: float = 0.0
    vertex_count: int = 0
    face_count: int = 0
    error: str | None = None
    task_id: str = ""
    metadata: dict = field(default_factory=dict)


class MeshGenerator:
    """3D 模型生成器 — 云端/本地双后端"""

    _instance: MeshGenerator | None = None

    def __new__(cls) -> MeshGenerator:
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
            self._output_dir = get_config().data_dir / "generated_meshes"
            self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir

    # ── 文字 → 3D ─────────────────────────────────────────────────────

    async def text_to_3d(
        self,
        prompt: str,
        provider: str | None = None,
        model_id: str | None = None,
        **kwargs: Any,
    ) -> MeshGenResult:
        """文字描述→3D模型 (仅云端 Tripo3D 支持)"""
        from moldgen.config import get_config
        provider = provider or get_config().ai.mesh_provider
        t0 = time.time()

        if provider == "local":
            return MeshGenResult(
                success=False,
                error="本地模型 (TripoSR) 不支持 text-to-3D，请使用 image-to-3D 或切换到云端 Tripo3D",
                provider="local",
            )

        result = await self._text_to_3d_tripo(prompt, **kwargs)
        result.elapsed_seconds = round(time.time() - t0, 2)
        return result

    # ── 图片 → 3D ─────────────────────────────────────────────────────

    async def image_to_3d(
        self,
        image_path: str,
        provider: str | None = None,
        model_id: str | None = None,
        **kwargs: Any,
    ) -> MeshGenResult:
        """单张图片→3D模型"""
        from moldgen.config import get_config
        cfg = get_config().ai
        provider = provider or cfg.mesh_provider
        t0 = time.time()

        if provider == "local":
            result = await self._image_to_3d_local(
                image_path, model_id or cfg.mesh_local_model, **kwargs
            )
        else:
            result = await self._image_to_3d_tripo(image_path, **kwargs)

        result.elapsed_seconds = round(time.time() - t0, 2)
        return result

    # ── 云端: Tripo3D API ─────────────────────────────────────────────

    async def _text_to_3d_tripo(self, prompt: str, **kwargs: Any) -> MeshGenResult:
        from moldgen.config import get_config
        api_key = get_config().ai.tripo_api_key
        if not api_key:
            return MeshGenResult(
                success=False,
                error="Tripo3D API Key 未配置。请在设置中填入 MOLDGEN_AI_TRIPO_API_KEY",
                provider="cloud",
                model="tripo3d",
            )

        try:
            import httpx
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            base_url = "https://api.tripo3d.ai/v2/openapi"

            async with httpx.AsyncClient(timeout=120) as client:
                create_resp = await client.post(
                    f"{base_url}/task",
                    headers=headers,
                    json={"type": "text_to_model", "prompt": prompt},
                )
                create_resp.raise_for_status()
                task_data = create_resp.json()
                task_id = task_data["data"]["task_id"]

                mesh_result = await self._poll_tripo_task(client, headers, base_url, task_id)
                mesh_result.prompt_used = prompt if hasattr(mesh_result, "prompt_used") else ""
                return mesh_result

        except Exception as e:
            logger.error("Tripo3D text-to-3D failed: %s", e)
            return MeshGenResult(success=False, error=str(e), provider="cloud", model="tripo3d")

    async def _image_to_3d_tripo(self, image_path: str, **kwargs: Any) -> MeshGenResult:
        from moldgen.config import get_config
        api_key = get_config().ai.tripo_api_key
        if not api_key:
            return MeshGenResult(
                success=False,
                error="Tripo3D API Key 未配置",
                provider="cloud",
                model="tripo3d",
            )

        try:
            import httpx
            headers = {"Authorization": f"Bearer {api_key}"}
            base_url = "https://api.tripo3d.ai/v2/openapi"

            async with httpx.AsyncClient(timeout=120) as client:
                upload_resp = await client.post(
                    f"{base_url}/upload",
                    headers=headers,
                    files={"file": open(image_path, "rb")},
                )
                upload_resp.raise_for_status()
                file_token = upload_resp.json()["data"]["image_token"]

                create_resp = await client.post(
                    f"{base_url}/task",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"type": "image_to_model", "file": {"type": "png", "file_token": file_token}},
                )
                create_resp.raise_for_status()
                task_id = create_resp.json()["data"]["task_id"]

                return await self._poll_tripo_task(client, headers, base_url, task_id)

        except Exception as e:
            logger.error("Tripo3D image-to-3D failed: %s", e)
            return MeshGenResult(success=False, error=str(e), provider="cloud", model="tripo3d")

    async def _poll_tripo_task(
        self, client: Any, headers: dict, base_url: str, task_id: str
    ) -> MeshGenResult:
        """轮询 Tripo3D 任务直到完成"""
        import asyncio

        for _ in range(60):
            await asyncio.sleep(2)
            status_resp = await client.get(f"{base_url}/task/{task_id}", headers=headers)
            status_resp.raise_for_status()
            data = status_resp.json()["data"]

            if data["status"] == "success":
                model_url = data["output"]["model"]
                mesh_id = str(uuid.uuid4())[:8]
                save_path = self.output_dir / f"{mesh_id}.glb"

                dl_resp = await client.get(model_url)
                dl_resp.raise_for_status()
                save_path.write_bytes(dl_resp.content)

                return MeshGenResult(
                    success=True,
                    mesh_path=str(save_path),
                    mesh_format="glb",
                    provider="cloud",
                    model="tripo3d",
                    task_id=task_id,
                )
            elif data["status"] == "failed":
                return MeshGenResult(
                    success=False,
                    error=f"Tripo3D 任务失败: {data.get('message', 'unknown')}",
                    provider="cloud",
                    model="tripo3d",
                    task_id=task_id,
                )

        return MeshGenResult(
            success=False,
            error="Tripo3D 任务超时 (120s)",
            provider="cloud",
            model="tripo3d",
            task_id=task_id,
        )

    # ── 本地: TripoSR ─────────────────────────────────────────────────

    async def _image_to_3d_local(
        self, image_path: str, model_id: str, **kwargs: Any
    ) -> MeshGenResult:
        from moldgen.ai.local_models import LocalModelManager, AVAILABLE_MODELS

        mgr = LocalModelManager()
        info = AVAILABLE_MODELS.get(model_id)
        if not info:
            return MeshGenResult(
                success=False,
                error=f"未知本地模型: {model_id}",
                provider="local",
                model=model_id,
            )

        model = mgr.get_loaded_model(model_id)
        if model is None:
            load_result = await mgr.load_model(model_id)
            if not load_result["success"]:
                return MeshGenResult(
                    success=False,
                    error=load_result.get("error", "加载失败"),
                    provider="local",
                    model=model_id,
                )
            model = mgr.get_loaded_model(model_id)

        try:
            if model_id == "triposr":
                return await self._run_triposr(model, image_path, info, **kwargs)
            else:
                return MeshGenResult(
                    success=False,
                    error=f"本地 3D 推理未实现: {model_id}",
                    provider="local",
                    model=model_id,
                )
        except Exception as e:
            logger.error("Local mesh gen failed: %s", e)
            return MeshGenResult(success=False, error=str(e), provider="local", model=model_id)
        finally:
            from moldgen.config import get_config
            if get_config().ai.auto_unload_after_gen:
                mgr.unload_model(model_id)

    async def _run_triposr(
        self, model: Any, image_path: str, info: Any, **kwargs: Any
    ) -> MeshGenResult:
        import numpy as np
        from PIL import Image

        image = Image.open(image_path).convert("RGBA")

        bg_color = [255, 255, 255]
        bg = Image.new("RGBA", image.size, (*bg_color, 255))
        bg.paste(image, mask=image.split()[-1])
        image = bg.convert("RGB")

        mc_resolution = kwargs.get("mc_resolution", info.extra_config.get("mc_resolution", 256))

        with __import__("torch").no_grad():
            scene_codes = model([image], device="cuda" if __import__("torch").cuda.is_available() else "cpu")
            meshes = model.extract_mesh(scene_codes, resolution=mc_resolution)

        mesh = meshes[0]
        mesh_id = str(uuid.uuid4())[:8]

        obj_path = self.output_dir / f"{mesh_id}.obj"
        mesh.export(str(obj_path))

        import trimesh
        tm = trimesh.load(str(obj_path))
        glb_path = self.output_dir / f"{mesh_id}.glb"
        tm.export(str(glb_path), file_type="glb")

        return MeshGenResult(
            success=True,
            mesh_path=str(glb_path),
            mesh_format="glb",
            provider="local",
            model="triposr",
            vertex_count=len(tm.vertices) if hasattr(tm, "vertices") else 0,
            face_count=len(tm.faces) if hasattr(tm, "faces") else 0,
            metadata={"mc_resolution": mc_resolution, "obj_path": str(obj_path)},
        )

    # ── 生成历史 ──────────────────────────────────────────────────────

    def get_generated_meshes(self, limit: int = 20) -> list[dict]:
        meshes = []
        for ext in ["*.glb", "*.obj", "*.stl"]:
            for p in self.output_dir.glob(ext):
                meshes.append({
                    "id": p.stem,
                    "path": str(p),
                    "filename": p.name,
                    "format": p.suffix[1:],
                    "size_kb": round(p.stat().st_size / 1024, 1),
                    "created": p.stat().st_mtime,
                })
        meshes.sort(key=lambda x: x["created"], reverse=True)
        return meshes[:limit]
