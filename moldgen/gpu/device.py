"""GPU 设备检测与管理"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    available: bool = False
    device_name: str = "N/A"
    vram_total_mb: int = 0
    vram_free_mb: int = 0
    vram_used_mb: int = 0
    compute_capability: tuple[int, int] = (0, 0)
    cuda_version: str = "N/A"
    driver_version: str = "N/A"
    numba_cuda: bool = False
    cupy_available: bool = False


class GPUDevice:
    """GPU 设备单例 — 检测并缓存 GPU 信息"""

    _instance: GPUDevice | None = None
    _info: GPUInfo | None = None

    def __new__(cls) -> GPUDevice:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def info(self) -> GPUInfo:
        if self._info is None:
            self._info = self._detect()
        return self._info

    @property
    def has_cuda(self) -> bool:
        return self.info.available

    def refresh(self) -> GPUInfo:
        self._info = self._detect()
        return self._info

    def _detect(self) -> GPUInfo:
        info = GPUInfo()

        try:
            import subprocess

            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total,memory.free,memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                if len(parts) >= 5:
                    info.device_name = parts[0]
                    info.driver_version = parts[1]
                    info.vram_total_mb = int(float(parts[2]))
                    info.vram_free_mb = int(float(parts[3]))
                    info.vram_used_mb = int(float(parts[4]))
                    info.available = True
        except Exception as e:
            logger.debug("nvidia-smi detection failed: %s", e)

        # CUDA version
        try:
            import subprocess

            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            pass

        # Numba CUDA
        try:
            from numba import cuda as numba_cuda

            if numba_cuda.is_available():
                info.numba_cuda = True
                device = numba_cuda.get_current_device()
                cc = device.compute_capability
                info.compute_capability = (cc[0], cc[1])
                logger.info(
                    "Numba CUDA available: %s (CC %d.%d)",
                    info.device_name,
                    cc[0],
                    cc[1],
                )
        except Exception as e:
            logger.debug("Numba CUDA not available: %s", e)

        # CuPy
        try:
            import cupy  # noqa: F401

            info.cupy_available = True
            info.cuda_version = cupy.cuda.runtime.runtimeGetVersion()
            logger.info("CuPy available, CUDA runtime: %s", info.cuda_version)
        except Exception as e:
            logger.debug("CuPy not available: %s", e)

        if info.available:
            logger.info(
                "GPU: %s | VRAM: %d/%d MB | CC: %s",
                info.device_name,
                info.vram_used_mb,
                info.vram_total_mb,
                f"{info.compute_capability[0]}.{info.compute_capability[1]}",
            )
        else:
            logger.warning("No CUDA GPU detected — CPU fallback mode")

        return info

    def get_memory_usage(self) -> dict:
        info = self.refresh()
        return {
            "total_mb": info.vram_total_mb,
            "used_mb": info.vram_used_mb,
            "free_mb": info.vram_free_mb,
            "utilization": (
                round(info.vram_used_mb / info.vram_total_mb, 3)
                if info.vram_total_mb > 0
                else 0
            ),
        }
