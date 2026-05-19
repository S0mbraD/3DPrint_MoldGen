"""浇注系统设计 — 浇口位置优化、流道布局、排气孔"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import trimesh

from moldgen.core.boolean_ops import boolean_subtract as _boolean_subtract
from moldgen.core.material import MaterialProperties
from moldgen.core.mesh_data import MeshData
from moldgen.core.mold_builder import MoldResult

logger = logging.getLogger(__name__)


def _aabb_overlap(a: trimesh.Trimesh, b: trimesh.Trimesh) -> bool:
    """True when the axis-aligned bounding boxes of *a* and *b* overlap."""
    return bool(
        np.all(a.bounds[1] >= b.bounds[0] - 1)
        and np.all(b.bounds[1] >= a.bounds[0] - 1)
    )


@dataclass
class GatingConfig:
    gate_diameter: float = 12.0  # mm
    runner_width: float = 6.0  # mm
    runner_depth: float = 4.0  # mm
    vent_width: float = 4.0  # mm
    vent_depth: float = 0.03  # mm (for silicone)
    n_vents: int = 4
    n_gates: int = 1
    runner_type: str = "cold"
    gate_search_resolution: int = 20
    funnel_angle: float = 30.0  # pour funnel taper degrees
    # Manual placement: None = auto, list = user-specified positions
    gate_position: list[float] | None = None  # manual [x,y,z] for primary gate
    vent_positions: list[list[float]] | None = None  # manual [[x,y,z],...] for vents


@dataclass
class GatePosition:
    position: np.ndarray
    score: float = 0.0
    flow_balance: float = 0.0
    accessibility: float = 0.0

    def to_dict(self) -> dict:
        return {
            "position": self.position.tolist(),
            "score": round(float(self.score), 4),
            "flow_balance": round(float(self.flow_balance), 4),
            "accessibility": round(float(self.accessibility), 4),
        }


@dataclass
class VentPosition:
    position: np.ndarray
    normal: np.ndarray

    def to_dict(self) -> dict:
        return {
            "position": self.position.tolist(),
            "normal": self.normal.tolist(),
        }


@dataclass
class RunnerSegment:
    start: np.ndarray
    end: np.ndarray
    width: float
    depth: float

    def to_dict(self) -> dict:
        return {
            "start": self.start.tolist(),
            "end": self.end.tolist(),
            "width": round(self.width, 2),
            "depth": round(self.depth, 2),
        }


@dataclass
class GatingResult:
    gate: GatePosition
    gates: list[GatePosition] | None = None
    vents: list[VentPosition] = None
    runners: list[RunnerSegment] | None = None
    gate_diameter: float = 12.0
    runner_width: float = 6.0
    cavity_volume: float = 0.0
    estimated_fill_time: float = 0.0
    estimated_material_volume: float = 0.0
    gate_mesh: object = None
    gate_meshes: list | None = None
    runner_meshes: list | None = None
    vent_meshes: list = None

    def to_dict(self) -> dict:
        result = {
            "gate": self.gate.to_dict(),
            "vents": [v.to_dict() for v in (self.vents or [])],
            "gate_diameter": round(self.gate_diameter, 2),
            "runner_width": round(self.runner_width, 2),
            "cavity_volume": round(self.cavity_volume, 2),
            "estimated_fill_time": round(self.estimated_fill_time, 1),
            "estimated_material_volume": round(self.estimated_material_volume, 2),
        }
        if self.gates:
            result["gates"] = [g.to_dict() for g in self.gates]
        if self.runners:
            result["runners"] = [r.to_dict() for r in self.runners]
        if self.gate_mesh is not None:
            result["gate_mesh"] = {
                "vertices": np.asarray(self.gate_mesh.vertices).tolist(),
                "faces": np.asarray(self.gate_mesh.faces).tolist(),
            }
        if self.gate_meshes:
            result["gate_meshes"] = [
                {"vertices": np.asarray(m.vertices).tolist(),
                 "faces": np.asarray(m.faces).tolist()}
                for m in self.gate_meshes
            ]
        if self.runner_meshes:
            result["runner_meshes"] = [
                {"vertices": np.asarray(m.vertices).tolist(),
                 "faces": np.asarray(m.faces).tolist()}
                for m in self.runner_meshes
            ]
        if self.vent_meshes:
            result["vent_meshes"] = [
                {
                    "vertices": np.asarray(m.vertices).tolist(),
                    "faces": np.asarray(m.faces).tolist(),
                }
                for m in self.vent_meshes
            ]
        return result


def _build_face_adjacency(tm: trimesh.Trimesh) -> dict[int, list[int]]:
    """Build face adjacency from shared edges (for BFS fill sim)."""
    adj: dict[int, list[int]] = {}
    try:
        for edge, faces in zip(tm.face_adjacency_edges, tm.face_adjacency):
            a, b = int(faces[0]), int(faces[1])
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
    except Exception:
        pass
    return adj


class GatingSystem:
    """浇注系统设计器 — 整合浇口优化、BFS排气、流道布局、手动布置"""

    def __init__(self, config: GatingConfig | None = None):
        self.config = config or GatingConfig()

    def design(
        self,
        mold: MoldResult,
        model: MeshData,
        material: MaterialProperties,
    ) -> GatingResult:
        logger.info(
            "Designing gating system for %s (n_gates=%d, runner=%s)",
            material.name, self.config.n_gates, self.config.runner_type,
        )

        tm = model.to_trimesh()
        if tm.is_watertight:
            cavity_volume = float(tm.volume)
        else:
            try:
                cavity_volume = float(tm.convex_hull.volume * 0.7)
                logger.info("Non-watertight mesh, using convex hull approx volume")
            except Exception:
                cavity_volume = 0.0

        n_gates = max(1, self.config.n_gates)

        if self.config.gate_position is not None:
            primary_gate = self._make_manual_gate(tm, mold)
            logger.info("Using manual gate position")
        else:
            primary_gate = self._optimize_gate_position(tm, mold)

        gates = [primary_gate]
        if n_gates > 1:
            extra = self._place_secondary_gates(
                tm, mold, primary_gate, n_gates - 1,
            )
            gates.extend(extra)

        vents = self._place_vents(tm, mold, primary_gate)

        runners = self._compute_runner_paths(gates, vents, tm, mold)

        per_gate_volume = cavity_volume / max(n_gates, 1)
        fill_time = self._estimate_fill_time(per_gate_volume, material)
        runner_volume = sum(
            np.linalg.norm(r.end - r.start) * r.width * r.depth
            for r in runners
        ) if runners else 0.0
        material_volume = (
            cavity_volume * (1.0 + material.shrinkage) * 1.1 + runner_volume
        )

        gate_meshes = [self._build_gate_mesh(g, mold) for g in gates]
        runner_meshes = self._build_runner_meshes(runners, mold)
        vent_meshes = self._build_vent_meshes(vents, mold)

        return GatingResult(
            gate=primary_gate,
            gates=gates if n_gates > 1 else None,
            vents=vents,
            runners=runners,
            gate_diameter=self.config.gate_diameter,
            runner_width=self.config.runner_width,
            cavity_volume=cavity_volume,
            estimated_fill_time=fill_time,
            estimated_material_volume=material_volume,
            gate_mesh=gate_meshes[0] if gate_meshes else None,
            gate_meshes=gate_meshes if n_gates > 1 else None,
            runner_meshes=runner_meshes,
            vent_meshes=vent_meshes,
        )

    # ------------------------------------------------------------------
    def apply_to_mold(self, mold: MoldResult, result: GatingResult) -> None:
        """Cut gate/vent holes into mold shells (in-place).

        Gate cylinders are offset so they extend from above the gate
        position downward through the entire mold, ensuring holes reach
        the cavity surface.  Vent cylinders are centered at the vent
        position and extend outward along the face normal.
        """
        direction = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            direction = np.asarray(mold.shells[0].direction, dtype=np.float64)
            n = np.linalg.norm(direction)
            if n > 1e-12:
                direction = direction / n

        all_shell_verts = np.vstack(
            [sh.mesh.to_trimesh().vertices for sh in mold.shells]
        ) if mold.shells else np.zeros((1, 3))
        all_h = all_shell_verts @ direction
        global_min_h = float(np.min(all_h))
        global_max_h = float(np.max(all_h))

        hole_specs: list[tuple[np.ndarray, np.ndarray, float, str]] = []
        hole_specs.append((
            result.gate.position, direction,
            result.gate_diameter / 2.0, "gate",
        ))
        if result.gates:
            for g in result.gates[1:]:
                hole_specs.append((g.position, direction, result.gate_diameter / 2.0, "gate"))
        for v in (result.vents or []):
            vnorm = np.asarray(v.normal, dtype=np.float64)
            vnorm = vnorm / (np.linalg.norm(vnorm) + 1e-12)
            hole_specs.append((v.position, vnorm, self.config.vent_width / 2.0, "vent"))

        for sh in mold.shells:
            tm_shell = sh.mesh.to_trimesh()
            sh_dir = np.asarray(sh.direction, dtype=np.float64)
            sh_dir = sh_dir / (np.linalg.norm(sh_dir) + 1e-12)
            shell_heights = tm_shell.vertices @ direction
            shell_center_h = float(tm_shell.centroid @ direction)
            shell_h_range = float(np.ptp(shell_heights))
            n_cut = 0

            for pos, axis, radius, htype in hole_specs:
                if htype == "gate":
                    hole_h = float(pos @ direction)
                    if np.dot(sh_dir, direction) > 0 and hole_h < shell_center_h - shell_h_range:
                        continue
                    if np.dot(sh_dir, direction) < 0 and hole_h > shell_center_h + shell_h_range:
                        continue

                if htype == "vent":
                    vent_proj = tm_shell.vertices @ axis
                    vent_range = float(np.ptp(vent_proj))
                    cyl_height = min(vent_range + 10.0, 120.0)
                    cyl_height = max(cyl_height, 15.0)
                    cyl_center = pos
                else:
                    shell_min_h = float(np.min(shell_heights))
                    shell_max_h = float(np.max(shell_heights))
                    gate_h = float(pos @ direction)
                    cyl_height = (shell_max_h - shell_min_h) + 8.0
                    cyl_height = max(cyl_height, 15.0)
                    shell_mid_h = (shell_max_h + shell_min_h) / 2.0
                    cyl_center = pos - direction * (gate_h - shell_mid_h)

                cyl = self._make_hole_cylinder(cyl_center, axis, radius, mold, cyl_height)
                if cyl is None:
                    continue
                if not _aabb_overlap(tm_shell, cyl):
                    continue

                cut = _boolean_subtract(tm_shell, cyl)
                if cut is not None and len(cut.faces) > 4:
                    tm_shell = cut
                    n_cut += 1

            if n_cut > 0:
                sh.mesh = MeshData.from_trimesh(tm_shell)
                sh.volume = (
                    float(tm_shell.volume) if tm_shell.is_watertight else sh.volume
                )
                sh.surface_area = float(tm_shell.area)
                logger.info(
                    "Applied gating: cut %d holes in shell %d (%d faces)",
                    n_cut, sh.shell_id, len(tm_shell.faces),
                )

    def _make_hole_cylinder(
        self,
        position: np.ndarray,
        axis: np.ndarray,
        radius: float,
        mold: MoldResult,
        height: float | None = None,
    ) -> trimesh.Trimesh | None:
        """Cylinder centred at *position* along *axis* with adaptive height."""
        try:
            if height is None:
                all_bounds = np.vstack([s.mesh.bounds for s in mold.shells])
                extent = float(np.ptp(np.linalg.norm(all_bounds, axis=1)))
                height = max(extent * 2, 60.0)
            cyl = trimesh.creation.cylinder(
                radius=radius, height=height, sections=32,
            )
            ax = np.asarray(axis, dtype=np.float64)
            n = np.linalg.norm(ax)
            if n < 1e-12:
                return None
            ax = ax / n
            z = np.array([0.0, 0.0, 1.0])
            if not np.allclose(ax, z) and not np.allclose(ax, -z):
                rot_ax = np.cross(z, ax)
                rot_ax /= np.linalg.norm(rot_ax)
                angle = np.arccos(np.clip(float(np.dot(z, ax)), -1, 1))
                R = trimesh.transformations.rotation_matrix(angle, rot_ax)
                cyl.apply_transform(R)
            elif np.dot(ax, z) < 0:
                cyl.apply_transform(np.diag([1, -1, -1, 1]).astype(float))
            cyl.apply_translation(position)
            return cyl
        except Exception:
            logger.warning("Failed to build hole cylinder at %s", position)
            return None

    def _mold_outer_height(self, mold: MoldResult, up: np.ndarray) -> float:
        """Max height of the upper mold shell along *up* (outer surface)."""
        for sh in mold.shells:
            sh_dir = np.asarray(sh.direction, dtype=np.float64)
            if np.dot(sh_dir, up) > 0:
                verts = sh.mesh.to_trimesh().vertices
                return float(np.max(verts @ up))
        return 0.0

    def _optimize_gate_position(
        self, tm: trimesh.Trimesh, mold: MoldResult,
    ) -> GatePosition:
        """Multi-objective gate position optimization (vectorized)."""
        bounds = tm.bounds
        center = tm.centroid.copy()
        extents = bounds[1] - bounds[0]

        up = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            up = mold.shells[0].direction.copy()

        n = self.config.gate_search_resolution
        arb = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u_axis = np.cross(up, arb).astype(np.float64)
        u_axis /= np.linalg.norm(u_axis)
        v_axis = np.cross(up, u_axis).astype(np.float64)
        v_axis /= np.linalg.norm(v_axis)

        outer_h = self._mold_outer_height(mold, up)
        model_top = float(bounds[1] @ up)
        top_height = max(outer_h, model_top + 5.0) + 2.0
        half_span = float(np.max(extents)) * 0.4

        # Build candidate grid (vectorized)
        su = np.linspace(-half_span, half_span, n)
        sv = np.linspace(-half_span, half_span, n)
        su_grid, sv_grid = np.meshgrid(su, sv)
        su_flat = su_grid.ravel()
        sv_flat = sv_grid.ravel()

        candidates = (
            center[np.newaxis, :]
            + su_flat[:, np.newaxis] * u_axis[np.newaxis, :]
            + sv_flat[:, np.newaxis] * v_axis[np.newaxis, :]
        )
        heights = candidates @ up
        candidates += (top_height - heights)[:, np.newaxis] * up[np.newaxis, :]

        face_centers = tm.triangles_center
        face_areas = tm.area_faces

        # Vectorized scoring: (n_candidates, n_faces)
        diff = face_centers[np.newaxis, :, :] - candidates[:, np.newaxis, :]  # (C, F, 3)
        dists = np.linalg.norm(diff, axis=2)  # (C, F)

        # Flow balance: area-weighted distance std / mean
        area_weights = face_areas / face_areas.sum()
        mean_dist = (dists * area_weights[np.newaxis, :]).sum(axis=1)  # (C,)
        var_dist = (area_weights[np.newaxis, :] * (dists - mean_dist[:, np.newaxis]) ** 2).sum(axis=1)
        std_dist = np.sqrt(var_dist)
        flow_balance = 1.0 / (1.0 + std_dist / np.maximum(mean_dist, 1e-8))

        # Accessibility: 2D distance to centroid on the parting plane
        offset = candidates - center[np.newaxis, :]
        offset_along_up = (offset @ up)[:, np.newaxis] * up[np.newaxis, :]
        offset_2d = offset - offset_along_up
        dist_2d = np.linalg.norm(offset_2d, axis=1)
        max_half = float(np.max(extents)) * 0.5
        accessibility = 1.0 - np.clip(dist_2d / max(max_half, 1e-8), 0, 1)

        # Min-distance penalty (avoid placing gate too close to edges)
        min_dist_to_faces = dists.min(axis=1)
        min_reach = np.clip(min_dist_to_faces / max(float(np.max(extents)) * 0.1, 1e-8), 0, 1)

        scores = 0.5 * flow_balance + 0.3 * accessibility + 0.2 * (1.0 - min_reach)

        best_idx = int(np.argmax(scores))
        best = GatePosition(
            position=candidates[best_idx],
            score=float(scores[best_idx]),
            flow_balance=float(flow_balance[best_idx]),
            accessibility=float(accessibility[best_idx]),
        )

        logger.info("Gate at [%.1f, %.1f, %.1f] score=%.3f", *best.position, best.score)
        return best

    def _make_manual_gate(
        self, tm: trimesh.Trimesh, mold: MoldResult,
    ) -> GatePosition:
        """Create gate at user-specified position, snapped to mold outer surface."""
        user_pos = np.asarray(self.config.gate_position, dtype=np.float64)

        up = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            up = np.asarray(mold.shells[0].direction, dtype=np.float64)
            up = up / (np.linalg.norm(up) + 1e-12)

        try:
            closest, _, _ = tm.nearest.on_surface([user_pos])
            surface_pt = closest[0]
        except Exception:
            surface_pt = user_pos.copy()

        outer_h = self._mold_outer_height(mold, up)
        model_top = float(tm.bounds[1] @ up)
        top_height = max(outer_h, model_top + 5.0) + 2.0
        pt_h = float(surface_pt @ up)
        gate_pos = surface_pt + up * (top_height - pt_h)

        logger.info("Manual gate at [%.1f, %.1f, %.1f]", *gate_pos)
        return GatePosition(position=gate_pos, score=1.0, flow_balance=0.5, accessibility=1.0)

    def _place_vents(
        self, tm: trimesh.Trimesh, mold: MoldResult, gate: GatePosition,
    ) -> list[VentPosition]:
        """BFS fill-simulation + air-trap detection for vent placement.

        Combines two complementary strategies from the merged algorithm:
        1. Gravity-fill BFS from the gate position to compute fill_time
           per face — late-filling areas need vents.
        2. Air-trap detection — local height maxima in the adjacency graph
           where air pockets form.
        3. Farthest-point sampling for well-spaced vent distribution.
        """
        # Manual placement
        if self.config.vent_positions is not None and len(self.config.vent_positions) > 0:
            return self._place_manual_vents(tm, self.config.vent_positions)

        face_centers = tm.triangles_center
        face_normals = np.asarray(tm.face_normals, dtype=np.float64)
        n_faces = len(face_centers)
        n_vents = self.config.n_vents

        if n_faces < 4:
            return self._place_vents_fallback(tm, gate, n_vents)

        # Mold direction for height computation
        up = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            up = np.asarray(mold.shells[0].direction, dtype=np.float64)
            up = up / (np.linalg.norm(up) + 1e-12)

        face_heights = face_centers @ up

        # Build face adjacency
        import heapq
        adj = _build_face_adjacency(tm)

        # Find start face nearest to gate
        dists_to_gate = np.linalg.norm(face_centers - gate.position, axis=1)
        start = int(np.argmin(dists_to_gate))

        # BFS Dijkstra with gravity cost
        fill_time = np.full(n_faces, np.inf)
        fill_time[start] = 0.0
        visited = np.zeros(n_faces, dtype=bool)
        heap: list[tuple[float, int]] = [(0.0, start)]

        while heap:
            t, fi = heapq.heappop(heap)
            if visited[fi]:
                continue
            visited[fi] = True
            fill_time[fi] = t
            for nj in adj.get(fi, []):
                if visited[nj]:
                    continue
                dh = face_heights[nj] - face_heights[fi]
                cost = 1.0 + dh * 3.0 if dh > 0 else max(0.3, 1.0 + dh * 0.3)
                new_t = t + cost
                if new_t < fill_time[nj]:
                    fill_time[nj] = new_t
                    heapq.heappush(heap, (new_t, nj))

        # Air trap detection: local height maxima
        air_trap = np.zeros(n_faces)
        for fi in range(n_faces):
            nbrs = adj.get(fi, [])
            if not nbrs:
                continue
            nbr_h = face_heights[np.array(nbrs)]
            if face_heights[fi] > np.max(nbr_h):
                air_trap[fi] = face_heights[fi] - float(np.mean(nbr_h))

        # Normalize
        ft_finite = fill_time[np.isfinite(fill_time)]
        if len(ft_finite) == 0:
            return self._place_vents_fallback(tm, gate, n_vents)
        ft_max = float(np.max(ft_finite)) + 1e-8
        fill_norm = np.where(np.isfinite(fill_time), fill_time / ft_max, 1.0)

        h_min, h_max = float(np.min(face_heights)), float(np.max(face_heights))
        h_range = h_max - h_min + 1e-8
        height_norm = (face_heights - h_min) / h_range

        trap_max = float(np.max(air_trap)) + 1e-8
        trap_norm = air_trap / trap_max

        # Combined score
        vent_score = 0.40 * fill_norm + 0.35 * height_norm + 0.25 * trap_norm

        # Farthest-point greedy selection
        min_spacing = float(np.max(tm.extents)) * 0.15
        vents: list[VentPosition] = []
        remaining = np.ones(n_faces, dtype=bool)

        for _ in range(n_vents):
            cands = np.where(remaining)[0]
            if len(cands) == 0:
                break
            best = cands[int(np.argmax(vent_score[cands]))]
            pos = face_centers[best].copy()
            normal = face_normals[best].copy()
            vents.append(VentPosition(position=pos, normal=normal))
            d_sq = np.sum((face_centers - pos) ** 2, axis=1)
            remaining &= (d_sq > min_spacing * min_spacing)

        logger.info(
            "Vent placement (BFS): %d placed, %d air traps detected",
            len(vents), int(np.sum(air_trap > 0)),
        )
        return vents

    def _place_manual_vents(
        self, tm: trimesh.Trimesh, positions: list[list[float]],
    ) -> list[VentPosition]:
        """Place vents at user-specified positions, snapped to surface."""
        face_centers = tm.triangles_center
        face_normals = np.asarray(tm.face_normals, dtype=np.float64)
        vents: list[VentPosition] = []
        min_spacing = self.config.vent_width * 3.0

        for upos in positions:
            pt = np.asarray(upos, dtype=np.float64)
            dists = np.linalg.norm(face_centers - pt, axis=1)
            idx = int(np.argmin(dists))
            pos = face_centers[idx].copy()
            normal = face_normals[idx].copy()

            too_close = any(
                np.linalg.norm(pos - v.position) < min_spacing for v in vents
            )
            if too_close:
                logger.warning("Manual vent too close to existing — skipping")
                continue

            vents.append(VentPosition(position=pos, normal=normal))

        logger.info("Manual vents: %d/%d placed", len(vents), len(positions))
        return vents

    def _place_vents_fallback(
        self, tm: trimesh.Trimesh, gate: GatePosition, n_vents: int,
    ) -> list[VentPosition]:
        """Simple fallback: faces farthest from gate."""
        face_centers = tm.triangles_center
        face_normals = np.asarray(tm.face_normals, dtype=np.float64)
        dists = np.linalg.norm(face_centers - gate.position, axis=1)
        vents: list[VentPosition] = []
        remaining = np.ones(len(face_centers), dtype=bool)

        for _ in range(n_vents):
            masked = dists.copy()
            masked[~remaining] = -np.inf
            for v in vents:
                d2 = np.linalg.norm(face_centers - v.position, axis=1)
                masked = np.minimum(masked, d2)
                masked[~remaining] = -np.inf
            idx = int(np.argmax(masked))
            vents.append(VentPosition(
                position=face_centers[idx].copy(),
                normal=face_normals[idx].copy(),
            ))
            remaining &= np.linalg.norm(face_centers - face_centers[idx], axis=1) > 5.0

        return vents

    def _place_secondary_gates(
        self, tm: trimesh.Trimesh, mold: MoldResult,
        primary: GatePosition, n_extra: int,
    ) -> list[GatePosition]:
        """Place additional gates maximizing distance from primary and each other."""
        bounds = tm.bounds
        center = tm.centroid.copy()
        extents = bounds[1] - bounds[0]

        up = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            up = mold.shells[0].direction.copy()

        arb = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u_axis = np.cross(up, arb).astype(np.float64)
        u_axis /= np.linalg.norm(u_axis)
        v_axis = np.cross(up, u_axis).astype(np.float64)
        v_axis /= np.linalg.norm(v_axis)

        n = self.config.gate_search_resolution
        outer_h = self._mold_outer_height(mold, up)
        model_top = float(bounds[1] @ up)
        top_height = max(outer_h, model_top + 5.0) + 2.0
        half_span = float(np.max(extents)) * 0.4

        su = np.linspace(-half_span, half_span, n)
        sv = np.linspace(-half_span, half_span, n)
        su_grid, sv_grid = np.meshgrid(su, sv)
        candidates = (
            center[np.newaxis, :]
            + su_grid.ravel()[:, np.newaxis] * u_axis[np.newaxis, :]
            + sv_grid.ravel()[:, np.newaxis] * v_axis[np.newaxis, :]
        )
        heights = candidates @ up
        candidates += (top_height - heights)[:, np.newaxis] * up[np.newaxis, :]

        placed = [primary.position.copy()]
        extras: list[GatePosition] = []

        for _ in range(n_extra):
            min_dists = np.full(len(candidates), np.inf)
            for p in placed:
                d = np.linalg.norm(candidates - p[np.newaxis, :], axis=1)
                min_dists = np.minimum(min_dists, d)

            best_idx = int(np.argmax(min_dists))
            pos = candidates[best_idx].copy()
            placed.append(pos)

            face_centers = tm.triangles_center
            face_dists = np.linalg.norm(face_centers - pos[np.newaxis, :], axis=1)
            face_areas = tm.area_faces
            aw = face_areas / face_areas.sum()
            mean_d = float((face_dists * aw).sum())
            std_d = float(np.sqrt((aw * (face_dists - mean_d) ** 2).sum()))
            fb = 1.0 / (1.0 + std_d / max(mean_d, 1e-8))

            extras.append(GatePosition(
                position=pos, score=float(min_dists[best_idx]),
                flow_balance=fb, accessibility=0.5,
            ))
            logger.info(
                "Secondary gate #%d at [%.1f, %.1f, %.1f]",
                len(extras), *pos,
            )

        return extras

    def _compute_runner_paths(
        self, gates: list[GatePosition], vents: list[VentPosition],
        tm: trimesh.Trimesh, mold: MoldResult,
    ) -> list[RunnerSegment]:
        """Compute runner channel paths connecting gates to a sprue point.

        For multi-gate: balanced H-pattern or star layout from a central sprue.
        For single gate: straight runner from gate to model top.
        Vents get thin runners from nearest gate.
        """
        cfg = self.config

        up = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            up = mold.shells[0].direction.copy()
            up = up / (np.linalg.norm(up) + 1e-12)

        runners: list[RunnerSegment] = []

        if len(gates) == 1:
            gate_pos = gates[0].position.copy()
            sprue_top = gate_pos + up * 10.0
            runners.append(RunnerSegment(
                start=sprue_top, end=gate_pos,
                width=cfg.runner_width, depth=cfg.runner_depth,
            ))
        else:
            center_pos = np.mean([g.position for g in gates], axis=0)
            sprue_top = center_pos + up * 15.0

            runners.append(RunnerSegment(
                start=sprue_top, end=center_pos,
                width=cfg.runner_width * 1.2, depth=cfg.runner_depth * 1.2,
            ))
            for g in gates:
                runners.append(RunnerSegment(
                    start=center_pos, end=g.position,
                    width=cfg.runner_width, depth=cfg.runner_depth,
                ))

        for vent in vents:
            nearest_gate = min(gates, key=lambda g: float(
                np.linalg.norm(g.position - vent.position)
            ))
            runners.append(RunnerSegment(
                start=vent.position,
                end=vent.position + np.asarray(vent.normal) * 8.0,
                width=cfg.vent_width, depth=max(cfg.vent_depth * 50, 1.0),
            ))

        logger.info("Computed %d runner segments", len(runners))
        return runners

    def _build_runner_meshes(
        self, runners: list[RunnerSegment], mold: MoldResult,
    ) -> list[trimesh.Trimesh]:
        """Build trapezoidal channel meshes for each runner segment."""
        meshes: list[trimesh.Trimesh] = []
        for seg in runners:
            start, end = seg.start, seg.end
            direction = end - start
            length = float(np.linalg.norm(direction))
            if length < 0.1:
                continue

            box = trimesh.creation.box(
                extents=[seg.width, length, seg.depth],
            )

            d = direction / length
            z_axis = np.array([0.0, 1.0, 0.0])
            if not np.allclose(d, z_axis) and not np.allclose(d, -z_axis):
                axis = np.cross(z_axis, d)
                axis_len = float(np.linalg.norm(axis))
                if axis_len > 1e-9:
                    axis /= axis_len
                    angle = np.arccos(np.clip(float(np.dot(z_axis, d)), -1, 1))
                    rot = trimesh.transformations.rotation_matrix(angle, axis)
                    box.apply_transform(rot)

            mid = (start + end) / 2.0
            box.apply_translation(mid)
            meshes.append(box)

        return meshes

    def _estimate_fill_time(
        self, cavity_volume_mm3: float, material: MaterialProperties,
    ) -> float:
        """Rough fill time estimate based on volume and material viscosity."""
        if cavity_volume_mm3 <= 0:
            return 0.0

        gate_area_mm2 = np.pi * (self.config.gate_diameter / 2) ** 2

        # Simplified: flow rate ~ gate_area * pressure / viscosity
        # Q = A * ΔP / (μ * L), approximate L as cube root of volume
        char_length = cavity_volume_mm3 ** (1.0 / 3.0)
        viscosity_pa_s = material.viscosity / 1000.0
        pressure_pa = material.max_pressure * 1e6

        if viscosity_pa_s < 1e-6:
            return 0.1

        flow_rate = gate_area_mm2 * pressure_pa / (viscosity_pa_s * char_length)
        if flow_rate < 1e-6:
            return 9999.0

        fill_time_s = cavity_volume_mm3 / flow_rate
        return float(max(fill_time_s, 0.1))

    def _build_gate_mesh(self, gate: GatePosition, mold: MoldResult) -> trimesh.Trimesh:
        """Build a cylindrical gate mesh limited to the nearest shell thickness."""
        up = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            up = np.asarray(mold.shells[0].direction, dtype=np.float64)
        up = up / (np.linalg.norm(up) + 1e-12)

        r = self.config.gate_diameter / 2
        gate_h = float(np.asarray(gate.position) @ up)

        best_shell_h = 20.0
        for sh in mold.shells:
            shell_verts = sh.mesh.to_trimesh().vertices
            shell_heights = shell_verts @ up
            sh_min = float(np.min(shell_heights))
            sh_max = float(np.max(shell_heights))
            if sh_min <= gate_h <= sh_max + 5.0:
                best_shell_h = sh_max - sh_min + 6.0
                break

        height = max(best_shell_h, 15.0)

        cyl = trimesh.creation.cylinder(radius=r, height=height, sections=24)

        z_axis = np.array([0.0, 0.0, 1.0])
        if not np.allclose(up, z_axis) and not np.allclose(up, -z_axis):
            axis = np.cross(z_axis, up)
            axis_len = np.linalg.norm(axis)
            if axis_len > 1e-9:
                axis /= axis_len
                angle = np.arccos(np.clip(np.dot(z_axis, up), -1, 1))
                rot = trimesh.transformations.rotation_matrix(angle, axis)
                cyl.apply_transform(rot)

        cyl.apply_translation(gate.position)
        return cyl

    def _build_vent_meshes(
        self, vents: list[VentPosition], mold: MoldResult,
    ) -> list[trimesh.Trimesh]:
        """Build elongated box meshes for each vent, spanning toward the mold surface."""
        meshes: list[trimesh.Trimesh] = []
        w = self.config.vent_width
        d = max(self.config.vent_depth * 100, 2.0)

        # Estimate mold wall thickness along vent normals
        all_shell_verts = np.vstack([sh.mesh.to_trimesh().vertices for sh in mold.shells]) if mold.shells else None
        base_h = 20.0

        for vent in vents:
            normal = np.asarray(vent.normal, dtype=np.float64)
            normal /= max(np.linalg.norm(normal), 1e-9)

            h = base_h
            if all_shell_verts is not None:
                proj = (all_shell_verts - vent.position) @ normal
                max_proj = float(np.max(proj))
                h = max(max_proj + 4.0, base_h)

            box = trimesh.creation.box(extents=[w, d, h])

            z_axis = np.array([0.0, 0.0, 1.0])
            if not np.allclose(normal, z_axis) and not np.allclose(normal, -z_axis):
                axis = np.cross(z_axis, normal)
                axis_len = np.linalg.norm(axis)
                if axis_len > 1e-9:
                    axis /= axis_len
                    angle = np.arccos(np.clip(np.dot(z_axis, normal), -1, 1))
                    rot = trimesh.transformations.rotation_matrix(angle, axis)
                    box.apply_transform(rot)

            offset = vent.position + normal * (h / 2)
            box.apply_translation(offset)
            meshes.append(box)

        return meshes
