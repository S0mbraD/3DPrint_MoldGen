"""CPU 降级实现 — 统一接口，自动检测 GPU 可用性并选择合适的后端

所有模块 (sdf, ray_cast, flow_kernel) 内部已自带 CPU/GPU 双路径。
本模块提供便捷的统一入口 + 纯 CPU 保底算法。
"""

from __future__ import annotations

import logging
import numpy as np

logger = logging.getLogger(__name__)


def ensure_numpy(arr) -> np.ndarray:
    """Convert CuPy array to NumPy if needed."""
    if hasattr(arr, "get"):
        return arr.get()
    return np.asarray(arr)


# ── SDF shortcuts ─────────────────────────────────────────────────────

def compute_sdf(mesh, resolution: int = 64, padding: float = 5.0):
    from moldgen.gpu.sdf import compute_sdf_grid
    return compute_sdf_grid(mesh, resolution=resolution, padding=padding)


def query_sdf(mesh, points: np.ndarray) -> np.ndarray:
    from moldgen.gpu.sdf import sample_sdf_at_points
    return sample_sdf_at_points(mesh, points)


# ── Ray casting shortcuts ─────────────────────────────────────────────

def raycast(mesh, origins: np.ndarray, directions: np.ndarray):
    from moldgen.gpu.ray_cast import cast_rays
    return cast_rays(mesh, origins, directions)


def check_visibility(mesh, direction: np.ndarray, n_samples: int = 1000):
    from moldgen.gpu.ray_cast import visibility_analysis
    return visibility_analysis(mesh, direction, n_samples=n_samples)


# ── Flow solver shortcuts ─────────────────────────────────────────────

def solve_flow(sdf_grid, gates, vents, grid_info, viscosity=5.0, permeability=1e-10):
    from moldgen.gpu.flow_kernel import solve_pressure_field
    return solve_pressure_field(
        sdf_grid, gates, vents, grid_info,
        viscosity=viscosity, permeability=permeability,
    )


# ── Pure-CPU mesh utilities (no GPU dependency) ──────────────────────

def voxelize_mesh(mesh, pitch: float = 1.0) -> np.ndarray:
    """Voxelize a trimesh mesh at the given pitch (mm). Returns bool array."""
    try:
        vox = mesh.voxelized(pitch)
        return vox.matrix
    except Exception:
        bounds = mesh.bounds
        lo, hi = bounds[0], bounds[1]
        shape = np.ceil((hi - lo) / pitch).astype(int)
        shape = np.clip(shape, 1, 256)
        grid = np.zeros(tuple(shape), dtype=bool)

        pts = []
        for i in range(shape[0]):
            for j in range(shape[1]):
                for k in range(shape[2]):
                    pts.append(lo + np.array([i, j, k]) * pitch)
        pts = np.array(pts)

        if mesh.is_watertight:
            inside = mesh.contains(pts)
            idx = 0
            for i in range(shape[0]):
                for j in range(shape[1]):
                    for k in range(shape[2]):
                        grid[i, j, k] = inside[idx]
                        idx += 1
        return grid


def compute_thickness_field(mesh, n_samples: int = 1000) -> np.ndarray:
    """Estimate local thickness by shooting opposing rays from surface samples."""
    import trimesh

    pts, face_idx = trimesh.sample.sample_surface(mesh, n_samples)
    normals = mesh.face_normals[face_idx]

    result_in = raycast(mesh, pts + normals * 0.01, -normals)
    result_out = raycast(mesh, pts - normals * 0.01, normals)

    t_in = np.where(result_in["hit"], result_in["distances"], 0)
    t_out = np.where(result_out["hit"], result_out["distances"], 0)
    thickness = t_in + t_out

    return thickness
