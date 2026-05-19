"""统一布尔运算层 — subtract / union / intersect

所有 CSG 操作优先使用 manifold3d，失败后依次回退到 trimesh 的
manifold、blender、默认引擎。提供单次和批量操作接口。

Usage::

    from moldgen.core.boolean_ops import boolean_subtract, boolean_union, batch_subtract
    result = boolean_subtract(outer_shell, cavity)
"""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
import trimesh

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_manifold(mesh: trimesh.Trimesh):
    """Convert trimesh.Trimesh → manifold3d.Manifold (lazy import)."""
    import manifold3d

    return manifold3d.Manifold(
        manifold3d.Mesh(
            vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
            tri_verts=np.asarray(mesh.faces, dtype=np.uint32),
        )
    )


def _from_manifold(manifold_out) -> trimesh.Trimesh:
    """Convert manifold3d mesh output → trimesh.Trimesh."""
    return trimesh.Trimesh(
        vertices=np.asarray(manifold_out.vert_properties[:, :3]),
        faces=np.asarray(manifold_out.tri_verts),
        process=True,
    )


def _trimesh_engine_loop(
    op_name: str,
    op_func,
    mesh_a: trimesh.Trimesh,
    mesh_b: trimesh.Trimesh,
    min_faces: int,
) -> trimesh.Trimesh | None:
    """Try a trimesh boolean through multiple engine backends."""
    for engine in ("manifold", "blender", None):
        try:
            kw = {"engine": engine} if engine else {}
            result = op_func(mesh_a, mesh_b, **kw)
            if result is not None and len(result.faces) > min_faces:
                logger.debug(
                    "trimesh %s (%s) OK: %d faces",
                    op_name, engine or "default", len(result.faces),
                )
                return result
        except Exception as e:
            logger.debug("trimesh %s (%s) failed: %s", op_name, engine, e)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def boolean_subtract(
    mesh_a: trimesh.Trimesh,
    mesh_b: trimesh.Trimesh,
    *,
    min_faces: int = 4,
) -> trimesh.Trimesh | None:
    """mesh_a − mesh_b, returns *None* if all engines fail."""
    try:
        diff = _to_manifold(mesh_a) - _to_manifold(mesh_b)
        result = _from_manifold(diff.to_mesh())
        if len(result.faces) > min_faces:
            logger.debug("manifold3d subtract OK: %d faces", len(result.faces))
            return result
    except Exception as e:
        logger.debug("manifold3d subtract failed: %s", e)

    result = _trimesh_engine_loop(
        "subtract",
        lambda a, b, **kw: a.difference(b, **kw),
        mesh_a, mesh_b, min_faces,
    )
    if result is not None:
        return result

    logger.warning("Boolean subtract failed for all engines")
    return None


def boolean_union(
    mesh_a: trimesh.Trimesh,
    mesh_b: trimesh.Trimesh,
    *,
    min_faces: int = 4,
    require_watertight: bool = False,
) -> trimesh.Trimesh | None:
    """mesh_a ∪ mesh_b, returns *None* if all engines fail."""
    try:
        uni = _to_manifold(mesh_a) + _to_manifold(mesh_b)
        result = _from_manifold(uni.to_mesh())
        if len(result.faces) > min_faces:
            if not require_watertight or result.is_watertight:
                logger.debug("manifold3d union OK: %d faces", len(result.faces))
                return result
    except Exception as e:
        logger.debug("manifold3d union failed: %s", e)

    def _union(a, b, **kw):
        r = a.union(b, **kw)
        if require_watertight and r is not None and not r.is_watertight:
            return None
        return r

    result = _trimesh_engine_loop("union", _union, mesh_a, mesh_b, min_faces)
    if result is not None:
        return result

    logger.warning("Boolean union failed for all engines")
    return None


def boolean_intersect(
    mesh_a: trimesh.Trimesh,
    mesh_b: trimesh.Trimesh,
    *,
    min_faces: int = 4,
) -> trimesh.Trimesh | None:
    """mesh_a ∩ mesh_b, returns *None* if all engines fail."""
    try:
        inter = _to_manifold(mesh_a) ^ _to_manifold(mesh_b)
        result = _from_manifold(inter.to_mesh())
        if len(result.faces) > min_faces:
            logger.debug("manifold3d intersect OK: %d faces", len(result.faces))
            return result
    except Exception as e:
        logger.debug("manifold3d intersect failed: %s", e)

    result = _trimesh_engine_loop(
        "intersect",
        lambda a, b, **kw: a.intersection(b, **kw),
        mesh_a, mesh_b, min_faces,
    )
    if result is not None:
        return result

    logger.warning("Boolean intersect failed for all engines")
    return None


def batch_subtract(
    base: trimesh.Trimesh,
    cutters: Sequence[trimesh.Trimesh],
    *,
    min_faces: int = 4,
) -> trimesh.Trimesh | None:
    """Batch boolean subtraction: concat cutters → single subtract, sequential fallback.

    Returns the carved mesh, or *None* if no cutters could be applied.
    """
    if not cutters:
        return base

    combined = trimesh.util.concatenate(list(cutters))
    result = boolean_subtract(base, combined, min_faces=min_faces)
    if result is not None:
        return result

    logger.debug("Batch subtract failed, trying sequential (%d cutters)", len(cutters))
    work = base
    cut_count = 0
    for cutter in cutters:
        r = boolean_subtract(work, cutter, min_faces=min_faces)
        if r is not None:
            work = r
            cut_count += 1
    if cut_count > 0:
        logger.debug("Sequential subtract: %d/%d succeeded", cut_count, len(cutters))
        return work
    return None
