"""网格修复 — 孔洞填补、法线修正、流形修复、退化面移除

本模块包含两层 API：
- **MeshRepair**：高层 API，操作 MeshData 对象，生成质量报告 (API 路由使用)
- **repair_trimesh / clean_trimesh / ...**：低层 API，直接操作 trimesh.Trimesh
  对象，供 mold_builder / gating / insert_generator 内部调用
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np
import trimesh

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """网格质量检查报告"""

    is_watertight: bool = False
    is_manifold: bool = False
    face_count: int = 0
    vertex_count: int = 0
    holes: int = 0
    non_manifold_edges: int = 0
    degenerate_faces: int = 0
    duplicate_faces: int = 0
    self_intersections: int = 0
    min_edge_length: float = 0.0
    max_edge_length: float = 0.0
    mean_edge_length: float = 0.0
    max_aspect_ratio: float = 0.0
    volume: float | None = None
    surface_area: float = 0.0
    bounds_min: list[float] = field(default_factory=list)
    bounds_max: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "is_watertight": self.is_watertight,
            "is_manifold": self.is_manifold,
            "face_count": self.face_count,
            "vertex_count": self.vertex_count,
            "holes": self.holes,
            "non_manifold_edges": self.non_manifold_edges,
            "degenerate_faces": self.degenerate_faces,
            "duplicate_faces": self.duplicate_faces,
            "min_edge_length": round(self.min_edge_length, 4),
            "max_edge_length": round(self.max_edge_length, 4),
            "mean_edge_length": round(self.mean_edge_length, 4),
            "max_aspect_ratio": round(self.max_aspect_ratio, 2),
            "volume": round(self.volume, 4) if self.volume is not None else None,
            "surface_area": round(self.surface_area, 4),
            "bounds_min": self.bounds_min,
            "bounds_max": self.bounds_max,
        }


@dataclass
class RepairResult:
    """修复操作结果"""

    success: bool
    mesh: MeshData
    actions: list[str] = field(default_factory=list)
    before: QualityReport | None = None
    after: QualityReport | None = None


class MeshRepair:
    """网格质量检查与自动修复"""

    @staticmethod
    def check_quality(mesh: MeshData) -> QualityReport:
        tm = mesh.to_trimesh()
        report = QualityReport()

        report.face_count = len(tm.faces)
        report.vertex_count = len(tm.vertices)
        report.is_watertight = bool(tm.is_watertight)
        report.surface_area = float(tm.area)
        report.bounds_min = tm.bounds[0].tolist()
        report.bounds_max = tm.bounds[1].tolist()

        if tm.is_watertight:
            report.volume = float(tm.volume)

        # Holes: count boundary loops
        try:
            outlines = tm.outline()
            if hasattr(outlines, "entities"):
                report.holes = len(outlines.entities)
            else:
                report.holes = 0
        except Exception:
            report.holes = 0 if tm.is_watertight else -1  # -1 = could not determine

        # Edge statistics
        edge_lengths = tm.edges_unique_length
        if len(edge_lengths) > 0:
            report.min_edge_length = float(np.min(edge_lengths))
            report.max_edge_length = float(np.max(edge_lengths))
            report.mean_edge_length = float(np.mean(edge_lengths))

        # Degenerate faces (zero area)
        face_areas = tm.area_faces
        report.degenerate_faces = int(np.sum(face_areas < 1e-10))

        # Duplicate faces
        sorted_faces = np.sort(tm.faces, axis=1)
        _, counts = np.unique(sorted_faces, axis=0, return_counts=True)
        report.duplicate_faces = int(np.sum(counts > 1))

        # Aspect ratio: longest edge / shortest edge per face
        try:
            triangles = tm.triangles
            edges_per_face = np.array([
                np.linalg.norm(triangles[:, 1] - triangles[:, 0], axis=1),
                np.linalg.norm(triangles[:, 2] - triangles[:, 1], axis=1),
                np.linalg.norm(triangles[:, 0] - triangles[:, 2], axis=1),
            ]).T  # (M, 3)
            mins = edges_per_face.min(axis=1)
            maxs = edges_per_face.max(axis=1)
            valid = mins > 1e-12
            if np.any(valid):
                ratios = maxs[valid] / mins[valid]
                report.max_aspect_ratio = float(np.max(ratios))
        except Exception:
            pass

        # Non-manifold edges
        try:
            face_adj = tm.face_adjacency
            edge_face_count = np.bincount(face_adj.ravel(), minlength=len(tm.faces))
            report.is_manifold = bool(np.all(edge_face_count <= 3))
        except Exception:
            pass

        logger.info(
            "Quality: %d faces, %d verts, watertight=%s, holes=%d, degenerate=%d",
            report.face_count, report.vertex_count, report.is_watertight,
            report.holes, report.degenerate_faces,
        )
        return report

    @staticmethod
    def repair(mesh: MeshData, auto_fix: bool = True) -> RepairResult:
        before = MeshRepair.check_quality(mesh)
        tm = mesh.to_trimesh()
        actions: list[str] = []

        if not auto_fix:
            return RepairResult(success=True, mesh=mesh, actions=[], before=before, after=before)

        # 1. Remove degenerate faces
        degenerate = tm.area_faces < 1e-10
        if np.any(degenerate):
            mask = ~degenerate
            tm.update_faces(mask)
            actions.append(f"removed {int(np.sum(degenerate))} degenerate faces")

        # 2. Remove duplicate faces
        sorted_faces = np.sort(tm.faces, axis=1)
        _, unique_idx = np.unique(sorted_faces, axis=0, return_index=True)
        if len(unique_idx) < len(tm.faces):
            removed = len(tm.faces) - len(unique_idx)
            mask = np.zeros(len(tm.faces), dtype=bool)
            mask[unique_idx] = True
            tm.update_faces(mask)
            actions.append(f"removed {removed} duplicate faces")

        # 3. Remove unreferenced vertices
        tm.remove_unreferenced_vertices()

        # 4. Fix normals / winding
        if not tm.is_winding_consistent:
            tm.fix_normals()
            actions.append("fixed face winding and normals")

        # 5. Merge close vertices
        tm.merge_vertices()
        actions.append("merged close vertices")

        # 6. Fill holes
        if not tm.is_watertight:
            try:
                tm.fill_holes()
                if tm.is_watertight:
                    actions.append("filled holes")
                else:
                    actions.append("attempted hole filling (some holes may remain)")
            except Exception as e:
                actions.append(f"hole filling failed: {e}")

        # 7. Process to clean up
        tm.process(validate=True)

        result_mesh = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result_mesh.unit = mesh.unit
        after = MeshRepair.check_quality(result_mesh)

        logger.info("Repair complete: %s", ", ".join(actions) if actions else "no changes needed")
        return RepairResult(
            success=True,
            mesh=result_mesh,
            actions=actions,
            before=before,
            after=after,
        )


# =========================================================================
# Low-level trimesh repair primitives
# =========================================================================


def clean_trimesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Lightweight cleanup: remove degenerate faces and unreferenced vertices."""
    try:
        mask = mesh.nondegenerate_faces()
        mesh.update_faces(mask)
    except (AttributeError, Exception):
        pass
    try:
        mesh.remove_unreferenced_vertices()
    except (AttributeError, Exception):
        pass
    return mesh


def compact_vertex_indices(tm: trimesh.Trimesh) -> None:
    """Remap ``faces`` to a dense 0…N-1 range and drop unreferenced vertices.

    ``trimesh.remove_unreferenced_vertices`` may fail to rewrite ``faces``
    in isolated cases, leaving stale indices.  This function always produces
    a compact vertex array.
    """
    if tm is None or len(tm.faces) == 0:
        return
    faces = np.asarray(tm.faces, dtype=np.int64)
    verts = np.asarray(tm.vertices, dtype=np.float64)
    ok = (faces >= 0).all(axis=1) & (faces < len(verts)).all(axis=1)
    if not np.all(ok):
        faces = faces[ok]
        tm.faces = faces
        if len(faces) == 0:
            return
    used = np.unique(faces.ravel())
    if used.size == 0:
        return
    if len(used) == len(verts) and int(used[0]) == 0 and int(used[-1]) == len(verts) - 1:
        return
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    tm.vertices = verts[used]
    tm.faces = remap[faces]
    try:
        tm._cache.clear()
    except Exception:
        pass


def _boundary_edge_count(tm: trimesh.Trimesh) -> int:
    """Count undirected boundary edges (multiplicity == 1)."""
    if tm is None or len(tm.faces) == 0:
        return 0
    fe = trimesh.geometry.faces_to_edges(np.asarray(tm.faces, dtype=np.int64))
    fe = np.sort(fe, axis=1)
    return sum(1 for _, v in Counter(map(tuple, fe)).items() if v == 1)


def dedupe_faces(tm: trimesh.Trimesh) -> None:
    """Remove duplicate triangles sharing the same 3 vertices (any winding).

    If removing extras would *increase* open boundary length, the edit is
    reverted (some coincident triangles are structurally required).
    """
    if tm is None or len(tm.faces) < 2:
        return
    f = np.asarray(tm.faces, dtype=np.int64)
    b0 = _boundary_edge_count(tm)
    groups: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for i in range(len(f)):
        tri = f[i]
        if len(set(int(x) for x in tri)) < 3:
            continue
        key = tuple(sorted(int(x) for x in tri))
        groups[key].append(i)
    drop: set[int] = set()
    for idxs in groups.values():
        if len(idxs) <= 1:
            continue
        drop.update(idxs[1:])
    if not drop:
        return
    keep = np.array([i for i in range(len(f)) if i not in drop], dtype=np.int64)
    trial = f[keep]
    tm.faces = trial
    try:
        tm._cache.clear()
    except Exception:
        pass
    if _boundary_edge_count(tm) > b0:
        tm.faces = f
        try:
            tm._cache.clear()
        except Exception:
            pass


def repair_trimesh(
    tm: trimesh.Trimesh,
    *,
    fill: bool = True,
    aggressive: bool = False,
) -> trimesh.Trimesh:
    """Unified low-level mesh repair for trimesh objects.

    Parameters
    ----------
    fill : bool
        If *True*, call ``trimesh.repair.fill_holes``.  Set to *False*
        when preserving intentional holes (e.g. after carving).
    aggressive : bool
        If *True*, also run ``fix_inversion``, ``dedupe_faces``, and
        ``compact_vertex_indices`` (used by mold_builder for final output).
    """
    if tm is None or len(tm.faces) < 4:
        return tm

    if tm.is_watertight and not aggressive:
        try:
            trimesh.repair.fix_normals(tm, multibody=True)
        except Exception as e:
            logger.debug("repair fix_normals skipped: %s", e)
        return tm

    try:
        tm.merge_vertices(merge_tex=True, merge_norm=True)
    except Exception as e:
        logger.debug("repair merge_vertices: %s", e)

    try:
        mask = tm.nondegenerate_faces()
        if not np.all(mask):
            tm.update_faces(mask)
    except Exception as e:
        logger.debug("repair degenerate removal: %s", e)

    try:
        tm.remove_duplicate_faces()
    except Exception as e:
        logger.debug("repair remove_duplicate_faces: %s", e)

    try:
        tm.remove_unreferenced_vertices()
    except Exception as e:
        logger.debug("repair remove_unreferenced: %s", e)

    try:
        trimesh.repair.fix_normals(tm, multibody=True)
    except Exception as e:
        logger.debug("repair fix_normals: %s", e)

    try:
        trimesh.repair.fix_winding(tm)
    except Exception as e:
        logger.debug("repair fix_winding: %s", e)

    if fill:
        try:
            trimesh.repair.fill_holes(tm)
        except Exception as e:
            logger.debug("repair fill_holes: %s", e)

    if aggressive:
        try:
            trimesh.repair.fix_inversion(tm)
        except Exception as e:
            logger.debug("repair fix_inversion: %s", e)
        try:
            dedupe_faces(tm)
        except Exception as e:
            logger.debug("repair dedupe_faces: %s", e)
        try:
            compact_vertex_indices(tm)
        except Exception as e:
            logger.debug("repair compact_indices: %s", e)

    try:
        trimesh.repair.fix_normals(tm, multibody=True)
    except Exception as e:
        logger.debug("repair final fix_normals: %s", e)

    return tm


def stitch_boundaries(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Attempt to close open boundaries left by face removal."""
    try:
        trimesh.repair.fill_holes(mesh)
    except Exception as e:
        logger.debug("stitch fill_holes: %s", e)
    try:
        trimesh.repair.fix_normals(mesh, multibody=True)
    except Exception as e:
        logger.debug("stitch fix_normals: %s", e)
    try:
        trimesh.repair.fix_winding(mesh)
    except Exception as e:
        logger.debug("stitch fix_winding: %s", e)
    return mesh


def voxel_repair(
    mesh: trimesh.Trimesh,
    pitch: float = 0.0,
) -> trimesh.Trimesh | None:
    """Voxelize a non-watertight mesh and reconstruct via marching cubes.

    Uses morphological close (dilate → fill → erode) to seal gaps, then
    marching cubes to reconstruct a watertight surface.
    """
    try:
        from scipy.ndimage import binary_dilation, binary_erosion, binary_fill_holes
        from skimage.measure import marching_cubes

        bounds = mesh.bounds
        extents = bounds[1] - bounds[0]
        if pitch <= 0:
            pitch = float(min(extents)) / 40.0
            pitch = max(pitch, 0.2)

        vox = mesh.voxelized(pitch)
        matrix = np.pad(vox.matrix, pad_width=2, mode="constant", constant_values=False)

        closed = binary_dilation(matrix, iterations=1)
        closed = binary_fill_holes(closed)
        closed = binary_erosion(closed, iterations=1)

        verts_mc, faces_mc, _, _ = marching_cubes(
            closed.astype(float), level=0.5, spacing=(pitch, pitch, pitch),
        )
        origin = bounds[0] - 4 * pitch
        verts_mc += origin

        result = trimesh.Trimesh(vertices=verts_mc, faces=faces_mc, process=True)
        repair_trimesh(result, fill=False)

        if len(result.faces) > 20000:
            try:
                target = 10000
                reduction = max(0.01, min(1.0 - target / len(result.faces), 0.99))
                result = result.simplify_quadric_decimation(reduction)
                repair_trimesh(result)
            except Exception:
                pass

        if result.is_watertight and len(result.faces) >= 4:
            return result
    except Exception as e:
        logger.warning("Voxel repair failed: %s", e)
    return None
