"""光线投射 (Ray Casting)

提供 GPU (CuPy) 和 CPU (trimesh) 两种实现。
用于可见性分析、脱模方向评估、undercut 检测。
"""

from __future__ import annotations

import logging
import numpy as np

logger = logging.getLogger(__name__)


def cast_rays(
    mesh,
    origins: np.ndarray,
    directions: np.ndarray,
    use_gpu: bool | None = None,
) -> dict:
    """Cast rays against a mesh.

    Returns dict with:
        hit: bool array (N,)
        locations: float array (N, 3) — hit point coords (NaN if no hit)
        face_indices: int array (N,) — hit face index (-1 if no hit)
        distances: float array (N,) — ray distance (inf if no hit)
    """
    if use_gpu is None:
        from moldgen.gpu.device import GPUDevice
        use_gpu = GPUDevice().info.cupy_available

    if use_gpu:
        try:
            return _raycast_gpu(mesh, origins, directions)
        except Exception as e:
            logger.warning("GPU raycast failed, falling back to CPU: %s", e)

    return _raycast_cpu(mesh, origins, directions)


def _raycast_cpu(mesh, origins: np.ndarray, directions: np.ndarray) -> dict:
    """CPU ray casting via trimesh ray module."""
    import trimesh

    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError("Expected trimesh.Trimesh")

    ray = mesh.ray
    n = len(origins)

    locations, index_ray, index_tri = ray.intersects_location(
        ray_origins=origins,
        ray_directions=directions,
        multiple_hits=False,
    )

    hit = np.zeros(n, dtype=bool)
    locs = np.full((n, 3), np.nan, dtype=np.float64)
    face_ids = np.full(n, -1, dtype=np.int64)
    dists = np.full(n, np.inf, dtype=np.float64)

    if len(index_ray) > 0:
        hit[index_ray] = True
        locs[index_ray] = locations
        face_ids[index_ray] = index_tri
        dists[index_ray] = np.linalg.norm(locations - origins[index_ray], axis=1)

    return {
        "hit": hit,
        "locations": locs,
        "face_indices": face_ids,
        "distances": dists,
    }


def _raycast_gpu(mesh, origins: np.ndarray, directions: np.ndarray) -> dict:
    """GPU-accelerated ray-triangle intersection (Möller–Trumbore)."""
    import cupy as cp

    verts = cp.asarray(mesh.vertices, dtype=cp.float32)
    faces = cp.asarray(mesh.faces, dtype=cp.int32)
    orig_g = cp.asarray(origins, dtype=cp.float32)
    dirs_g = cp.asarray(directions, dtype=cp.float32)

    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    e1 = v1 - v0
    e2 = v2 - v0

    n = len(origins)
    min_t = cp.full(n, cp.inf, dtype=cp.float32)
    hit_face = cp.full(n, -1, dtype=cp.int32)
    eps = 1e-7

    batch = 2048
    for start in range(0, n, batch):
        end = min(start + batch, n)
        o = orig_g[start:end]
        d = dirs_g[start:end]
        h = cp.cross(d[:, None, :], e2[None, :, :])
        a = (e1[None, :, :] * h).sum(axis=2)
        valid = cp.abs(a) > eps
        f = 1.0 / cp.where(valid, a, 1.0)
        s = o[:, None, :] - v0[None, :, :]
        u = f * (s * h).sum(axis=2)
        q = cp.cross(s, e1[None, :, :])
        v = f * (d[:, None, :] * q).sum(axis=2)
        t = f * (e2[None, :, :] * q).sum(axis=2)

        hit_mask = valid & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > eps)
        t_masked = cp.where(hit_mask, t, cp.inf)
        best_face = t_masked.argmin(axis=1)
        best_t = t_masked[cp.arange(end - start), best_face]
        closer = best_t < min_t[start:end]
        min_t[start:end] = cp.where(closer, best_t, min_t[start:end])
        hit_face[start:end] = cp.where(closer, best_face, hit_face[start:end])

    min_t_np = cp.asnumpy(min_t)
    hit_face_np = cp.asnumpy(hit_face)
    hit = np.isfinite(min_t_np)
    locs = np.full((n, 3), np.nan, dtype=np.float64)
    locs[hit] = origins[hit] + directions[hit] * min_t_np[hit, None]

    return {
        "hit": hit,
        "locations": locs,
        "face_indices": hit_face_np.astype(np.int64),
        "distances": min_t_np.astype(np.float64),
    }


def visibility_analysis(
    mesh,
    direction: np.ndarray,
    n_samples: int = 1000,
    use_gpu: bool | None = None,
) -> dict:
    """Analyze mesh visibility from a given direction.

    Returns fraction of surface visible, undercut faces, etc.
    """
    import trimesh

    direction = np.asarray(direction, dtype=np.float64)
    direction = direction / np.linalg.norm(direction)

    normals = mesh.face_normals
    dots = normals @ direction

    visible_mask = dots > 0
    undercut_mask = dots < -0.05

    centers = mesh.triangles_center
    areas = mesh.area_faces

    total_area = areas.sum()
    visible_area = areas[visible_mask].sum()
    undercut_area = areas[undercut_mask].sum()

    return {
        "direction": direction.tolist(),
        "visible_fraction": float(visible_area / max(total_area, 1e-10)),
        "undercut_fraction": float(undercut_area / max(total_area, 1e-10)),
        "n_visible_faces": int(visible_mask.sum()),
        "n_undercut_faces": int(undercut_mask.sum()),
        "total_faces": len(normals),
    }
