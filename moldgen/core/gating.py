"""浇注系统设计 — 浇口位置优化、流道布局、排气孔"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import trimesh

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


def _boolean_subtract(
    mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh,
) -> trimesh.Trimesh | None:
    try:
        import manifold3d
        ma = manifold3d.Manifold(manifold3d.Mesh(
            vert_properties=np.asarray(mesh_a.vertices, dtype=np.float32),
            tri_verts=np.asarray(mesh_a.faces, dtype=np.uint32),
        ))
        mb = manifold3d.Manifold(manifold3d.Mesh(
            vert_properties=np.asarray(mesh_b.vertices, dtype=np.float32),
            tri_verts=np.asarray(mesh_b.faces, dtype=np.uint32),
        ))
        out = (ma - mb).to_mesh()
        return trimesh.Trimesh(
            vertices=np.asarray(out.vert_properties[:, :3]),
            faces=np.asarray(out.tri_verts), process=True,
        )
    except Exception:
        pass
    try:
        r = mesh_a.difference(mesh_b)
        if r is not None and len(r.faces) > 4:
            return r
    except Exception:
        pass
    return None


def _boolean_union(
    mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh,
) -> trimesh.Trimesh | None:
    try:
        import manifold3d
        ma = manifold3d.Manifold(manifold3d.Mesh(
            vert_properties=np.asarray(mesh_a.vertices, dtype=np.float32),
            tri_verts=np.asarray(mesh_a.faces, dtype=np.uint32),
        ))
        mb = manifold3d.Manifold(manifold3d.Mesh(
            vert_properties=np.asarray(mesh_b.vertices, dtype=np.float32),
            tri_verts=np.asarray(mesh_b.faces, dtype=np.uint32),
        ))
        out = (ma + mb).to_mesh()
        return trimesh.Trimesh(
            vertices=np.asarray(out.vert_properties[:, :3]),
            faces=np.asarray(out.tri_verts), process=True,
        )
    except Exception:
        pass
    try:
        r = mesh_a.union(mesh_b)
        if r is not None and len(r.faces) > 4:
            return r
    except Exception:
        pass
    return None


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


class GatingSystem:
    """浇注系统设计器"""

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
        cavity_volume = float(tm.volume) if tm.is_watertight else 0.0

        n_gates = max(1, self.config.n_gates)
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

        Boolean-subtracts long cylinders at each gate/vent position so the
        exported shell geometry has physical through-holes that match the
        gating design.  This mutates *mold.shells* directly; subsequent
        GLB / export endpoints will return the updated meshes.
        """
        direction = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            direction = np.asarray(mold.shells[0].direction, dtype=np.float64)
            n = np.linalg.norm(direction)
            if n > 1e-12:
                direction = direction / n

        gate_cyl = self._make_hole_cylinder(
            result.gate.position, direction, result.gate_diameter / 2.0,
            mold,
        )
        vent_cyls = [
            self._make_hole_cylinder(
                v.position, np.asarray(v.normal, dtype=np.float64),
                self.config.vent_width / 2.0, mold,
            )
            for v in result.vents
        ]

        for sh in mold.shells:
            tm_shell = sh.mesh.to_trimesh()
            n_cut = 0

            for cyl in [gate_cyl] + vent_cyls:
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
    ) -> trimesh.Trimesh | None:
        """Long cylinder centred at *position* along *axis*."""
        try:
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

        top_height = float(bounds[1] @ up) + 5.0
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

    def _place_vents(
        self, tm: trimesh.Trimesh, mold: MoldResult, gate: GatePosition,
    ) -> list[VentPosition]:
        """Place vent holes at positions farthest from the gate."""
        face_centers = tm.triangles_center
        face_normals = np.asarray(tm.face_normals, dtype=np.float64)

        dists = np.linalg.norm(face_centers - gate.position, axis=1)
        n_vents = self.config.n_vents

        vents: list[VentPosition] = []
        remaining_mask = np.ones(len(face_centers), dtype=bool)

        for _ in range(n_vents):
            masked_dists = dists.copy()
            masked_dists[~remaining_mask] = -np.inf

            # Also maximize distance to existing vents
            for vent in vents:
                d_to_vent = np.linalg.norm(face_centers - vent.position, axis=1)
                masked_dists = np.minimum(masked_dists, d_to_vent)
                masked_dists[~remaining_mask] = -np.inf

            idx = int(np.argmax(masked_dists))
            pos = face_centers[idx]
            normal = face_normals[idx]

            vents.append(VentPosition(position=pos.copy(), normal=normal.copy()))

            near_mask = np.linalg.norm(face_centers - pos, axis=1) < 5.0
            remaining_mask[near_mask] = False

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
        top_height = float(bounds[1] @ up) + 5.0
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
        """Build a cylindrical gate mesh."""
        up = np.array([0.0, 0.0, 1.0])
        if mold.shells:
            up = np.asarray(mold.shells[0].direction, dtype=np.float64)

        r = self.config.gate_diameter / 2
        height = max(self.config.gate_diameter * 1.5, 15.0)
        cyl = trimesh.creation.cylinder(radius=r, height=height, sections=24)

        z_axis = np.array([0.0, 0.0, 1.0])
        if not np.allclose(up, z_axis):
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
        """Build small box meshes for each vent."""
        meshes: list[trimesh.Trimesh] = []
        w = self.config.vent_width
        d = max(self.config.vent_depth * 100, 2.0)
        h = 8.0

        for vent in vents:
            box = trimesh.creation.box(extents=[w, d, h])

            normal = np.asarray(vent.normal, dtype=np.float64)
            normal /= max(np.linalg.norm(normal), 1e-9)

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
