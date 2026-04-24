"""分型线/分型面生成 — 基于脱模方向的模型分割 + Undercut 检测 + 曲面分型
===========================================================================

v5 核心变更:
  1. UndercutAnalyzer — 射线投射 undercut 检测、深度量化、严重度分级
  2. 高度场分型面 (heightfield) — 贴合模型轮廓的非平面分型面
  3. 投影拉伸分型面 (projected) — 沿分型线径向拉伸的曲面分型面
  4. 侧抽方向推荐 (side-pull) — 基于 undercut 区域法线聚类
  5. Undercut 热力图导出 — per-face depth 数据用于 3D 可视化
  6. 分型面支持 "flat" / "heightfield" / "projected" / "auto" 模式
  7. auto 模式根据 undercut 严重度和分型线共面性智能选择
"""

from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field

import numpy as np
import trimesh

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


# ═══════════════════════ Data Structures ═════════════════════════════

@dataclass
class PartingConfig:
    side_angle_threshold: float = 5.0
    smooth_iterations: int = 5
    smooth_lambda: float = 0.5
    extend_margin: float = 5.0
    sdf_resolution: int = 128
    min_loop_edges: int = 3
    surface_type: str = "auto"        # "flat" | "heightfield" | "projected" | "auto"
    heightfield_resolution: int = 40  # grid cells per axis for heightfield
    heightfield_smooth: int = 3       # Laplacian smoothing passes
    undercut_threshold: float = 1.0   # depth (mm) below which undercut is ignored
    projected_radial_steps: int = 12  # radial extension steps for projected surface
    side_pull_n_candidates: int = 6   # candidate side-pull directions to evaluate


@dataclass
class PartingLine:
    vertices: np.ndarray
    edges: list[tuple[int, int]]
    is_closed: bool = True
    length: float = 0.0

    def to_dict(self) -> dict:
        return {
            "vertex_count": len(self.vertices),
            "edge_count": len(self.edges),
            "is_closed": bool(self.is_closed),
            "length": round(float(self.length), 2),
        }


@dataclass
class SidePullDirection:
    """A recommended side-pull direction to resolve undercuts."""
    direction: np.ndarray
    n_resolved: int = 0       # faces resolved by this side-pull
    coverage: float = 0.0     # fraction of undercut faces resolved
    angle_from_primary: float = 0.0  # degrees from primary pull

    def to_dict(self) -> dict:
        return {
            "direction": [round(float(v), 4) for v in self.direction],
            "n_resolved": self.n_resolved,
            "coverage": round(self.coverage, 3),
            "angle_from_primary": round(self.angle_from_primary, 1),
        }


@dataclass
class UndercutInfo:
    """Per-direction undercut analysis."""
    n_undercut_faces: int = 0
    total_faces: int = 0
    undercut_ratio: float = 0.0       # fraction of faces with undercut
    max_depth: float = 0.0            # deepest undercut (mm)
    mean_depth: float = 0.0
    total_volume: float = 0.0         # estimated undercut volume (mm³)
    severity: str = "none"            # "none" | "mild" | "moderate" | "severe"
    face_depths: np.ndarray = field(  # per-face depth (0 for non-undercut)
        default_factory=lambda: np.array([], dtype=np.float64),
    )
    side_pulls: list[SidePullDirection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_undercut_faces": self.n_undercut_faces,
            "total_faces": self.total_faces,
            "undercut_ratio": round(self.undercut_ratio, 4),
            "max_depth": round(self.max_depth, 2),
            "mean_depth": round(self.mean_depth, 2),
            "total_volume": round(self.total_volume, 1),
            "severity": self.severity,
            "side_pulls": [sp.to_dict() for sp in self.side_pulls],
        }


@dataclass
class PartingSurface:
    mesh: MeshData
    normal: np.ndarray
    bounds: np.ndarray
    surface_type: str = "flat"

    def to_dict(self) -> dict:
        return {
            "face_count": self.mesh.face_count,
            "normal": self.normal.tolist(),
            "bounds_min": self.bounds[0].tolist(),
            "bounds_max": self.bounds[1].tolist(),
            "surface_type": self.surface_type,
        }


@dataclass
class PartingResult:
    direction: np.ndarray
    parting_lines: list[PartingLine]
    parting_surface: PartingSurface | None = None
    upper_faces: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=int),
    )
    lower_faces: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=int),
    )
    n_upper: int = 0
    n_lower: int = 0
    undercut: UndercutInfo = field(default_factory=UndercutInfo)
    surface_type_used: str = "flat"

    def to_dict(self) -> dict:
        return {
            "direction": self.direction.tolist(),
            "parting_lines": [pl.to_dict() for pl in self.parting_lines],
            "parting_surface": (
                self.parting_surface.to_dict()
                if self.parting_surface else None
            ),
            "n_upper_faces": int(self.n_upper),
            "n_lower_faces": int(self.n_lower),
            "undercut": self.undercut.to_dict(),
            "surface_type_used": self.surface_type_used,
        }


# ═══════════════════════ Undercut Analyzer ═══════════════════════════

class UndercutAnalyzer:
    """Ray-cast based undercut detection for a given pull direction.

    For each face whose normal opposes the pull direction, a ray is shot
    along +direction from the face centroid.  If the ray re-enters the
    model, that face is *shadowed* — it cannot be de-molded without
    obstruction.  The penetration depth is the distance between exit and
    re-entry points.
    """

    def analyze(
        self, tm: trimesh.Trimesh, direction: np.ndarray,
        threshold: float = 1.0,
    ) -> UndercutInfo:
        direction = direction / (np.linalg.norm(direction) + 1e-12)
        normals = np.asarray(tm.face_normals, dtype=np.float64)
        dot = normals @ direction
        n_faces = len(tm.faces)

        face_areas = np.asarray(tm.area_faces, dtype=np.float64)
        centroids = np.asarray(tm.triangles_center, dtype=np.float64)

        # Faces pointing away from pull direction are candidates
        candidate_mask = dot < -0.01
        candidate_idx = np.where(candidate_mask)[0]

        if len(candidate_idx) == 0:
            return UndercutInfo(total_faces=n_faces, severity="none")

        # Offset origins slightly along direction to avoid self-intersection
        origins = centroids[candidate_idx] + direction * 0.05
        dirs = np.tile(direction, (len(candidate_idx), 1))

        face_depths = np.zeros(n_faces, dtype=np.float64)

        try:
            hits, ray_idx, tri_idx = tm.ray.intersects_location(
                origins, dirs, multiple_hits=True,
            )
        except Exception:
            return UndercutInfo(total_faces=n_faces, severity="none")

        if len(hits) == 0:
            return UndercutInfo(total_faces=n_faces, severity="none")

        # For each candidate face, check if any hit is on a DIFFERENT face
        # (self-hits are on the same face or immediate neighbours)
        for ci, c_face in enumerate(candidate_idx):
            mask = ray_idx == ci
            if not np.any(mask):
                continue
            hit_pts = hits[mask]
            hit_tris = tri_idx[mask]

            # Filter out hits on the originating face itself
            other_mask = hit_tris != c_face
            if not np.any(other_mask):
                continue

            dists = np.linalg.norm(
                hit_pts[other_mask] - centroids[c_face], axis=1,
            )
            # Closest re-entry distance = undercut depth
            min_dist = float(dists.min())
            if min_dist > threshold:
                face_depths[c_face] = min_dist

        undercut_mask = face_depths > 0
        n_uc = int(np.sum(undercut_mask))

        if n_uc == 0:
            return UndercutInfo(
                total_faces=n_faces, severity="none",
                face_depths=face_depths,
            )

        max_d = float(face_depths.max())
        mean_d = float(face_depths[undercut_mask].mean())
        vol = float(np.sum(face_depths[undercut_mask] * face_areas[undercut_mask]))
        ratio = n_uc / max(n_faces, 1)

        if ratio < 0.02 and max_d < 3.0:
            severity = "mild"
        elif ratio < 0.10 and max_d < 8.0:
            severity = "moderate"
        else:
            severity = "severe"

        return UndercutInfo(
            n_undercut_faces=n_uc,
            total_faces=n_faces,
            undercut_ratio=ratio,
            max_depth=max_d,
            mean_depth=mean_d,
            total_volume=vol,
            severity=severity,
            face_depths=face_depths,
        )

    def recommend_side_pulls(
        self, tm: trimesh.Trimesh, direction: np.ndarray,
        undercut_info: UndercutInfo,
        n_candidates: int = 6,
    ) -> list[SidePullDirection]:
        """Suggest side-pull directions by clustering undercut face normals.

        Groups the normals of undercut faces, then for each cluster mean
        direction, evaluates how many undercut faces it would resolve
        (i.e. faces whose normal dots positively with the candidate).
        """
        if undercut_info.n_undercut_faces == 0:
            return []

        direction = direction / (np.linalg.norm(direction) + 1e-12)
        normals = np.asarray(tm.face_normals, dtype=np.float64)
        uc_mask = undercut_info.face_depths > 0
        uc_idx = np.where(uc_mask)[0]
        uc_normals = normals[uc_idx]

        # Generate candidate directions: cluster undercut normals via k-means-like
        # approach on the unit sphere.  For simplicity we use a deterministic
        # strategy: take the mean + principal component directions of uc normals,
        # plus cardinal directions perpendicular to primary pull.
        candidates: list[np.ndarray] = []

        # Mean of undercut normals (negated = the direction to pull them out)
        mean_n = uc_normals.mean(axis=0)
        norm = np.linalg.norm(mean_n)
        if norm > 1e-6:
            candidates.append(-mean_n / norm)

        # SVD principal directions of undercut normals
        try:
            centered = uc_normals - uc_normals.mean(axis=0)
            _, _, vh = np.linalg.svd(centered, full_matrices=False)
            for row in vh[:min(3, len(vh))]:
                row_n = row / (np.linalg.norm(row) + 1e-12)
                candidates.append(row_n)
                candidates.append(-row_n)
        except Exception:
            pass

        # Cardinal directions perpendicular to primary pull
        arb = np.array([1, 0, 0]) if abs(direction[0]) < 0.9 else np.array([0, 1, 0])
        u_ax = np.cross(direction, arb)
        u_ax /= (np.linalg.norm(u_ax) + 1e-12)
        v_ax = np.cross(direction, u_ax)
        v_ax /= (np.linalg.norm(v_ax) + 1e-12)
        for ax in [u_ax, -u_ax, v_ax, -v_ax]:
            candidates.append(ax)

        # Deduplicate and filter (must differ from primary by >30 degrees)
        unique: list[np.ndarray] = []
        for c in candidates:
            angle = np.degrees(np.arccos(np.clip(abs(c @ direction), 0, 1)))
            if angle < 30:
                continue
            is_dup = False
            for u in unique:
                if abs(c @ u) > 0.95:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(c)

        # Evaluate each candidate direction.  A side-pull "resolves" an
        # undercut face if either:
        #   (a) the face normal dots positively with the candidate (face visible), or
        #   (b) the original shadow (ray along primary direction) would be cleared
        #       by pulling along the candidate (the angle between the face's
        #       obstruction direction and the candidate is large enough).
        results: list[SidePullDirection] = []
        for cand in unique[:n_candidates * 2]:
            resolved = 0
            for fi in uc_idx:
                fn = normals[fi]
                if fn @ cand > 0.01:
                    resolved += 1
                    continue
                # Heuristic: if pulling along candidate has significant
                # component perpendicular to the primary obstruction, it
                # may allow the piece to slide out.  Check if the angle
                # between -fn (the obstruction axis) and cand > 45 degrees.
                obstruction_dir = -fn / (np.linalg.norm(fn) + 1e-12)
                cos_angle = abs(obstruction_dir @ cand)
                if cos_angle < 0.707:  # > ~45 degrees
                    resolved += 1
            if resolved == 0:
                continue
            angle = float(np.degrees(np.arccos(
                np.clip(abs(cand @ direction), 0, 1),
            )))
            results.append(SidePullDirection(
                direction=cand,
                n_resolved=resolved,
                coverage=resolved / max(len(uc_idx), 1),
                angle_from_primary=angle,
            ))

        results.sort(key=lambda sp: sp.coverage, reverse=True)
        return results[:n_candidates]


class PartingGenerator:
    """分型面生成器 v4 — 支持 undercut 检测 + 高度场分型面"""

    def __init__(self, config: PartingConfig | None = None):
        self.config = config or PartingConfig()

    def generate(
        self, mesh: MeshData, direction: np.ndarray,
    ) -> PartingResult:
        direction = np.asarray(direction, dtype=np.float64)
        direction = direction / np.linalg.norm(direction)

        logger.info(
            "Generating parting for [%.2f, %.2f, %.2f]", *direction,
        )
        t0 = _time.perf_counter()

        PARTING_MAX_FACES = 1_500_000
        from moldgen.core.orientation import _auto_decimate
        analysis_mesh, decimated = _auto_decimate(mesh, PARTING_MAX_FACES)
        if decimated:
            logger.info(
                "Decimated to %d faces for parting", analysis_mesh.face_count,
            )

        tm = analysis_mesh.to_trimesh()
        normals = np.asarray(tm.face_normals, dtype=np.float64)
        dot = normals @ direction

        # Face classification
        threshold = np.cos(
            np.radians(90 - self.config.side_angle_threshold),
        )
        upper_mask_strict = dot > threshold
        lower_mask_strict = dot < -threshold
        upper_mask_sign = dot > 0
        lower_mask_sign = dot < 0

        upper_faces = np.where(upper_mask_sign)[0]
        lower_faces = np.where(lower_mask_sign)[0]

        # ── Parting edge detection ──
        parting_edges = self._find_parting_edges_fast(
            tm, upper_mask_strict, lower_mask_strict,
        )
        logger.info("Strict threshold: %d parting edges", len(parting_edges))

        if len(parting_edges) < 3:
            parting_edges = self._find_parting_edges_sign_change(tm, dot)
            logger.info("Sign-change fallback: %d parting edges", len(parting_edges))

        parting_lines = self._build_loops(tm, parting_edges)
        logger.info("Built %d parting line loops", len(parting_lines))

        for pl in parting_lines:
            if self.config.smooth_iterations > 0:
                pl.vertices = self._smooth_loop_vectorized(
                    pl.vertices,
                    self.config.smooth_iterations,
                    self.config.smooth_lambda,
                )

        # ── Undercut analysis ──
        ua = UndercutAnalyzer()
        undercut = ua.analyze(
            tm, direction, self.config.undercut_threshold,
        )
        logger.info(
            "Undercut: %d/%d faces (%.1f%%), depth max=%.1fmm, severity=%s",
            undercut.n_undercut_faces, undercut.total_faces,
            undercut.undercut_ratio * 100,
            undercut.max_depth, undercut.severity,
        )

        # ── Side-pull recommendations ──
        if undercut.severity != "none":
            undercut.side_pulls = ua.recommend_side_pulls(
                tm, direction, undercut,
                self.config.side_pull_n_candidates,
            )
            if undercut.side_pulls:
                best_sp = undercut.side_pulls[0]
                logger.info(
                    "Best side-pull: [%.2f,%.2f,%.2f] resolves %d faces (%.0f%%)",
                    *best_sp.direction, best_sp.n_resolved,
                    best_sp.coverage * 100,
                )

        # ── Decide surface type ──
        surf_type = self.config.surface_type
        if surf_type == "auto":
            nonplanar = (
                parting_lines
                and self._parting_line_is_nonplanar(parting_lines[0], direction)
            )
            has_undercut = undercut.severity in ("moderate", "severe")
            if nonplanar and has_undercut:
                surf_type = "projected"
            elif nonplanar or has_undercut:
                surf_type = "heightfield"
            else:
                surf_type = "flat"
            logger.info("Auto surface type: %s", surf_type)

        # ── Build parting surface ──
        if surf_type == "projected" and parting_lines:
            parting_surface = self._build_projected_surface(
                tm, direction, parting_lines,
            )
            if parting_surface is None:
                parting_surface = self._build_heightfield_surface(
                    tm, direction, parting_lines,
                )
        elif surf_type == "heightfield" and parting_lines:
            parting_surface = self._build_heightfield_surface(
                tm, direction, parting_lines,
            )
        else:
            parting_surface = self._build_parting_surface(
                tm, direction, parting_lines,
            )

        if parting_surface is not None:
            parting_surface.surface_type = surf_type

        elapsed = _time.perf_counter() - t0
        logger.info(
            "Parting complete: %d lines, surface=%s (%s), "
            "undercut=%s, %.1fs",
            len(parting_lines),
            "yes" if parting_surface else "no",
            surf_type, undercut.severity, elapsed,
        )

        return PartingResult(
            direction=direction,
            parting_lines=parting_lines,
            parting_surface=parting_surface,
            upper_faces=upper_faces,
            lower_faces=lower_faces,
            n_upper=int(len(upper_faces)),
            n_lower=int(len(lower_faces)),
            undercut=undercut,
            surface_type_used=surf_type,
        )

    # ───────────── Edge detection strategies ──────────────────

    def _find_parting_edges_sign_change(
        self, tm: trimesh.Trimesh, dot: np.ndarray,
    ) -> list[tuple[int, int]]:
        """Find edges where adjacent faces have opposite dot-product sign
        with the direction vector.  This is the most robust method and
        works for any curved mesh — there will always be a sign transition
        around the "equator" perpendicular to the direction.
        """
        try:
            face_adj = tm.face_adjacency
            edge_verts = tm.face_adjacency_edges
            f0 = face_adj[:, 0]
            f1 = face_adj[:, 1]
            cross = (dot[f0] > 0) != (dot[f1] > 0)
            return [
                (int(e[0]), int(e[1]))
                for e in edge_verts[cross]
            ]
        except Exception:
            return self._find_parting_edges_sign_fallback(tm, dot)

    def _find_parting_edges_sign_fallback(
        self, tm: trimesh.Trimesh, dot: np.ndarray,
    ) -> list[tuple[int, int]]:
        """Python-loop fallback for non-manifold meshes."""
        edges_to_faces: dict[tuple[int, int], list[int]] = {}
        for fi, face in enumerate(tm.faces):
            for k in range(3):
                a, b = int(face[k]), int(face[(k + 1) % 3])
                e = (min(a, b), max(a, b))
                edges_to_faces.setdefault(e, []).append(fi)

        parting: list[tuple[int, int]] = []
        for edge, fids in edges_to_faces.items():
            if len(fids) != 2:
                continue
            if (dot[fids[0]] > 0) != (dot[fids[1]] > 0):
                parting.append(edge)
        return parting

    def _find_parting_edges_fast(
        self, tm: trimesh.Trimesh,
        upper_mask: np.ndarray, lower_mask: np.ndarray,
    ) -> list[tuple[int, int]]:
        """Vectorized parting edge detection (strict threshold)."""
        try:
            face_adj = tm.face_adjacency
            edge_verts = tm.face_adjacency_edges
            f0, f1 = face_adj[:, 0], face_adj[:, 1]
            cross = (
                (upper_mask[f0] & lower_mask[f1])
                | (lower_mask[f0] & upper_mask[f1])
            )
            return [
                (int(e[0]), int(e[1]))
                for e in edge_verts[cross]
            ]
        except Exception:
            return self._find_parting_edges_fallback(
                tm, upper_mask, lower_mask,
            )

    def _find_parting_edges_fallback(
        self, tm: trimesh.Trimesh,
        upper_mask: np.ndarray, lower_mask: np.ndarray,
    ) -> list[tuple[int, int]]:
        edges_to_faces: dict[tuple[int, int], list[int]] = {}
        for fi, face in enumerate(tm.faces):
            for k in range(3):
                a, b = int(face[k]), int(face[(k + 1) % 3])
                e = (min(a, b), max(a, b))
                edges_to_faces.setdefault(e, []).append(fi)
        parting: list[tuple[int, int]] = []
        for edge, fids in edges_to_faces.items():
            if len(fids) != 2:
                continue
            f0, f1 = fids
            if (upper_mask[f0] and lower_mask[f1]) or (
                lower_mask[f0] and upper_mask[f1]
            ):
                parting.append(edge)
        return parting

    # ───────────── Loop building ──────────────────────────────

    def _build_loops(
        self, tm: trimesh.Trimesh,
        parting_edges: list[tuple[int, int]],
    ) -> list[PartingLine]:
        if not parting_edges:
            return []

        adj: dict[int, list[int]] = {}
        for v0, v1 in parting_edges:
            adj.setdefault(v0, []).append(v1)
            adj.setdefault(v1, []).append(v0)

        visited_edges: set[tuple[int, int]] = set()
        loops: list[PartingLine] = []

        for start_edge in parting_edges:
            e_key = tuple(sorted(start_edge))
            if e_key in visited_edges:
                continue

            loop_verts = [start_edge[0], start_edge[1]]
            visited_edges.add(e_key)
            current = start_edge[1]
            prev = start_edge[0]

            for _ in range(len(parting_edges) + 1):
                neighbors = adj.get(current, [])
                next_v = None
                for n in neighbors:
                    ek = tuple(sorted((current, n)))
                    if ek not in visited_edges and n != prev:
                        next_v = n
                        break
                if next_v is None:
                    break
                visited_edges.add(tuple(sorted((current, next_v))))
                if next_v == loop_verts[0]:
                    break
                loop_verts.append(next_v)
                prev = current
                current = next_v

            if len(loop_verts) < self.config.min_loop_edges:
                continue

            verts = tm.vertices[loop_verts]
            is_closed = (
                current == loop_verts[0]
                or (
                    len(loop_verts) > 2
                    and np.linalg.norm(verts[0] - verts[-1]) < 1e-4
                )
            )
            edges = [
                (loop_verts[i], loop_verts[(i + 1) % len(loop_verts)])
                for i in range(len(loop_verts))
            ]
            diffs = np.diff(verts, axis=0)
            length = float(np.sum(np.linalg.norm(diffs, axis=1)))
            if is_closed:
                length += float(np.linalg.norm(verts[0] - verts[-1]))

            loops.append(PartingLine(
                vertices=verts, edges=edges,
                is_closed=is_closed, length=length,
            ))

        loops.sort(key=lambda lp: lp.length, reverse=True)
        return loops

    # ───────────── Smoothing ──────────────────────────────────

    def _smooth_loop_vectorized(
        self, vertices: np.ndarray, iterations: int, lam: float,
    ) -> np.ndarray:
        verts = vertices.copy()
        if len(verts) < 3:
            return verts
        for _ in range(iterations):
            prev_v = np.roll(verts, 1, axis=0)
            next_v = np.roll(verts, -1, axis=0)
            laplacian = 0.5 * (prev_v + next_v) - verts
            verts = verts + lam * laplacian
        return verts

    # ───────────── Parting surface ────────────────────────────

    def _build_parting_surface(
        self, tm: trimesh.Trimesh, direction: np.ndarray,
        parting_lines: list[PartingLine],
    ) -> PartingSurface | None:
        """Build a planar parting surface.  Uses parting line center if
        available, otherwise model centroid (guarantees output).
        """
        if parting_lines:
            main_line = parting_lines[0]
            line_center = main_line.vertices.mean(axis=0)
            heights = main_line.vertices @ direction
            plane_height = float(np.mean(heights))
        else:
            line_center = np.asarray(tm.centroid, dtype=np.float64)
            plane_height = float(line_center @ direction)

        plane_origin = line_center - (
            line_center @ direction - plane_height
        ) * direction

        bounds = tm.bounds
        margin = self.config.extend_margin

        up = direction
        arb = (
            np.array([1, 0, 0])
            if abs(up[0]) < 0.9
            else np.array([0, 1, 0])
        )
        u = np.cross(up, arb)
        u /= np.linalg.norm(u)
        v = np.cross(up, u)
        v /= np.linalg.norm(v)

        extents = bounds[1] - bounds[0]
        size_u = float(np.dot(extents, np.abs(u))) + 2 * margin
        size_v = float(np.dot(extents, np.abs(v))) + 2 * margin

        n_grid = 20
        us = np.linspace(-size_u / 2, size_u / 2, n_grid)
        vs = np.linspace(-size_v / 2, size_v / 2, n_grid)
        grid_u, grid_v = np.meshgrid(us, vs)
        grid_pts = (
            plane_origin[np.newaxis, np.newaxis, :]
            + grid_u[:, :, np.newaxis] * u[np.newaxis, np.newaxis, :]
            + grid_v[:, :, np.newaxis] * v[np.newaxis, np.newaxis, :]
        )

        vertices = grid_pts.reshape(-1, 3)
        faces = []
        for i in range(n_grid - 1):
            for j in range(n_grid - 1):
                idx = i * n_grid + j
                faces.append([idx, idx + 1, idx + n_grid])
                faces.append([idx + 1, idx + n_grid + 1, idx + n_grid])

        faces_arr = np.array(faces, dtype=np.int64)
        surf_tm = trimesh.Trimesh(
            vertices=vertices, faces=faces_arr, process=False,
        )
        surf_data = MeshData.from_trimesh(surf_tm)

        return PartingSurface(
            mesh=surf_data,
            normal=direction.copy(),
            bounds=np.array([vertices.min(axis=0), vertices.max(axis=0)]),
            surface_type="flat",
        )

    # ───────────── Heightfield parting surface ────────────────

    def _parting_line_is_nonplanar(
        self, pl: PartingLine, direction: np.ndarray,
        tolerance: float = 2.0,
    ) -> bool:
        """Return True if the parting line deviates more than *tolerance*
        mm from a single plane perpendicular to *direction*."""
        if len(pl.vertices) < 4:
            return False
        heights = pl.vertices @ direction
        spread = float(heights.max() - heights.min())
        return spread > tolerance

    def _build_heightfield_surface(
        self, tm: trimesh.Trimesh, direction: np.ndarray,
        parting_lines: list[PartingLine],
    ) -> PartingSurface | None:
        """Build a parting surface that follows the model silhouette.

        For each point on a u-v grid perpendicular to *direction*, a ray
        is cast in ±direction.  The surface height is set to the model
        boundary height at that point, producing a surface that hugs the
        model contour and avoids undercuts.
        """
        c = self.config
        up = direction.copy()

        arb = np.array([1, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1, 0])
        u_ax = np.cross(up, arb)
        u_ax /= np.linalg.norm(u_ax)
        v_ax = np.cross(up, u_ax)
        v_ax /= np.linalg.norm(v_ax)

        bounds = tm.bounds
        extents = bounds[1] - bounds[0]
        center = np.asarray(tm.centroid, dtype=np.float64)
        margin = c.extend_margin

        size_u = float(np.dot(extents, np.abs(u_ax))) + 2 * margin
        size_v = float(np.dot(extents, np.abs(v_ax))) + 2 * margin

        n = c.heightfield_resolution
        us = np.linspace(-size_u / 2, size_u / 2, n)
        vs = np.linspace(-size_v / 2, size_v / 2, n)
        grid_u, grid_v = np.meshgrid(us, vs)

        # Default height: average parting line height or centroid
        if parting_lines:
            default_h = float(np.mean(parting_lines[0].vertices @ up))
        else:
            default_h = float(center @ up)

        # Flat base points on the parting plane
        base_pts = (
            center[np.newaxis, np.newaxis, :]
            + grid_u[:, :, np.newaxis] * u_ax[np.newaxis, np.newaxis, :]
            + grid_v[:, :, np.newaxis] * v_ax[np.newaxis, np.newaxis, :]
        )
        # Project onto the default parting plane
        for i in range(n):
            for j in range(n):
                pt = base_pts[i, j]
                h = float(pt @ up)
                base_pts[i, j] = pt + (default_h - h) * up

        height_map = np.full((n, n), default_h, dtype=np.float64)

        # Ray cast downward (+direction) and upward (-direction) from high/low
        h_max = float((tm.vertices @ up).max()) + 5.0
        h_min = float((tm.vertices @ up).min()) - 5.0

        flat_pts = base_pts.reshape(-1, 3)
        n_pts = len(flat_pts)

        # Rays from above looking down
        origins_down = flat_pts - up * (default_h - h_max)
        dirs_down = np.tile(-up, (n_pts, 1))

        # Rays from below looking up
        origins_up = flat_pts - up * (default_h - h_min)
        dirs_up = np.tile(up, (n_pts, 1))

        try:
            # Find where model surface is when looking down
            locs_d, ray_d, _ = tm.ray.intersects_location(
                origins_down, dirs_down, multiple_hits=True,
            )
            # Find where model surface is when looking up
            locs_u, ray_u, _ = tm.ray.intersects_location(
                origins_up, dirs_up, multiple_hits=True,
            )
        except Exception:
            logger.warning("Heightfield ray cast failed, falling back to flat")
            return self._build_parting_surface(tm, direction, parting_lines)

        h_ceil = np.full(n_pts, h_max, dtype=np.float64)
        h_floor = np.full(n_pts, h_min, dtype=np.float64)

        if len(locs_d) > 0:
            h_d = locs_d @ up
            # Use np.minimum.at for scatter-min (vectorized)
            np.minimum.at(h_ceil, ray_d, h_d)

        if len(locs_u) > 0:
            h_u = locs_u @ up
            np.maximum.at(h_floor, ray_u, h_u)

        # Parting surface height = midpoint between floor and ceiling
        midpoints = (h_ceil + h_floor) / 2.0

        # For points outside the model shadow, keep default height
        outside = (h_ceil >= h_max - 1.0) & (h_floor <= h_min + 1.0)
        midpoints[outside] = default_h

        height_map = midpoints.reshape(n, n)

        # Boundary constraint: blend edges to default_h for clean mold cuts
        blend_width = max(2, n // 8)
        for k in range(blend_width):
            alpha = k / blend_width
            height_map[k, :] = height_map[k, :] * alpha + default_h * (1 - alpha)
            height_map[n - 1 - k, :] = height_map[n - 1 - k, :] * alpha + default_h * (1 - alpha)
            height_map[:, k] = height_map[:, k] * alpha + default_h * (1 - alpha)
            height_map[:, n - 1 - k] = height_map[:, n - 1 - k] * alpha + default_h * (1 - alpha)

        # Laplacian smoothing on the height map
        for _ in range(c.heightfield_smooth):
            padded = np.pad(height_map, 1, mode="edge")
            height_map = (
                padded[:-2, 1:-1] + padded[2:, 1:-1]
                + padded[1:-1, :-2] + padded[1:-1, 2:]
            ) / 4.0

        # Build mesh from height map (vectorized)
        jj, ii = np.meshgrid(np.arange(n), np.arange(n))
        h_flat = height_map.ravel()
        vertices = (
            center[np.newaxis, :]
            + us[jj.ravel()][:, np.newaxis] * u_ax[np.newaxis, :]
            + vs[ii.ravel()][:, np.newaxis] * v_ax[np.newaxis, :]
            + (h_flat - float(center @ up))[:, np.newaxis] * up[np.newaxis, :]
        )

        # Build faces (vectorized)
        row = np.arange(n - 1)
        col = np.arange(n - 1)
        rr, cc = np.meshgrid(row, col, indexing="ij")
        idx = (rr * n + cc).ravel()
        tri_a = np.column_stack([idx, idx + 1, idx + n])
        tri_b = np.column_stack([idx + 1, idx + n + 1, idx + n])
        faces_arr = np.vstack([tri_a, tri_b]).astype(np.int64)

        surf_tm = trimesh.Trimesh(
            vertices=vertices, faces=faces_arr, process=False,
        )

        logger.info(
            "Heightfield surface: %d×%d grid, height range [%.1f, %.1f]mm",
            n, n, float(height_map.min()), float(height_map.max()),
        )

        return PartingSurface(
            mesh=MeshData.from_trimesh(surf_tm),
            normal=direction.copy(),
            bounds=np.array([vertices.min(axis=0), vertices.max(axis=0)]),
            surface_type="heightfield",
        )

    # ───────────── Projected parting surface ─────────────────

    def _build_projected_surface(
        self, tm: trimesh.Trimesh, direction: np.ndarray,
        parting_lines: list[PartingLine],
    ) -> PartingSurface | None:
        """Build a parting surface by radially extending the parting line outward.

        The surface is formed by connecting the parting line vertices to
        outer boundary points via radial fan triangles.  The height of
        each outer point matches the nearest parting line vertex height,
        producing a surface that follows the model contour.
        """
        if not parting_lines:
            return None

        main_line = parting_lines[0]
        verts = main_line.vertices.copy()
        n_pl = len(verts)
        if n_pl < 3:
            return None

        c = self.config
        up = direction / (np.linalg.norm(direction) + 1e-12)
        center = verts.mean(axis=0)
        margin = c.extend_margin

        bounds = tm.bounds
        extents = bounds[1] - bounds[0]
        max_extent = float(np.linalg.norm(extents)) / 2.0 + margin

        # For each parting line vertex, compute a radial outward direction
        # (projected onto the plane perpendicular to `direction`)
        radials = verts - center
        # Project out the direction component
        radials = radials - np.outer(radials @ up, up)
        radial_norms = np.linalg.norm(radials, axis=1, keepdims=True)
        radial_norms = np.maximum(radial_norms, 1e-6)
        radials = radials / radial_norms

        n_steps = c.projected_radial_steps
        step_size = max_extent / max(n_steps, 1)

        all_verts = [verts.copy()]  # ring 0 = parting line

        # Outer rings gradually blend toward the default parting height
        default_h = float(np.mean(verts @ up))
        pl_heights = verts @ up

        for s in range(1, n_steps + 1):
            blend = s / n_steps  # 0→1 from parting line to outer boundary
            offset = radials * (step_size * s)
            ring = verts + offset
            # Blend heights toward flat default as we move outward
            ring_h = ring @ up
            target_h = pl_heights * (1 - blend) + default_h * blend
            ring = ring + np.outer(target_h - ring_h, up)
            all_verts.append(ring)

        all_verts_arr = np.vstack(all_verts)  # shape: ((n_steps+1)*n_pl, 3)
        n_rings = n_steps + 1

        faces_list: list[list[int]] = []
        for r in range(n_rings - 1):
            for i in range(n_pl):
                i_next = (i + 1) % n_pl
                v00 = r * n_pl + i
                v01 = r * n_pl + i_next
                v10 = (r + 1) * n_pl + i
                v11 = (r + 1) * n_pl + i_next
                faces_list.append([v00, v01, v10])
                faces_list.append([v01, v11, v10])

        faces_arr = np.array(faces_list, dtype=np.int64)
        surf_tm = trimesh.Trimesh(
            vertices=all_verts_arr, faces=faces_arr, process=False,
        )

        logger.info(
            "Projected surface: %d rings × %d pts = %d faces",
            n_rings, n_pl, len(faces_arr),
        )

        return PartingSurface(
            mesh=MeshData.from_trimesh(surf_tm),
            normal=direction.copy(),
            bounds=np.array([
                all_verts_arr.min(axis=0),
                all_verts_arr.max(axis=0),
            ]),
            surface_type="projected",
        )

    # ───────────── Undercut heatmap data export ──────────────

    @staticmethod
    def export_undercut_heatmap(
        tm: trimesh.Trimesh, undercut: UndercutInfo,
    ) -> dict:
        """Export per-face undercut depth as vertex-color data for 3D rendering.

        Returns a dict with vertex_positions (Nx3), face_indices (Mx3),
        and face_values (M,) normalized to [0,1] for colormap mapping.
        """
        depths = undercut.face_depths
        if len(depths) == 0 or len(depths) != len(tm.faces):
            return {
                "vertex_positions": [],
                "face_indices": [],
                "face_values": [],
                "max_depth": 0.0,
            }

        max_d = float(depths.max()) if depths.max() > 0 else 1.0
        normalized = depths / max_d

        vertices = tm.vertices.tolist()
        faces = tm.faces.tolist()
        face_values = normalized.tolist()

        return {
            "vertex_positions": vertices,
            "face_indices": faces,
            "face_values": face_values,
            "max_depth": round(max_d, 2),
        }
