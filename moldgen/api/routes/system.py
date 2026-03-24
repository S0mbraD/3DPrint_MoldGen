"""系统状态与 GPU 信息"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from moldgen import __version__
from moldgen.gpu.device import GPUDevice

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/info")
async def system_info():
    gpu = GPUDevice()
    gpu_info = gpu.info
    return {
        "version": __version__,
        "gpu": {
            "available": gpu_info.available,
            "device_name": gpu_info.device_name,
            "vram_total_mb": gpu_info.vram_total_mb,
            "vram_free_mb": gpu_info.vram_free_mb,
            "vram_used_mb": gpu_info.vram_used_mb,
            "compute_capability": f"{gpu_info.compute_capability[0]}.{gpu_info.compute_capability[1]}",
            "cuda_version": str(gpu_info.cuda_version),
            "driver_version": gpu_info.driver_version,
            "numba_cuda": gpu_info.numba_cuda,
            "cupy": gpu_info.cupy_available,
        },
    }


@router.get("/gpu")
async def gpu_status():
    gpu = GPUDevice()
    return gpu.get_memory_usage()


@router.get("/health")
async def health_check():
    return {"status": "ok", "version": __version__}


# ── Connectivity check ─────────────────────────────────────────────────

_AI_ENDPOINTS: dict[str, dict] = {
    "deepseek": {"url": "https://api.deepseek.com/v1/models", "method": "GET"},
    "qwen": {"url": "https://dashscope.aliyuncs.com/compatible-mode/v1/models", "method": "GET"},
    "kimi": {"url": "https://api.moonshot.cn/v1/models", "method": "GET"},
    "wanxiang": {"url": "https://dashscope.aliyuncs.com/compatible-mode/v1/models", "method": "GET"},
    "tripo": {"url": "https://api.tripo3d.ai/v2/openapi/task", "method": "GET"},
}


class ConnectivityRequest(BaseModel):
    service: str
    api_key: str = ""


async def _ping_service(name: str, endpoint: dict, api_key: str, timeout: float = 10.0) -> dict:
    """Ping a single AI service and return connectivity info."""
    url = endpoint["url"]
    method = endpoint.get("method", "GET")
    t0 = time.perf_counter()
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method == "POST":
                resp = await client.post(url, headers=headers, json={})
            else:
                resp = await client.get(url, headers=headers)
            latency_ms = round((time.perf_counter() - t0) * 1000)
            return {
                "service": name,
                "reachable": True,
                "status_code": resp.status_code,
                "authenticated": resp.status_code in (200, 201),
                "latency_ms": latency_ms,
                "error": None,
            }
    except httpx.ConnectError as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000)
        return {
            "service": name,
            "reachable": False,
            "status_code": 0,
            "authenticated": False,
            "latency_ms": latency_ms,
            "error": f"连接失败: {str(exc)[:100]}",
        }
    except httpx.TimeoutException:
        latency_ms = round((time.perf_counter() - t0) * 1000)
        return {
            "service": name,
            "reachable": False,
            "status_code": 0,
            "authenticated": False,
            "latency_ms": latency_ms,
            "error": "连接超时",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000)
        return {
            "service": name,
            "reachable": False,
            "status_code": 0,
            "authenticated": False,
            "latency_ms": latency_ms,
            "error": str(exc)[:120],
        }


@router.post("/connectivity/check")
async def check_single_connectivity(req: ConnectivityRequest):
    """Check connectivity for a single AI service."""
    endpoint = _AI_ENDPOINTS.get(req.service)
    if not endpoint:
        return {"service": req.service, "reachable": False, "error": f"Unknown service: {req.service}"}
    return await _ping_service(req.service, endpoint, req.api_key)


@router.post("/connectivity/check-all")
async def check_all_connectivity(keys: dict[str, str] | None = None):
    """Check connectivity for all AI services in parallel."""
    keys = keys or {}
    tasks = [
        _ping_service(name, endpoint, keys.get(name, ""))
        for name, endpoint in _AI_ENDPOINTS.items()
    ]
    results = await asyncio.gather(*tasks)
    return {"services": results}


class SaveKeysRequest(BaseModel):
    deepseek: str = ""
    qwen: str = ""
    kimi: str = ""
    wanxiang: str = ""
    tripo: str = ""


@router.post("/api-keys/save")
async def save_api_keys(req: SaveKeysRequest):
    """Save API keys to the .env file for persistence across restarts."""
    import os
    from pathlib import Path

    env_path = Path(os.getcwd()) / ".env"

    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    key_map = {
        "MOLDGEN_AI_DEEPSEEK_API_KEY": req.deepseek,
        "MOLDGEN_AI_QWEN_API_KEY": req.qwen,
        "MOLDGEN_AI_KIMI_API_KEY": req.kimi,
        "MOLDGEN_AI_WANXIANG_API_KEY": req.wanxiang,
        "MOLDGEN_AI_TRIPO_API_KEY": req.tripo,
    }

    for env_key, val in key_map.items():
        if val:
            existing[env_key] = val
            os.environ[env_key] = val

    lines = [f"{k}={v}" for k, v in existing.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    saved_count = sum(1 for v in key_map.values() if v)
    logger.info("Saved %d API keys to %s", saved_count, env_path)
    return {"saved": saved_count, "path": str(env_path)}


@router.get("/api-keys/status")
async def api_keys_status():
    """Return which API keys are configured (without revealing values)."""
    from moldgen.config import get_config
    cfg = get_config().ai
    return {
        "deepseek": bool(cfg.deepseek_api_key),
        "qwen": bool(cfg.qwen_api_key),
        "kimi": bool(cfg.kimi_api_key),
        "wanxiang": bool(cfg.wanxiang_api_key),
        "tripo": bool(cfg.tripo_api_key),
    }


@router.get("/topology")
async def service_topology():
    """Return the backend service topology for the UI diagram."""
    gpu = GPUDevice()
    gpu_info = gpu.info

    nodes = [
        {"id": "frontend", "label": "前端 UI", "type": "client", "status": "online"},
        {"id": "backend", "label": "FastAPI 后端", "type": "server", "status": "online",
         "detail": f"v{__version__}"},
        {"id": "gpu", "label": f"GPU ({gpu_info.device_name or 'N/A'})", "type": "hardware",
         "status": "online" if gpu_info.available else "offline",
         "detail": f"{gpu_info.vram_total_mb}MB VRAM" if gpu_info.available else "不可用"},
        {"id": "trimesh", "label": "Trimesh 引擎", "type": "library", "status": "online"},
        {"id": "deepseek", "label": "DeepSeek", "type": "ai_service", "status": "unknown"},
        {"id": "qwen", "label": "通义千问", "type": "ai_service", "status": "unknown"},
        {"id": "kimi", "label": "Kimi", "type": "ai_service", "status": "unknown"},
        {"id": "wanxiang", "label": "通义万相", "type": "ai_service", "status": "unknown"},
        {"id": "tripo", "label": "Tripo3D", "type": "ai_service", "status": "unknown"},
    ]

    edges = [
        {"from": "frontend", "to": "backend", "label": "REST / WebSocket"},
        {"from": "backend", "to": "gpu", "label": "CUDA"},
        {"from": "backend", "to": "trimesh", "label": "网格处理"},
        {"from": "backend", "to": "deepseek", "label": "对话 API"},
        {"from": "backend", "to": "qwen", "label": "对话 API"},
        {"from": "backend", "to": "kimi", "label": "对话 API"},
        {"from": "backend", "to": "wanxiang", "label": "图像生成"},
        {"from": "backend", "to": "tripo", "label": "3D 生成"},
    ]

    return {"nodes": nodes, "edges": edges}
