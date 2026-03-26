"""AI 生成 API — 图像生成、3D模型生成、本地模型管理"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response 模型 ──────────────────────────────────────────

class ImageGenRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    num_images: int = 1
    width: int = 1024
    height: int = 1024
    steps: int | None = None
    cfg_scale: float | None = None
    seed: int | None = None
    provider: str | None = None
    model_id: str | None = None


class MeshGenTextRequest(BaseModel):
    prompt: str
    provider: str | None = None


class MeshGenImageRequest(BaseModel):
    image_path: str
    provider: str | None = None
    model_id: str | None = None
    mc_resolution: int = 256


class PromptOptRequest(BaseModel):
    prompt: str


class ModelDownloadRequest(BaseModel):
    model_id: str


class ProviderSwitchRequest(BaseModel):
    image_provider: str | None = None
    image_local_model: str | None = None
    mesh_provider: str | None = None
    mesh_local_model: str | None = None
    auto_unload_after_gen: bool | None = None


# ── 图像生成 ──────────────────────────────────────────────────────────

@router.post("/image/generate")
async def generate_image(req: ImageGenRequest):
    """生成图像 (云端万相 / 本地 Diffusers)"""
    from moldgen.ai.image_gen import ImageGenerator
    gen = ImageGenerator()
    result = await gen.generate(
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        num_images=req.num_images,
        width=req.width,
        height=req.height,
        steps=req.steps,
        cfg_scale=req.cfg_scale,
        seed=req.seed,
        provider=req.provider,
        model_id=req.model_id,
    )
    return {
        "success": result.success,
        "images": result.images,
        "provider": result.provider,
        "model": result.model,
        "elapsed_seconds": result.elapsed_seconds,
        "prompt_used": result.prompt_used,
        "error": result.error,
    }


@router.get("/image/history")
async def image_history(limit: int = 20):
    """已生成图像历史"""
    from moldgen.ai.image_gen import ImageGenerator
    return {"images": ImageGenerator().get_generated_images(limit)}


# ── 3D 模型生成 ──────────────────────────────────────────────────────

@router.post("/mesh/text-to-3d")
async def text_to_3d(req: MeshGenTextRequest):
    """文字→3D (仅云端 Tripo3D)"""
    from moldgen.ai.model_gen import MeshGenerator
    gen = MeshGenerator()
    result = await gen.text_to_3d(prompt=req.prompt, provider=req.provider)
    return {
        "success": result.success,
        "mesh_path": result.mesh_path,
        "mesh_format": result.mesh_format,
        "provider": result.provider,
        "model": result.model,
        "elapsed_seconds": result.elapsed_seconds,
        "vertex_count": result.vertex_count,
        "face_count": result.face_count,
        "error": result.error,
    }


@router.post("/mesh/image-to-3d")
async def image_to_3d(req: MeshGenImageRequest):
    """单图→3D (云端 Tripo3D / 本地 TripoSR)"""
    from moldgen.ai.model_gen import MeshGenerator
    gen = MeshGenerator()
    result = await gen.image_to_3d(
        image_path=req.image_path,
        provider=req.provider,
        model_id=req.model_id,
        mc_resolution=req.mc_resolution,
    )
    return {
        "success": result.success,
        "mesh_path": result.mesh_path,
        "mesh_format": result.mesh_format,
        "provider": result.provider,
        "model": result.model,
        "elapsed_seconds": result.elapsed_seconds,
        "vertex_count": result.vertex_count,
        "face_count": result.face_count,
        "error": result.error,
        "metadata": result.metadata,
    }


@router.get("/mesh/history")
async def mesh_history(limit: int = 20):
    """已生成 3D 模型历史"""
    from moldgen.ai.model_gen import MeshGenerator
    return {"meshes": MeshGenerator().get_generated_meshes(limit)}


# ── 提示词优化 ────────────────────────────────────────────────────────

@router.post("/prompt/optimize")
async def optimize_prompt(req: PromptOptRequest):
    """优化中文提示词为适合 AI 生成的英文提示词"""
    from moldgen.ai.chat import ChatService
    result = await ChatService().optimize_prompt(req.prompt)
    return {"original": req.prompt, "optimized": result}


# ── 本地模型管理 ──────────────────────────────────────────────────────

@router.get("/local-models")
async def list_local_models(category: str | None = None):
    """列出所有可用本地模型"""
    from moldgen.ai.local_models import LocalModelManager, ModelCategory
    mgr = LocalModelManager()
    cat = ModelCategory(category) if category else None
    models = mgr.list_models(cat)
    recommendation = mgr.recommend_models()
    return {"models": models, "recommendation": recommendation}


@router.get("/local-models/vram")
async def local_model_vram():
    """本地模型 VRAM 使用情况"""
    from moldgen.ai.local_models import LocalModelManager
    return LocalModelManager().get_vram_usage()


@router.post("/local-models/download")
async def download_model(req: ModelDownloadRequest):
    """下载本地模型"""
    from moldgen.ai.local_models import LocalModelManager
    return await LocalModelManager().download_model(req.model_id)


@router.post("/local-models/{model_id}/load")
async def load_model(model_id: str):
    """加载模型到 GPU"""
    from moldgen.ai.local_models import LocalModelManager
    return await LocalModelManager().load_model(model_id)


@router.post("/local-models/{model_id}/unload")
async def unload_model(model_id: str):
    """从 GPU 卸载模型"""
    from moldgen.ai.local_models import LocalModelManager
    return LocalModelManager().unload_model(model_id)


@router.delete("/local-models/{model_id}")
async def delete_model(model_id: str):
    """删除本地模型文件"""
    from moldgen.ai.local_models import LocalModelManager
    return LocalModelManager().delete_model(model_id)


@router.post("/local-models/unload-all")
async def unload_all_models():
    """卸载所有模型"""
    from moldgen.ai.local_models import LocalModelManager
    return LocalModelManager().unload_all()


# ── Provider 切换 ─────────────────────────────────────────────────────

@router.get("/providers")
async def get_providers():
    """获取当前 provider 配置"""
    from moldgen.config import get_config
    cfg = get_config().ai
    return {
        "image_provider": cfg.image_provider,
        "image_local_model": cfg.image_local_model,
        "mesh_provider": cfg.mesh_provider,
        "mesh_local_model": cfg.mesh_local_model,
        "auto_unload_after_gen": cfg.auto_unload_after_gen,
        "cloud_status": {
            "wanxiang": bool(cfg.wanxiang_api_key),
            "tripo3d": bool(cfg.tripo_api_key),
        },
    }


@router.put("/providers")
async def update_providers(req: ProviderSwitchRequest):
    """切换 provider (cloud/local) 和模型"""
    import os
    updates = {}
    if req.image_provider is not None:
        os.environ["MOLDGEN_AI_IMAGE_PROVIDER"] = req.image_provider
        updates["image_provider"] = req.image_provider
    if req.image_local_model is not None:
        os.environ["MOLDGEN_AI_IMAGE_LOCAL_MODEL"] = req.image_local_model
        updates["image_local_model"] = req.image_local_model
    if req.mesh_provider is not None:
        os.environ["MOLDGEN_AI_MESH_PROVIDER"] = req.mesh_provider
        updates["mesh_provider"] = req.mesh_provider
    if req.mesh_local_model is not None:
        os.environ["MOLDGEN_AI_MESH_LOCAL_MODEL"] = req.mesh_local_model
        updates["mesh_local_model"] = req.mesh_local_model
    if req.auto_unload_after_gen is not None:
        os.environ["MOLDGEN_AI_AUTO_UNLOAD_AFTER_GEN"] = str(req.auto_unload_after_gen).lower()
        updates["auto_unload_after_gen"] = req.auto_unload_after_gen

    return {"updated": updates, "message": "Provider 配置已更新（运行时生效，重启后需重新设置）"}
