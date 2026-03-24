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


@dataclass
class GatingConfig:
    gate_diameter: float = 12.0  # mm
    runner_width: float = 6.0  # mm
    runner_depth: float = 4.0  # mm
    vent_width: float = 4.0  # mm
    vent_depth: float = 0.03  # mm (for silicone)
    n_vents: int = 4
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
class GatingResult:
    gate: GatePosition
    vents: list[VentPosition]
    gate_diameter: float
    runner_width: float
    cavity_volume: float = 0.0
    estimated_fill_time: float = 0.0
    estimated_material_volume: float = 0.0

    def to_dict(self) -> dict:
        return {
            "gate": self.gate.to_dict(),
            "vents": [v.to_dict() for v in self.vents],
            "gate_diameter": round(self.gate_diameter, 2),
            "runner_width": round(self.runner_width, 2),
            "cavity_volume": round(self.cavity_volume, 2),
            "estimated_fill_time": round(self.estimated_fill_time, 1),
            "estimated_material_volume": round(self.estimated_material_volume, 2),
        }


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
        logger.info("Designing gating system for %s", material.name)

        tm = model.to_trimesh()
        cavity_volume = float(tm.volume) if tm.is_watertight else 0.0

        gate = self._optimize_gate_position(tm, mold)
        vents = self._place_vents(tm, mold, gate)

        fill_time = self._estimate_fill_time(cavity_volume, material)
        material_volume = cavity_volume * (1.0 + material.shrinkage) * 1.1  # 10% overflow

        return GatingResult(
            gate=gate,
            vents=vents,
            gate_diameter=self.config.gate_diameter,
            runner_width=self.config.runner_width,
            cavity_volume=cavity_volume,
            estimated_fill_time=fill_time,
            estimated_material_volume=material_volume,
        )

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
