"""GPU 计算层 — CUDA 检测与统一抽象

Modules:
- device: GPU hardware detection
- sdf: Signed Distance Field computation (GPU + CPU)
- ray_cast: Ray-mesh intersection (GPU + CPU)
- flow_kernel: Darcy flow pressure solver (GPU + CPU)
- fallback: Unified CPU-only convenience functions
"""

from moldgen.gpu.device import GPUDevice, GPUInfo

__all__ = ["GPUDevice", "GPUInfo"]


def __getattr__(name: str):
    _lazy = {
        "compute_sdf_grid": "moldgen.gpu.sdf",
        "sample_sdf_at_points": "moldgen.gpu.sdf",
        "cast_rays": "moldgen.gpu.ray_cast",
        "visibility_analysis": "moldgen.gpu.ray_cast",
        "solve_pressure_field": "moldgen.gpu.flow_kernel",
        "compute_fill_animation": "moldgen.gpu.flow_kernel",
        "compute_sdf": "moldgen.gpu.fallback",
        "query_sdf": "moldgen.gpu.fallback",
        "raycast": "moldgen.gpu.fallback",
        "check_visibility": "moldgen.gpu.fallback",
        "solve_flow": "moldgen.gpu.fallback",
        "voxelize_mesh": "moldgen.gpu.fallback",
        "compute_thickness_field": "moldgen.gpu.fallback",
    }
    if name in _lazy:
        import importlib
        mod = importlib.import_module(_lazy[name])
        return getattr(mod, name)
    raise AttributeError(f"module 'moldgen.gpu' has no attribute {name!r}")
