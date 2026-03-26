"""SDF (Signed Distance Field) 计算

提供 GPU (CuPy) 加速版本和 CPU (NumPy/SciPy) 降级版本。
用于模具壁偏移、碰撞检测、距离查询等核心操作。
"""

from __future__ import annotations

import logging
import numpy as np

logger = logging.getLogger(__name__)


def compute_sdf_grid(
    mesh,
    resolution: int = 64,
    padding: float = 5.0,
    use_gpu: bool | None = None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Compute a signed distance field on a regular 3D grid.

    Returns (sdf_values, grid_points, grid_info).
    sdf_values: shape (res, res, res) — negative inside, positive outside.
    grid_points: shape (res**3, 3) — flat array of xyz coords.
    grid_info: dict with origin, pitch, resolution.
    """
    if use_gpu is None:
        from moldgen.gpu.device import GPUDevice
        use_gpu = GPUDevice().info.cupy_available

    bounds = mesh.bounds
    lo = bounds[0] - padding
    hi = bounds[1] + padding
    pitch = (hi - lo) / resolution

    axes = [np.linspace(lo[i], hi[i], resolution) for i in range(3)]
    gx, gy, gz = np.meshgrid(*axes, indexing="ij")
    pts = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])

    grid_info = {
        "origin": lo.tolist(),
        "pitch": pitch.tolist(),
        "resolution": [resolution] * 3,
    }

    if use_gpu:
        try:
            sdf = _sdf_gpu(mesh, pts, resolution)
            return sdf, pts, grid_info
        except Exception as e:
            logger.warning("GPU SDF failed, falling back to CPU: %s", e)

    sdf = _sdf_cpu(mesh, pts, resolution)
    return sdf, pts, grid_info


def _sdf_cpu(mesh, pts: np.ndarray, resolution: int) -> np.ndarray:
    """CPU SDF via trimesh proximity query."""
    import trimesh

    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError("Expected trimesh.Trimesh")

    closest, distances, _ = trimesh.proximity.closest_point(mesh, pts)

    sign = np.ones(len(pts), dtype=np.float32)
    if mesh.is_watertight:
        inside = mesh.contains(pts)
        sign[inside] = -1.0

    sdf_flat = sign * distances.astype(np.float32)
    return sdf_flat.reshape(resolution, resolution, resolution)


def _sdf_gpu(mesh, pts: np.ndarray, resolution: int) -> np.ndarray:
    """GPU-accelerated SDF using CuPy + batch nearest-point."""
    import cupy as cp
    import trimesh

    verts = cp.asarray(mesh.vertices, dtype=cp.float32)
    faces = cp.asarray(mesh.faces, dtype=cp.int32)
    pts_g = cp.asarray(pts, dtype=cp.float32)

    batch = 4096
    dists_all = cp.empty(len(pts), dtype=cp.float32)
    for start in range(0, len(pts), batch):
        end = min(start + batch, len(pts))
        chunk = pts_g[start:end]
        tri_centers = (verts[faces[:, 0]] + verts[faces[:, 1]] + verts[faces[:, 2]]) / 3
        diff = chunk[:, None, :] - tri_centers[None, :, :]
        d2 = (diff ** 2).sum(axis=2)
        dists_all[start:end] = cp.sqrt(d2.min(axis=1))

    sdf_flat = cp.asnumpy(dists_all)

    if mesh.is_watertight:
        inside = mesh.contains(pts)
        sdf_flat[inside] *= -1

    return sdf_flat.reshape(resolution, resolution, resolution)


def sample_sdf_at_points(mesh, points: np.ndarray) -> np.ndarray:
    """Query SDF at arbitrary points (CPU only, always available)."""
    import trimesh

    closest, distances, _ = trimesh.proximity.closest_point(mesh, points)
    sign = np.ones(len(points), dtype=np.float32)
    if mesh.is_watertight:
        inside = mesh.contains(points)
        sign[inside] = -1.0
    return sign * distances.astype(np.float32)
