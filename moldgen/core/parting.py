"""分型线/分型面生成 — 基于脱模方向的模型分割
=============================================

v3 核心变更:
  1. 分型边检测改用 **法线点积符号变化** (dot > 0 vs dot < 0)
     而非严格角度阈值, 保证任何网格都能找到分型边
  2. 新增 _find_parting_edges_sign_change: 相邻面法线与方向点积
     符号不同 → 分型边  (更鲁棒, 适用于所有曲面模型)
  3. 当原始方法找不到分型边时, 自动回退到符号变化法
  4. 分型面生成: 当无分型线时在质心处生成平面分型面 (保证总有输出)
"""

from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field

import numpy as np
import trimesh

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


@dataclass
class PartingConfig:
    side_angle_threshold: float = 5.0
    smooth_iterations: int = 5
    smooth_lambda: float = 0.5
    extend_margin: float = 5.0
    sdf_resolution: int = 128
    min_loop_edges: int = 3


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
class PartingSurface:
    mesh: MeshData
    normal: np.ndarray
    bounds: np.ndarray

    def to_dict(self) -> dict:
        return {
            "face_count": self.mesh.face_count,
            "normal": self.normal.tolist(),
            "bounds_min": self.bounds[0].tolist(),
            "bounds_max": self.bounds[1].tolist(),
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
        }


class PartingGenerator:
    """分型面生成器 v3"""

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

        # Face classification: upper (dot > 0), lower (dot < 0)
        threshold = np.cos(
            np.radians(90 - self.config.side_angle_threshold),
        )
        upper_mask_strict = dot > threshold
        lower_mask_strict = dot < -threshold
        upper_mask_sign = dot > 0
        lower_mask_sign = dot < 0

        upper_faces = np.where(upper_mask_sign)[0]
        lower_faces = np.where(lower_mask_sign)[0]

        # Strategy 1: strict threshold edges
        parting_edges = self._find_parting_edges_fast(
            tm, upper_mask_strict, lower_mask_strict,
        )
        logger.info(
            "Strict threshold: %d parting edges", len(parting_edges),
        )

        # Strategy 2: sign-change edges (more robust, guaranteed for curved)
        if len(parting_edges) < 3:
            parting_edges = self._find_parting_edges_sign_change(tm, dot)
            logger.info(
                "Sign-change fallback: %d parting edges", len(parting_edges),
            )

        parting_lines = self._build_loops(tm, parting_edges)
        logger.info("Built %d parting line loops", len(parting_lines))

        for pl in parting_lines:
            if self.config.smooth_iterations > 0:
                pl.vertices = self._smooth_loop_vectorized(
                    pl.vertices,
                    self.config.smooth_iterations,
                    self.config.smooth_lambda,
                )

        # Build parting surface (guaranteed even without parting lines)
        parting_surface = self._build_parting_surface(
            tm, direction, parting_lines,
        )

        elapsed = _time.perf_counter() - t0
        logger.info(
            "Parting complete: %d lines, surface=%s, %.1fs",
            len(parting_lines),
            "yes" if parting_surface else "no",
            elapsed,
        )

        return PartingResult(
            direction=direction,
            parting_lines=parting_lines,
            parting_surface=parting_surface,
            upper_faces=upper_faces,
            lower_faces=lower_faces,
            n_upper=int(len(upper_faces)),
            n_lower=int(len(lower_faces)),
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
        )
