"""网格修复 — 孔洞填补、法线修正、流形修复、退化面移除"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

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
