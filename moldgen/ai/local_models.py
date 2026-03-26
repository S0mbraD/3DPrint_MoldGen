"""本地 AI 模型管理器 — 下载、加载、卸载、VRAM 管理

支持的本地模型:
  图像生成: SDXL, FLUX.1-schnell, SD 1.5
  三维重建: TripoSR, InstantMesh
"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ModelCategory(StrEnum):
    IMAGE_GEN = "image_gen"
    MESH_GEN = "mesh_gen"
    VISION = "vision"
    CHAT = "chat"


class ModelStatus(StrEnum):
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"


@dataclass
class LocalModelInfo:
    """本地模型元数据"""
    model_id: str
    name: str
    category: ModelCategory
    description: str
    vram_required_mb: int
    disk_size_gb: float
    hf_repo: str
    hf_revision: str = "main"
    subfolder: str = ""
    model_class: str = ""
    supports_fp16: bool = True
    supports_bf16: bool = True
    recommended_dtype: str = "float16"
    extra_config: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


# ── 模型注册表 ─────────────────────────────────────────────────────────

AVAILABLE_MODELS: dict[str, LocalModelInfo] = {
    # ── 图像生成 ──────────────────────────────────────────────────────
    "sdxl-base": LocalModelInfo(
        model_id="sdxl-base",
        name="Stable Diffusion XL 1.0",
        category=ModelCategory.IMAGE_GEN,
        description="高质量图像生成，1024x1024，适合医学解剖模型参考图",
        vram_required_mb=6500,
        disk_size_gb=6.9,
        hf_repo="stabilityai/stable-diffusion-xl-base-1.0",
        model_class="StableDiffusionXLPipeline",
        tags=["推荐", "高质量", "1024x1024"],
        extra_config={"default_steps": 30, "default_cfg": 7.5},
    ),
    "flux-schnell": LocalModelInfo(
        model_id="flux-schnell",
        name="FLUX.1-schnell",
        category=ModelCategory.IMAGE_GEN,
        description="极速图像生成（1-4步），12B参数但推理快，效果优秀",
        vram_required_mb=8000,
        disk_size_gb=23.8,
        hf_repo="black-forest-labs/FLUX.1-schnell",
        model_class="FluxPipeline",
        tags=["最快", "高质量"],
        extra_config={"default_steps": 4, "default_cfg": 0.0, "max_sequence_length": 256},
    ),
    "sd15": LocalModelInfo(
        model_id="sd15",
        name="Stable Diffusion 1.5",
        category=ModelCategory.IMAGE_GEN,
        description="轻量级图像生成，512x512，VRAM占用低，适合低显存设备",
        vram_required_mb=4000,
        disk_size_gb=4.3,
        hf_repo="stable-diffusion-v1-5/stable-diffusion-v1-5",
        model_class="StableDiffusionPipeline",
        tags=["轻量", "低显存"],
        extra_config={"default_steps": 30, "default_cfg": 7.5, "default_size": 512},
    ),
    "kolors": LocalModelInfo(
        model_id="kolors",
        name="Kolors (可图)",
        category=ModelCategory.IMAGE_GEN,
        description="快手可图大模型，中文提示词理解极强，1024x1024",
        vram_required_mb=7000,
        disk_size_gb=10.5,
        hf_repo="Kwai-Kolors/Kolors-diffusers",
        model_class="KolorsPipeline",
        tags=["中文优化", "高质量"],
        extra_config={"default_steps": 25, "default_cfg": 5.0},
    ),

    # ── 三维重建 ──────────────────────────────────────────────────────
    "triposr": LocalModelInfo(
        model_id="triposr",
        name="TripoSR",
        category=ModelCategory.MESH_GEN,
        description="单图→3D网格，Stability AI + Tripo 联合开源，速度快质量好",
        vram_required_mb=4000,
        disk_size_gb=1.5,
        hf_repo="stabilityai/TripoSR",
        model_class="TSR",
        tags=["推荐", "快速", "图→3D"],
        extra_config={"chunk_size": 8192, "mc_resolution": 256},
    ),
    "instantmesh": LocalModelInfo(
        model_id="instantmesh",
        name="InstantMesh",
        category=ModelCategory.MESH_GEN,
        description="高质量多视角→3D重建，适合复杂解剖结构",
        vram_required_mb=8000,
        disk_size_gb=5.2,
        hf_repo="TencentARC/InstantMesh",
        model_class="InstantMesh",
        tags=["高质量", "多视角"],
        extra_config={"mc_resolution": 256},
    ),
    "trellis": LocalModelInfo(
        model_id="trellis",
        name="TRELLIS",
        category=ModelCategory.MESH_GEN,
        description="微软 TRELLIS，SOTA 图→3D，结构化隐式表征",
        vram_required_mb=10000,
        disk_size_gb=4.0,
        hf_repo="microsoft/TRELLIS-image-large",
        model_class="TrellisImageTo3DPipeline",
        tags=["SOTA", "高质量"],
        extra_config={"slat_sampler_params": {"steps": 12}},
    ),
}


class LocalModelManager:
    """本地模型管理器 — 单例"""

    _instance: LocalModelManager | None = None

    def __new__(cls) -> LocalModelManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._loaded_models: dict[str, Any] = {}
        self._model_status: dict[str, ModelStatus] = {}
        self._download_progress: dict[str, float] = {}
        self._models_dir: Path | None = None

    @property
    def models_dir(self) -> Path:
        if self._models_dir is None:
            from moldgen.config import get_config
            self._models_dir = get_config().data_dir / "local_models"
            self._models_dir.mkdir(parents=True, exist_ok=True)
        return self._models_dir

    # ── 查询 ──────────────────────────────────────────────────────────

    def list_models(self, category: ModelCategory | None = None) -> list[dict]:
        """列出所有可用模型及其状态"""
        result = []
        for mid, info in AVAILABLE_MODELS.items():
            if category and info.category != category:
                continue
            model_path = self.models_dir / mid
            status = self._model_status.get(mid, ModelStatus.NOT_DOWNLOADED)
            if status == ModelStatus.NOT_DOWNLOADED and model_path.exists():
                status = ModelStatus.DOWNLOADED
                self._model_status[mid] = status
            if mid in self._loaded_models:
                status = ModelStatus.LOADED

            result.append({
                "model_id": mid,
                "name": info.name,
                "category": info.category,
                "description": info.description,
                "vram_required_mb": info.vram_required_mb,
                "disk_size_gb": info.disk_size_gb,
                "status": status,
                "tags": info.tags,
                "hf_repo": info.hf_repo,
                "download_progress": self._download_progress.get(mid, 0.0),
                "is_loaded": mid in self._loaded_models,
            })
        return result

    def get_model_info(self, model_id: str) -> LocalModelInfo | None:
        return AVAILABLE_MODELS.get(model_id)

    def get_loaded_model(self, model_id: str) -> Any | None:
        return self._loaded_models.get(model_id)

    def get_status(self, model_id: str) -> ModelStatus:
        if model_id in self._loaded_models:
            return ModelStatus.LOADED
        if model_id in self._model_status:
            return self._model_status[model_id]
        model_path = self.models_dir / model_id
        if model_path.exists():
            return ModelStatus.DOWNLOADED
        return ModelStatus.NOT_DOWNLOADED

    # ── VRAM 管理 ─────────────────────────────────────────────────────

    def get_vram_usage(self) -> dict:
        """当前本地模型 VRAM 占用估算"""
        total_loaded = 0
        loaded_list = []
        for mid in self._loaded_models:
            info = AVAILABLE_MODELS.get(mid)
            if info:
                total_loaded += info.vram_required_mb
                loaded_list.append({"model_id": mid, "vram_mb": info.vram_required_mb})

        from moldgen.gpu.device import GPUDevice
        gpu = GPUDevice()
        gpu_info = gpu.info
        return {
            "loaded_models": loaded_list,
            "total_loaded_vram_mb": total_loaded,
            "gpu_vram_total_mb": gpu_info.vram_total_mb,
            "gpu_vram_free_mb": gpu_info.vram_free_mb,
            "available_for_models_mb": max(0, gpu_info.vram_free_mb - 1024),
        }

    def can_load(self, model_id: str) -> tuple[bool, str]:
        """检查是否有足够 VRAM 加载指定模型"""
        info = AVAILABLE_MODELS.get(model_id)
        if not info:
            return False, f"Unknown model: {model_id}"
        vram = self.get_vram_usage()
        available = vram["available_for_models_mb"]
        if info.vram_required_mb > available:
            return False, (
                f"VRAM 不足: {info.name} 需要 {info.vram_required_mb}MB, "
                f"可用 {available}MB. 请先卸载其他模型。"
            )
        return True, "OK"

    # ── 下载 ──────────────────────────────────────────────────────────

    async def download_model(self, model_id: str) -> dict:
        """从 HuggingFace 下载模型到本地"""
        info = AVAILABLE_MODELS.get(model_id)
        if not info:
            return {"success": False, "error": f"Unknown model: {model_id}"}

        model_path = self.models_dir / model_id
        if model_path.exists():
            self._model_status[model_id] = ModelStatus.DOWNLOADED
            return {"success": True, "message": "模型已存在", "path": str(model_path)}

        self._model_status[model_id] = ModelStatus.DOWNLOADING
        self._download_progress[model_id] = 0.0

        try:
            import huggingface_hub
            logger.info("Downloading %s from %s ...", info.name, info.hf_repo)

            def progress_callback(progress: float) -> None:
                self._download_progress[model_id] = progress

            huggingface_hub.snapshot_download(
                repo_id=info.hf_repo,
                revision=info.hf_revision,
                local_dir=str(model_path),
                local_dir_use_symlinks=False,
            )

            self._model_status[model_id] = ModelStatus.DOWNLOADED
            self._download_progress[model_id] = 100.0
            logger.info("Downloaded %s to %s", info.name, model_path)
            return {"success": True, "path": str(model_path)}

        except Exception as e:
            self._model_status[model_id] = ModelStatus.ERROR
            logger.error("Download failed for %s: %s", model_id, e)
            return {"success": False, "error": str(e)}

    # ── 加载 / 卸载 ──────────────────────────────────────────────────

    async def load_model(self, model_id: str) -> dict:
        """加载模型到 GPU 显存"""
        info = AVAILABLE_MODELS.get(model_id)
        if not info:
            return {"success": False, "error": f"Unknown model: {model_id}"}

        if model_id in self._loaded_models:
            return {"success": True, "message": "模型已加载"}

        model_path = self.models_dir / model_id
        if not model_path.exists():
            dl = await self.download_model(model_id)
            if not dl["success"]:
                return dl

        can, reason = self.can_load(model_id)
        if not can:
            return {"success": False, "error": reason}

        self._model_status[model_id] = ModelStatus.LOADING
        t0 = time.time()

        try:
            pipeline = await self._create_pipeline(info, model_path)
            self._loaded_models[model_id] = pipeline
            self._model_status[model_id] = ModelStatus.LOADED
            elapsed = round(time.time() - t0, 1)
            logger.info("Loaded %s in %.1fs", info.name, elapsed)
            return {"success": True, "elapsed_seconds": elapsed}

        except Exception as e:
            self._model_status[model_id] = ModelStatus.ERROR
            logger.error("Failed to load %s: %s", model_id, e)
            return {"success": False, "error": str(e)}

    async def _create_pipeline(self, info: LocalModelInfo, model_path: Path) -> Any:
        """根据模型类型创建推理管线"""
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if info.supports_fp16 and device == "cuda" else torch.float32

        if info.category == ModelCategory.IMAGE_GEN:
            return await self._load_image_pipeline(info, model_path, device, dtype)
        elif info.category == ModelCategory.MESH_GEN:
            return await self._load_mesh_pipeline(info, model_path, device, dtype)
        else:
            raise ValueError(f"Unsupported category: {info.category}")

    async def _load_image_pipeline(
        self, info: LocalModelInfo, path: Path, device: str, dtype: Any
    ) -> Any:
        import torch
        from diffusers import (
            DiffusionPipeline,
            StableDiffusionPipeline,
            StableDiffusionXLPipeline,
        )

        cls_map: dict[str, type] = {
            "StableDiffusionPipeline": StableDiffusionPipeline,
            "StableDiffusionXLPipeline": StableDiffusionXLPipeline,
        }

        pipeline_cls = cls_map.get(info.model_class)
        if pipeline_cls:
            pipe = pipeline_cls.from_pretrained(
                str(path), torch_dtype=dtype, use_safetensors=True
            )
        else:
            pipe = DiffusionPipeline.from_pretrained(
                str(path), torch_dtype=dtype, use_safetensors=True
            )

        pipe = pipe.to(device)

        if hasattr(pipe, "enable_model_cpu_offload") and device == "cuda":
            try:
                pipe.enable_model_cpu_offload()
            except Exception:
                pass

        return pipe

    async def _load_mesh_pipeline(
        self, info: LocalModelInfo, path: Path, device: str, dtype: Any
    ) -> Any:
        if info.model_id == "triposr":
            return self._load_triposr(path, device)
        else:
            raise ValueError(f"Mesh pipeline not implemented: {info.model_id}")

    def _load_triposr(self, path: Path, device: str) -> Any:
        import torch
        from tsr.system import TSR

        model = TSR.from_pretrained(
            str(path),
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        model.renderer.set_chunk_size(8192)
        model.to(device)
        return model

    def unload_model(self, model_id: str) -> dict:
        """从 GPU 卸载模型释放显存"""
        if model_id not in self._loaded_models:
            return {"success": False, "error": "模型未加载"}

        import gc
        model = self._loaded_models.pop(model_id)
        del model
        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        self._model_status[model_id] = ModelStatus.DOWNLOADED
        logger.info("Unloaded model: %s", model_id)
        return {"success": True}

    def unload_all(self) -> dict:
        """卸载所有已加载模型"""
        ids = list(self._loaded_models.keys())
        for mid in ids:
            self.unload_model(mid)
        return {"success": True, "unloaded": ids}

    # ── 删除 ──────────────────────────────────────────────────────────

    def delete_model(self, model_id: str) -> dict:
        """删除本地模型文件"""
        if model_id in self._loaded_models:
            self.unload_model(model_id)

        model_path = self.models_dir / model_id
        if model_path.exists():
            shutil.rmtree(model_path)
            self._model_status[model_id] = ModelStatus.NOT_DOWNLOADED
            logger.info("Deleted model files: %s", model_path)
            return {"success": True}
        return {"success": False, "error": "模型文件不存在"}

    # ── 推荐 ──────────────────────────────────────────────────────────

    def recommend_models(self) -> dict:
        """根据当前 GPU 推荐最佳模型组合"""
        from moldgen.gpu.device import GPUDevice
        gpu = GPUDevice()
        vram = gpu.info.vram_total_mb

        if vram >= 12000:
            return {
                "tier": "高端 (≥12GB)",
                "image_gen": "sdxl-base",
                "mesh_gen": "triposr",
                "note": f"GPU: {gpu.info.device_name} ({vram}MB). "
                        f"SDXL + TripoSR 可同时加载。FLUX.1-schnell 也可使用。",
            }
        elif vram >= 8000:
            return {
                "tier": "中端 (8-12GB)",
                "image_gen": "sdxl-base",
                "mesh_gen": "triposr",
                "note": f"GPU: {gpu.info.device_name} ({vram}MB). "
                        f"SDXL + TripoSR 需交替加载，建议用完一个卸载后再加载另一个。",
            }
        elif vram >= 4000:
            return {
                "tier": "入门 (4-8GB)",
                "image_gen": "sd15",
                "mesh_gen": "triposr",
                "note": f"GPU: {gpu.info.device_name} ({vram}MB). "
                        f"推荐 SD 1.5 + TripoSR。SDXL 可能超出显存。",
            }
        else:
            return {
                "tier": "无 GPU / 低显存",
                "image_gen": None,
                "mesh_gen": None,
                "note": "显存不足以运行本地模型。请使用云端 API (通义万相 + Tripo3D)。",
            }
