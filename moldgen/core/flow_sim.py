"""灌注流动仿真 — L1 启发式 + L2 达西流 (CPU/GPU)（v4: 多场分析 + 可视化数据）"""

from __future__ import annotations

import heapq
import logging
import math
from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy import ndimage, sparse
from scipy.sparse.linalg import spsolve

from moldgen.core.gating import GatingResult
from moldgen.core.material import MaterialProperties
from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


def _safe_float(v: float) -> float:
    """Clamp inf/nan to JSON-safe 0.0."""
    if math.isnan(v) or math.isinf(v):
        return 0.0
    return v


@dataclass
class SimConfig:
    level: int = 2  # 1=heuristic, 2=darcy
    voxel_resolution: int = 64
    time_steps: int = 60
    animation_frames: int = 30
    use_gpu: bool = False
    detect_air_traps: bool = True
    detect_weld_lines: bool = True
    convergence_tol: float = 1e-6
    compute_shear_rate: bool = True
    compute_temperature: bool = True
    compute_cure_progress: bool = True


@dataclass
class FlowDefect:
    defect_type: str  # "short_shot" | "air_trap" | "weld_line" | "slow_fill"
    position: np.ndarray | None = None
    severity: float = 0.0  # 0-1
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "type": self.defect_type,
            "position": self.position.tolist() if self.position is not None else None,
            "severity": round(_safe_float(float(self.severity)), 3),
            "description": self.description,
        }


@dataclass
class AnalysisReport:
    """Comprehensive simulation analysis report."""
    fill_quality_score: float = 0.0
    fill_uniformity_index: float = 0.0
    pressure_uniformity_index: float = 0.0
    velocity_uniformity_index: float = 0.0
    max_shear_rate: float = 0.0
    avg_shear_rate: float = 0.0
    temperature_range: tuple[float, float] = (0.0, 0.0)
    avg_temperature: float = 0.0
    cure_progress_range: tuple[float, float] = (0.0, 0.0)
    avg_cure_progress: float = 0.0
    thin_wall_fraction: float = 0.0
    thick_wall_fraction: float = 0.0
    min_thickness: float = 0.0
    max_thickness: float = 0.0
    avg_thickness: float = 0.0
    flow_length_ratio: float = 0.0
    fill_balance_score: float = 0.0
    gate_efficiency: float = 0.0
    n_stagnation_zones: int = 0
    n_high_shear_zones: int = 0
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        sf = _safe_float
        return {
            "fill_quality_score": round(sf(self.fill_quality_score), 4),
            "fill_uniformity_index": round(sf(self.fill_uniformity_index), 4),
            "pressure_uniformity_index": round(sf(self.pressure_uniformity_index), 4),
            "velocity_uniformity_index": round(sf(self.velocity_uniformity_index), 4),
            "max_shear_rate": round(sf(self.max_shear_rate), 2),
            "avg_shear_rate": round(sf(self.avg_shear_rate), 2),
            "temperature_range": [round(sf(self.temperature_range[0]), 1), round(sf(self.temperature_range[1]), 1)],
            "avg_temperature": round(sf(self.avg_temperature), 1),
            "cure_progress_range": [round(sf(self.cure_progress_range[0]), 4), round(sf(self.cure_progress_range[1]), 4)],
            "avg_cure_progress": round(sf(self.avg_cure_progress), 4),
            "thin_wall_fraction": round(sf(self.thin_wall_fraction), 4),
            "thick_wall_fraction": round(sf(self.thick_wall_fraction), 4),
            "min_thickness": round(sf(self.min_thickness), 2),
            "max_thickness": round(sf(self.max_thickness), 2),
            "avg_thickness": round(sf(self.avg_thickness), 2),
            "flow_length_ratio": round(sf(self.flow_length_ratio), 2),
            "fill_balance_score": round(sf(self.fill_balance_score), 4),
            "gate_efficiency": round(sf(self.gate_efficiency), 4),
            "n_stagnation_zones": self.n_stagnation_zones,
            "n_high_shear_zones": self.n_high_shear_zones,
            "recommendations": self.recommendations,
        }


@dataclass
class SimulationResult:
    fill_fraction: float = 0.0
    fill_time_seconds: float = 0.0
    max_pressure: float = 0.0
    defects: list[FlowDefect] = field(default_factory=list)
    # Volumetric fields (voxel grids)
    fill_time_field: np.ndarray | None = None
    pressure_field: np.ndarray | None = None
    velocity_magnitude: np.ndarray | None = None
    shear_rate_field: np.ndarray | None = None
    temperature_field: np.ndarray | None = None
    cure_progress_field: np.ndarray | None = None
    thickness_field: np.ndarray | None = None
    animation_frames: list[np.ndarray] | None = None
    # Voxel metadata for coordinate mapping
    voxel_origin: np.ndarray | None = None
    voxel_pitch: float = 0.0
    voxel_mask: np.ndarray | None = None
    # Analysis report
    analysis: AnalysisReport | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "fill_fraction": round(_safe_float(float(self.fill_fraction)), 4),
            "fill_time_seconds": round(_safe_float(float(self.fill_time_seconds)), 2),
            "max_pressure": round(_safe_float(float(self.max_pressure)), 2),
            "defects": [df.to_dict() for df in self.defects],
            "has_fill_time_field": self.fill_time_field is not None,
            "has_pressure_field": self.pressure_field is not None,
            "has_velocity_field": self.velocity_magnitude is not None,
            "has_shear_rate_field": self.shear_rate_field is not None,
            "has_temperature_field": self.temperature_field is not None,
            "has_cure_progress_field": self.cure_progress_field is not None,
            "has_thickness_field": self.thickness_field is not None,
            "n_animation_frames": len(self.animation_frames) if self.animation_frames else 0,
            "has_visualization": self.voxel_origin is not None,
        }
        if self.fill_time_field is not None:
            d["voxel_resolution"] = list(self.fill_time_field.shape)
        if self.analysis:
            d["analysis"] = self.analysis.to_dict()
        return d


class FlowSimulator:
    """灌注流动仿真器（v4: 多场分析）"""

    def __init__(self, config: SimConfig | None = None):
        self.config = config or SimConfig()

    def simulate(
        self,
        model: MeshData,
        gating: GatingResult,
        material: MaterialProperties,
    ) -> SimulationResult:
        if self.config.level == 1:
            return self._run_level1(model, gating, material)
        return self._run_level2(model, gating, material)

    # ── Level 1: Heuristic (CPU, fast) ───────────────────────────────

    def _run_level1(
        self,
        model: MeshData,
        gating: GatingResult,
        material: MaterialProperties,
    ) -> SimulationResult:
        logger.info("Running L1 heuristic simulation")
        tm = model.to_trimesh()

        gate_pos = gating.gate.position
        face_centers = tm.triangles_center
        face_areas = tm.area_faces

        distances = np.linalg.norm(face_centers - gate_pos, axis=1)
        max_dist = float(np.max(distances)) if len(distances) > 0 else 1.0
        total_area = float(np.sum(face_areas))
        est_time = gating.estimated_fill_time

        defects: list[FlowDefect] = []

        area_p10 = float(np.percentile(face_areas, 10))
        thin_faces = face_areas < area_p10 * 0.5
        if np.any(thin_faces):
            thin_ratio = float(np.sum(face_areas[thin_faces])) / total_area
            defects.append(FlowDefect(
                defect_type="slow_fill",
                position=face_centers[thin_faces].mean(axis=0),
                severity=min(thin_ratio * 3, 1.0),
                description=f"{int(np.sum(thin_faces))} thin-wall faces ({thin_ratio:.1%} area)",
            ))

        far_threshold = max_dist * 0.85
        very_far = distances > far_threshold
        if np.any(very_far):
            far_area = float(np.sum(face_areas[very_far])) / total_area
            defects.append(FlowDefect(
                defect_type="short_shot",
                position=face_centers[very_far].mean(axis=0),
                severity=min(far_area * 2, 1.0),
                description=f"{int(np.sum(very_far))} faces beyond {far_threshold:.0f}mm from gate",
            ))

        dists_norm = distances / max(max_dist, 1e-8)
        area_weights = face_areas / max(total_area, 1e-8)
        weighted_std = float(np.sqrt(np.average(
            (dists_norm - np.average(dists_norm, weights=area_weights)) ** 2,
            weights=area_weights,
        )))
        if weighted_std > 0.3:
            defects.append(FlowDefect(
                defect_type="weld_line",
                severity=min(weighted_std, 1.0),
                description=f"Asymmetric flow distribution (sigma={weighted_std:.2f})",
            ))

        fill_frac = 1.0 - sum(
            d.severity * 0.1 for d in defects if d.defect_type == "short_shot"
        )
        fill_frac = max(fill_frac, 0.5)

        report = AnalysisReport(
            fill_quality_score=fill_frac * 0.7 + (1.0 - min(len(defects) * 0.1, 1.0)) * 0.3,
            fill_uniformity_index=1.0 - min(weighted_std, 1.0),
            fill_balance_score=1.0 - min(weighted_std, 1.0),
            flow_length_ratio=max_dist / max(float(np.mean(distances)), 1e-8),
            recommendations=self._generate_recommendations_l1(defects, fill_frac),
        )

        return SimulationResult(
            fill_fraction=fill_frac,
            fill_time_seconds=est_time,
            max_pressure=material.max_pressure * 0.8,
            defects=defects,
            analysis=report,
        )

    def _generate_recommendations_l1(
        self, defects: list[FlowDefect], fill_frac: float,
    ) -> list[str]:
        recs: list[str] = []
        if fill_frac < 0.95:
            recs.append("充填率偏低，建议增大浇口直径或添加辅助浇口")
        for d in defects:
            if d.defect_type == "short_shot":
                recs.append("存在短射风险，建议增大浇口或提高注射压力")
            elif d.defect_type == "slow_fill":
                recs.append("薄壁区域充填缓慢，建议检查壁厚均匀性")
            elif d.defect_type == "weld_line":
                recs.append("流动不平衡，可能产生熔接线，建议调整浇口位置")
        if not recs:
            recs.append("L1 启发式分析未发现明显问题，建议运行 L2 精细仿真")
        return recs

    # ── Level 2: Simplified Darcy Flow (voxel-based, optimized) ──────

    def _run_level2(
        self,
        model: MeshData,
        gating: GatingResult,
        material: MaterialProperties,
    ) -> SimulationResult:
        res = self.config.voxel_resolution
        logger.info("Running L2 Darcy flow simulation (resolution=%d)", res)

        tm = model.to_trimesh()

        # Step 1: Voxelize
        voxels, origin, pitch = self._voxelize(tm, res)
        cavity_count = int(np.sum(voxels))
        logger.info("Voxelized: %d cavity voxels (pitch=%.3f mm)", cavity_count, pitch)

        if cavity_count == 0:
            return SimulationResult(fill_fraction=0.0, defects=[
                FlowDefect(defect_type="short_shot", severity=1.0,
                           description="Model could not be voxelized"),
            ])

        # Step 2: Thickness (distance transform)
        thickness = ndimage.distance_transform_edt(voxels).astype(np.float64) * pitch

        # Step 3: Permeability K = h^2/12
        K = np.where(voxels, thickness ** 2 / 12.0, 0.0)

        # Step 4: Gate voxel
        gate_voxel = self._world_to_voxel(gating.gate.position, origin, pitch, voxels.shape)

        # Step 5: Pressure field
        pressure = self._solve_pressure_vectorized(voxels, K, gate_voxel, material)

        # Step 6: Velocity magnitude
        pressure = np.nan_to_num(pressure, nan=0.0, posinf=0.0, neginf=0.0)
        grad = np.array(np.gradient(pressure, pitch))
        vel_mag = np.sqrt(np.sum(grad ** 2, axis=0)) * np.where(voxels, 1.0, 0.0)
        vel_mag = np.nan_to_num(vel_mag, nan=0.0, posinf=0.0, neginf=0.0)

        # Step 7: Shear rate estimation
        shear_rate = None
        if self.config.compute_shear_rate:
            shear_rate = self._compute_shear_rate(vel_mag, thickness, voxels, material)

        # Step 8: Fill front (Dijkstra-based)
        fill_time_field, frames = self._simulate_fill_dijkstra(
            voxels, vel_mag, gate_voxel, pitch, material
        )

        # Step 9: Temperature estimation
        temperature = None
        if self.config.compute_temperature:
            temperature = self._compute_temperature_field(
                fill_time_field, voxels, thickness, material
            )

        # Step 10: Cure progress estimation
        cure_progress = None
        if self.config.compute_cure_progress:
            cure_progress = self._compute_cure_progress(
                fill_time_field, voxels, temperature, material
            )

        # Step 11: Metrics
        fill_time_field = np.nan_to_num(fill_time_field, nan=np.inf, posinf=np.inf, neginf=0.0)
        filled = fill_time_field < np.inf
        fill_fraction = float(np.sum(filled & voxels)) / max(cavity_count, 1)
        finite_ft = fill_time_field[filled]
        finite_ft = finite_ft[np.isfinite(finite_ft)]
        max_fill_time = float(np.max(finite_ft)) if len(finite_ft) > 0 else 0.0
        p_vals = pressure[voxels]
        p_finite = p_vals[np.isfinite(p_vals)]
        max_pressure_val = float(np.max(p_finite)) if len(p_finite) > 0 else 0.0

        # Step 12: Defect detection
        defects = self._detect_defects(
            voxels, fill_time_field, pressure, vel_mag,
            origin, pitch, fill_fraction
        )

        # Step 13: Analysis report
        report = self._compute_analysis_report(
            voxels, fill_time_field, pressure, vel_mag,
            thickness, shear_rate, temperature, cure_progress,
            origin, pitch, fill_fraction, defects, material, gate_voxel,
        )

        logger.info(
            "L2 complete: fill=%.1f%%, time=%.1fs, defects=%d, quality=%.2f",
            fill_fraction * 100, max_fill_time, len(defects),
            report.fill_quality_score,
        )

        return SimulationResult(
            fill_fraction=fill_fraction,
            fill_time_seconds=max_fill_time,
            max_pressure=max_pressure_val,
            defects=defects,
            fill_time_field=fill_time_field,
            pressure_field=pressure,
            velocity_magnitude=vel_mag,
            shear_rate_field=shear_rate,
            temperature_field=temperature,
            cure_progress_field=cure_progress,
            thickness_field=thickness,
            animation_frames=frames,
            voxel_origin=origin,
            voxel_pitch=pitch,
            voxel_mask=voxels,
            analysis=report,
        )

    # ── Shear rate estimation ────────────────────────────────────────

    def _compute_shear_rate(
        self,
        vel_mag: np.ndarray,
        thickness: np.ndarray,
        voxels: np.ndarray,
        material: MaterialProperties,
    ) -> np.ndarray:
        """Estimate wall shear rate: gamma_dot ≈ 6V / h (slit flow approximation)."""
        h = np.where(voxels & (thickness > 0), thickness, 1.0)
        shear = np.where(voxels, 6.0 * vel_mag / h, 0.0)
        return shear

    # ── Temperature field estimation ─────────────────────────────────

    def _compute_temperature_field(
        self,
        fill_time: np.ndarray,
        voxels: np.ndarray,
        thickness: np.ndarray,
        material: MaterialProperties,
    ) -> np.ndarray:
        """Estimate temperature: T = T_mold + (T_melt - T_mold) * exp(-t/tau).

        tau ~ h^2 / (4 * alpha), alpha ≈ 0.1 mm²/s for polymers/silicones.
        For exothermic curing materials (silicone, epoxy), add heat generation.
        """
        T_inlet = material.temperature
        T_mold = 25.0  # ambient mold temperature
        alpha = 0.1  # thermal diffusivity mm^2/s

        safe_thick = np.where(voxels & (thickness > 0), thickness, 1.0)
        tau = safe_thick ** 2 / (4.0 * alpha)
        tau = np.clip(tau, 0.1, 1e6)

        safe_ft = np.where(voxels & (fill_time < np.inf), fill_time, 0.0)
        decay = np.exp(-safe_ft / tau)

        temperature = np.where(
            voxels,
            T_mold + (T_inlet - T_mold) * decay,
            T_mold,
        )

        # Exothermic curing heat for reactive systems
        is_curing = material.cure_time > 1.0  # minutes
        if is_curing:
            exo_peak = 10.0  # exothermic temperature rise in °C
            cure_time_s = material.cure_time * 60.0
            t_frac = np.clip(safe_ft / max(cure_time_s * 0.3, 1.0), 0.0, 1.0)
            exo = exo_peak * t_frac * np.exp(1.0 - t_frac)
            temperature = np.where(voxels, temperature + exo, temperature)

        return temperature

    # ── Cure progress estimation ─────────────────────────────────────

    def _compute_cure_progress(
        self,
        fill_time: np.ndarray,
        voxels: np.ndarray,
        temperature: np.ndarray | None,
        material: MaterialProperties,
    ) -> np.ndarray:
        """Estimate cure progress (0-1): Kamal-Sourour simplified model.

        alpha(t) = 1 - exp(-k * t_cure) where k depends on temperature.
        """
        cure_time_s = material.cure_time * 60.0
        if cure_time_s < 1.0:
            return np.where(voxels, 1.0, 0.0)

        safe_ft = np.where(voxels & (fill_time < np.inf), fill_time, 0.0)

        # Base reaction rate at reference temperature
        k_base = 2.0 / cure_time_s  # rate constant such that ~86% cured at cure_time

        k = k_base
        if temperature is not None:
            T_ref = material.temperature
            E_a_over_R = 5000.0  # activation energy / R, typical for silicone
            safe_temp = np.where(voxels, temperature, T_ref)
            k = k_base * np.exp(E_a_over_R * (1.0 / (T_ref + 273.15) - 1.0 / (safe_temp + 273.15)))

        progress = np.where(
            voxels,
            1.0 - np.exp(-k * safe_ft),
            0.0,
        )
        return np.clip(progress, 0.0, 1.0)

    # ── Analysis report ──────────────────────────────────────────────

    def _compute_analysis_report(
        self,
        voxels: np.ndarray,
        fill_time: np.ndarray,
        pressure: np.ndarray,
        vel_mag: np.ndarray,
        thickness: np.ndarray,
        shear_rate: np.ndarray | None,
        temperature: np.ndarray | None,
        cure_progress: np.ndarray | None,
        origin: np.ndarray,
        pitch: float,
        fill_fraction: float,
        defects: list[FlowDefect],
        material: MaterialProperties,
        gate_voxel: tuple[int, int, int],
    ) -> AnalysisReport:
        report = AnalysisReport()
        filled = voxels & (fill_time < np.inf)
        cavity_count = int(np.sum(voxels))

        # Fill quality score
        defect_penalty = sum(d.severity * 0.15 for d in defects)
        report.fill_quality_score = max(0.0, fill_fraction * 0.7 + (1.0 - min(defect_penalty, 1.0)) * 0.3)

        # Fill uniformity
        ft_filled = fill_time[filled]
        if len(ft_filled) > 1:
            ft_valid = ft_filled[ft_filled < np.inf]
            if len(ft_valid) > 1:
                cv = float(np.std(ft_valid) / max(np.mean(ft_valid), 1e-8))
                report.fill_uniformity_index = max(0.0, 1.0 - min(cv, 2.0) / 2.0)

        # Pressure uniformity
        p_filled = pressure[filled]
        if len(p_filled) > 1 and np.max(p_filled) > 0:
            p_cv = float(np.std(p_filled) / max(np.mean(p_filled), 1e-8))
            report.pressure_uniformity_index = max(0.0, 1.0 - min(p_cv, 2.0) / 2.0)

        # Velocity uniformity
        v_filled = vel_mag[filled]
        if len(v_filled) > 1:
            v_pos = v_filled[v_filled > 0]
            if len(v_pos) > 1:
                v_cv = float(np.std(v_pos) / max(np.mean(v_pos), 1e-8))
                report.velocity_uniformity_index = max(0.0, 1.0 - min(v_cv, 2.0) / 2.0)

        # Shear rate stats
        if shear_rate is not None:
            sr_filled = shear_rate[filled]
            if len(sr_filled) > 0:
                report.max_shear_rate = float(np.max(sr_filled))
                report.avg_shear_rate = float(np.mean(sr_filled[sr_filled > 0])) if np.any(sr_filled > 0) else 0.0
                high_shear_threshold = report.avg_shear_rate * 3.0 if report.avg_shear_rate > 0 else 1e6
                high_shear_mask = filled & (shear_rate > high_shear_threshold)
                labeled_hs, n_hs = ndimage.label(high_shear_mask)
                report.n_high_shear_zones = n_hs

        # Temperature stats
        if temperature is not None:
            t_filled = temperature[filled]
            if len(t_filled) > 0:
                report.temperature_range = (float(np.min(t_filled)), float(np.max(t_filled)))
                report.avg_temperature = float(np.mean(t_filled))

        # Cure progress stats
        if cure_progress is not None:
            cp_filled = cure_progress[filled]
            if len(cp_filled) > 0:
                report.cure_progress_range = (float(np.min(cp_filled)), float(np.max(cp_filled)))
                report.avg_cure_progress = float(np.mean(cp_filled))

        # Thickness analysis
        th_filled = thickness[filled]
        if len(th_filled) > 0:
            th_pos = th_filled[th_filled > 0]
            if len(th_pos) > 0:
                report.min_thickness = float(np.min(th_pos))
                report.max_thickness = float(np.max(th_pos))
                report.avg_thickness = float(np.mean(th_pos))
                thin_threshold = report.avg_thickness * 0.4
                thick_threshold = report.avg_thickness * 2.5
                report.thin_wall_fraction = float(np.sum(th_pos < thin_threshold)) / len(th_pos)
                report.thick_wall_fraction = float(np.sum(th_pos > thick_threshold)) / len(th_pos)

        # Flow length ratio (max distance from gate / model characteristic length)
        if np.any(filled):
            gate_arr = np.array(gate_voxel)
            filled_coords = np.argwhere(filled)
            dists_from_gate = np.linalg.norm(filled_coords - gate_arr, axis=1) * pitch
            max_flow_len = float(np.max(dists_from_gate))
            char_len = float(np.cbrt(cavity_count)) * pitch
            report.flow_length_ratio = max_flow_len / max(char_len, 1e-8)

        # Fill balance: compare fill times in 8 octants
        if np.any(filled):
            center = np.mean(np.argwhere(voxels).astype(float), axis=0)
            octant_times: list[float] = []
            for sx in (-1, 1):
                for sy in (-1, 1):
                    for sz in (-1, 1):
                        mask = (
                            filled
                            & (np.arange(voxels.shape[0])[:, None, None] * sx >= center[0] * sx)
                            & (np.arange(voxels.shape[1])[None, :, None] * sy >= center[1] * sy)
                            & (np.arange(voxels.shape[2])[None, None, :] * sz >= center[2] * sz)
                        )
                        ft_oct = fill_time[mask]
                        ft_oct = ft_oct[ft_oct < np.inf]
                        if len(ft_oct) > 0:
                            octant_times.append(float(np.mean(ft_oct)))
            if len(octant_times) >= 2:
                oct_std = float(np.std(octant_times))
                oct_mean = float(np.mean(octant_times))
                report.fill_balance_score = max(0.0, 1.0 - oct_std / max(oct_mean, 1e-8))

        # Gate efficiency: fill fraction achieved per unit pressure
        max_p = float(np.max(pressure[voxels])) if np.any(voxels) else 1.0
        report.gate_efficiency = fill_fraction / max(max_p / 1e6, 1e-8) if max_p > 0 else 0.0
        report.gate_efficiency = min(report.gate_efficiency, 1.0)

        # Stagnation zones
        if len(v_filled) > 0 and np.any(v_filled > 0):
            v_p5 = float(np.percentile(v_filled[v_filled > 0], 5))
            stag_mask = filled & (vel_mag < v_p5 * 0.3) & (vel_mag >= 0)
            labeled_st, n_st = ndimage.label(stag_mask)
            report.n_stagnation_zones = n_st

        # Recommendations
        report.recommendations = self._generate_recommendations(
            report, defects, fill_fraction, material
        )

        return report

    def _generate_recommendations(
        self,
        report: AnalysisReport,
        defects: list[FlowDefect],
        fill_fraction: float,
        material: MaterialProperties,
    ) -> list[str]:
        recs: list[str] = []

        if fill_fraction < 0.95:
            recs.append("充填率不足 95%，建议增大浇口直径或添加辅助浇口以改善流动性")
        if report.fill_uniformity_index < 0.5:
            recs.append("充填均匀性较差，建议优化浇口位置以平衡流动路径")
        if report.fill_balance_score < 0.5:
            recs.append("八分体充填不平衡，考虑调整浇口到更靠近几何中心的位置")
        if report.thin_wall_fraction > 0.15:
            recs.append(f"薄壁区域占比 {report.thin_wall_fraction:.0%}，可能导致充填困难和缺陷")
        if report.thick_wall_fraction > 0.1:
            recs.append(f"厚壁区域占比 {report.thick_wall_fraction:.0%}，存在缩痕和气泡风险")
        if report.n_stagnation_zones > 3:
            recs.append(f"检测到 {report.n_stagnation_zones} 个滞流区，建议增加排气孔")
        if report.n_high_shear_zones > 2:
            recs.append(f"检测到 {report.n_high_shear_zones} 个高剪切区，可能损伤材料")

        for d in defects:
            if d.defect_type == "air_trap" and d.severity > 0.3:
                recs.append("严重气穴缺陷，建议在对应位置增加排气孔或调整排气系统")
            elif d.defect_type == "weld_line" and d.severity > 0.5:
                recs.append("明显熔接线缺陷，建议调整浇口位置或增加浇口数量")

        if report.avg_cure_progress > 0.3 and material.cure_time > 0:
            recs.append("充填期间固化进度较高，建议缩短充填时间或降低材料温度")
        if report.flow_length_ratio > 5.0:
            recs.append("流动长径比过大，建议增加辅助浇口或调整浇口位置")

        if not recs:
            recs.append("仿真结果良好，未发现明显需要优化的问题")

        return recs

    # ── Visualization data extraction ────────────────────────────────

    def extract_visualization_data(self, result: SimulationResult) -> dict | None:
        """Extract point-cloud visualization data from simulation result."""
        if result.voxel_mask is None or result.voxel_origin is None:
            return None

        voxels = result.voxel_mask
        origin = result.voxel_origin
        pitch = result.voxel_pitch
        filled = voxels & (result.fill_time_field < np.inf) if result.fill_time_field is not None else voxels

        coords = np.argwhere(filled)
        if len(coords) == 0:
            return None

        positions = (origin + coords * pitch).tolist()

        max_ft = 1.0
        fill_times: list[float] = []
        if result.fill_time_field is not None:
            ft_vals = result.fill_time_field[filled]
            ft_finite = ft_vals[ft_vals < np.inf]
            max_ft = float(np.max(ft_finite)) if len(ft_finite) > 0 else 1.0
            fill_times = [
                round(min(float(v) / max_ft, 1.0), 4) if v < np.inf else 1.0
                for v in ft_vals
            ]

        pressures: list[float] = []
        max_p = 1.0
        if result.pressure_field is not None:
            p_vals = result.pressure_field[filled]
            max_p = float(np.max(p_vals)) if np.max(p_vals) > 0 else 1.0
            pressures = [round(float(v) / max_p, 4) for v in p_vals]

        velocities: list[float] = []
        max_v = 1.0
        if result.velocity_magnitude is not None:
            v_vals = result.velocity_magnitude[filled]
            max_v = float(np.max(v_vals)) if np.max(v_vals) > 0 else 1.0
            velocities = [round(float(v) / max_v, 4) for v in v_vals]

        shear_rates: list[float] = []
        max_sr = 1.0
        if result.shear_rate_field is not None:
            sr_vals = result.shear_rate_field[filled]
            max_sr = float(np.max(sr_vals)) if np.max(sr_vals) > 0 else 1.0
            shear_rates = [round(float(v) / max_sr, 4) for v in sr_vals]

        temperatures: list[float] = []
        t_range = (0.0, 1.0)
        if result.temperature_field is not None:
            t_vals = result.temperature_field[filled]
            t_min, t_max = float(np.min(t_vals)), float(np.max(t_vals))
            t_range = (t_min, t_max)
            t_span = max(t_max - t_min, 1e-8)
            temperatures = [round((float(v) - t_min) / t_span, 4) for v in t_vals]

        cure_values: list[float] = []
        if result.cure_progress_field is not None:
            cp_vals = result.cure_progress_field[filled]
            cure_values = [round(float(v), 4) for v in cp_vals]

        thickness_values: list[float] = []
        max_th = 1.0
        if result.thickness_field is not None:
            th_vals = result.thickness_field[filled]
            max_th = float(np.max(th_vals)) if np.max(th_vals) > 0 else 1.0
            thickness_values = [round(float(v) / max_th, 4) for v in th_vals]

        defect_positions: list[dict] = []
        for d in result.defects:
            if d.position is not None:
                defect_positions.append({
                    "type": d.defect_type,
                    "position": d.position.tolist(),
                    "severity": round(float(d.severity), 3),
                })

        sf = _safe_float
        return {
            "n_points": len(positions),
            "positions": positions,
            "fill_times": fill_times,
            "pressures": pressures,
            "velocities": velocities,
            "shear_rates": shear_rates,
            "temperatures": temperatures,
            "cure_progress": cure_values,
            "thickness": thickness_values,
            "max_fill_time": round(sf(max_ft), 3),
            "max_pressure": round(sf(max_p), 2),
            "max_velocity": round(sf(max_v), 4),
            "max_shear_rate": round(sf(max_sr), 2),
            "temperature_range": [round(sf(t_range[0]), 1), round(sf(t_range[1]), 1)],
            "max_thickness": round(sf(max_th), 2),
            "voxel_pitch": round(sf(pitch), 3),
            "defect_positions": defect_positions,
        }

    def extract_cross_section(
        self,
        result: SimulationResult,
        axis: str = "z",
        position: float = 0.5,
        field_name: str = "fill_time",
    ) -> dict | None:
        """Extract a 2D cross-section slice from a simulation field."""
        field_map = {
            "fill_time": result.fill_time_field,
            "pressure": result.pressure_field,
            "velocity": result.velocity_magnitude,
            "shear_rate": result.shear_rate_field,
            "temperature": result.temperature_field,
            "cure_progress": result.cure_progress_field,
            "thickness": result.thickness_field,
        }
        field_data = field_map.get(field_name)
        if field_data is None or result.voxel_mask is None:
            return None

        shape = field_data.shape
        axis_idx = {"x": 0, "y": 1, "z": 2}.get(axis, 2)
        slice_idx = int(np.clip(position * shape[axis_idx], 0, shape[axis_idx] - 1))

        if axis_idx == 0:
            slice_2d = field_data[slice_idx, :, :]
            mask_2d = result.voxel_mask[slice_idx, :, :]
        elif axis_idx == 1:
            slice_2d = field_data[:, slice_idx, :]
            mask_2d = result.voxel_mask[:, slice_idx, :]
        else:
            slice_2d = field_data[:, :, slice_idx]
            mask_2d = result.voxel_mask[:, :, slice_idx]

        vals = slice_2d[mask_2d]
        finite_vals = vals[(vals < np.inf) & np.isfinite(vals)]
        vmin = float(np.min(finite_vals)) if len(finite_vals) > 0 else 0.0
        vmax = float(np.max(finite_vals)) if len(finite_vals) > 0 else 1.0
        span = max(vmax - vmin, 1e-8)

        normalized = np.where(
            mask_2d & np.isfinite(slice_2d),
            np.clip((slice_2d - vmin) / span, 0.0, 1.0),
            -1.0,
        )

        h, w = normalized.shape
        pixels: list[list[float]] = []
        for row in range(h):
            pixels.append([round(float(normalized[row, col]), 3) for col in range(w)])

        return {
            "axis": axis,
            "slice_index": slice_idx,
            "field": field_name,
            "width": w,
            "height": h,
            "value_range": [round(vmin, 4), round(vmax, 4)],
            "pixels": pixels,
        }

    # ── Surface-mapped simulation data ────────────────────────────────

    def extract_surface_mapped_data(
        self,
        result: SimulationResult,
        mesh: MeshData,
        field_name: str = "fill_time",
    ) -> dict | None:
        """Project volumetric simulation field onto mesh surface vertices via nearest voxel lookup."""
        if result.voxel_mask is None or result.voxel_origin is None:
            return None

        field_map = {
            "fill_time": result.fill_time_field,
            "pressure": result.pressure_field,
            "velocity": result.velocity_magnitude,
            "shear_rate": result.shear_rate_field,
            "temperature": result.temperature_field,
            "cure_progress": result.cure_progress_field,
            "thickness": result.thickness_field,
        }
        field_data = field_map.get(field_name)
        if field_data is None:
            return None

        origin = result.voxel_origin
        pitch = result.voxel_pitch
        mask = result.voxel_mask
        shape = np.array(field_data.shape)

        tm = mesh.to_trimesh()
        verts = np.asarray(tm.vertices, dtype=np.float64)
        n_verts = len(verts)

        voxel_coords = ((verts - origin) / pitch).astype(np.int64)
        voxel_coords = np.clip(voxel_coords, 0, shape - 1)

        values = np.zeros(n_verts)
        for vi in range(n_verts):
            ix, iy, iz = voxel_coords[vi]
            if mask[ix, iy, iz]:
                values[vi] = float(field_data[ix, iy, iz])
            else:
                for d in range(1, 4):
                    found = False
                    for dx in range(-d, d + 1):
                        for dy in range(-d, d + 1):
                            for dz in range(-d, d + 1):
                                nx = max(0, min(ix + dx, shape[0] - 1))
                                ny = max(0, min(iy + dy, shape[1] - 1))
                                nz = max(0, min(iz + dz, shape[2] - 1))
                                if mask[nx, ny, nz]:
                                    values[vi] = float(field_data[nx, ny, nz])
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break
                    if found:
                        break

        finite_mask = np.isfinite(values) & (values < 1e10)
        safe_values = np.where(finite_mask, values, 0.0)
        vmin = float(np.min(safe_values[finite_mask])) if np.any(finite_mask) else 0.0
        vmax = float(np.max(safe_values[finite_mask])) if np.any(finite_mask) else 1.0
        span = max(vmax - vmin, 1e-8)
        normalized = np.clip((safe_values - vmin) / span, 0.0, 1.0)

        sf = _safe_float
        return {
            "field": field_name,
            "n_vertices": n_verts,
            "values": [round(sf(float(v)), 4) for v in normalized],
            "raw_min": round(sf(vmin), 4),
            "raw_max": round(sf(vmax), 4),
            "vertex_positions": verts.tolist(),
            "faces": tm.faces.tolist(),
        }

    # ── Voxelization ─────────────────────────────────────────────────

    def _voxelize(
        self, tm: trimesh.Trimesh, resolution: int,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        bounds = tm.bounds
        extents = bounds[1] - bounds[0]
        max_extent = float(np.max(extents))
        pitch = max_extent / resolution

        origin = bounds[0] - pitch * 2
        grid_shape = tuple(int(np.ceil(e / pitch)) + 4 for e in extents)

        try:
            vox = tm.voxelized(pitch)
            matrix = vox.matrix
            padded = np.zeros(grid_shape, dtype=bool)
            s = matrix.shape
            padded[2:2 + s[0], 2:2 + s[1], 2:2 + s[2]] = matrix
            return padded, origin, pitch
        except Exception:
            pass

        grid = np.zeros(grid_shape, dtype=bool)
        ix, iy, iz = np.meshgrid(
            np.arange(grid_shape[0]),
            np.arange(grid_shape[1]),
            np.arange(grid_shape[2]),
            indexing="ij",
        )
        pts = origin + np.stack([ix, iy, iz], axis=-1).reshape(-1, 3) * pitch
        chunk_size = 50_000
        inside = np.zeros(len(pts), dtype=bool)
        for ci in range(0, len(pts), chunk_size):
            inside[ci:ci + chunk_size] = tm.contains(pts[ci:ci + chunk_size])
        grid = inside.reshape(grid_shape)
        return grid, origin, pitch

    def _world_to_voxel(
        self, world_pos: np.ndarray, origin: np.ndarray, pitch: float,
        shape: tuple,
    ) -> tuple[int, int, int]:
        idx = ((np.asarray(world_pos) - origin) / pitch).astype(int)
        idx = np.clip(idx, 0, np.array(shape) - 1)
        return (int(idx[0]), int(idx[1]), int(idx[2]))

    def _solve_pressure_vectorized(
        self, voxels: np.ndarray, K: np.ndarray,
        gate_voxel: tuple[int, int, int],
        material: MaterialProperties,
    ) -> np.ndarray:
        """Solve Laplace equation for pressure with vectorized matrix assembly."""
        shape = voxels.shape
        n_voxels = int(np.sum(voxels))

        if n_voxels == 0:
            return np.zeros(shape)

        voxel_to_idx = np.full(shape, -1, dtype=np.int32)
        cavity_coords = np.argwhere(voxels)
        voxel_to_idx[cavity_coords[:, 0], cavity_coords[:, 1], cavity_coords[:, 2]] = np.arange(n_voxels)

        viscosity = material.viscosity / 1000.0

        gate_idx = voxel_to_idx[gate_voxel[0], gate_voxel[1], gate_voxel[2]]
        if gate_idx < 0:
            dists = np.linalg.norm(cavity_coords - np.array(gate_voxel), axis=1)
            gate_linear = int(np.argmin(dists))
        else:
            gate_linear = int(gate_idx)

        neighbors_offsets = np.array([
            [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1],
        ])

        rows_list: list[np.ndarray] = []
        cols_list: list[np.ndarray] = []
        vals_list: list[np.ndarray] = []
        rhs = np.zeros(n_voxels)

        rhs[gate_linear] = material.max_pressure * 1e6

        for offset in neighbors_offsets:
            neighbor_coords = cavity_coords + offset
            valid = (
                (neighbor_coords[:, 0] >= 0) & (neighbor_coords[:, 0] < shape[0])
                & (neighbor_coords[:, 1] >= 0) & (neighbor_coords[:, 1] < shape[1])
                & (neighbor_coords[:, 2] >= 0) & (neighbor_coords[:, 2] < shape[2])
            )
            valid_nc = neighbor_coords[valid]
            j_indices = voxel_to_idx[valid_nc[:, 0], valid_nc[:, 1], valid_nc[:, 2]]
            connected = j_indices >= 0

            src_global = np.arange(n_voxels)[valid][connected]
            dst_global = j_indices[connected]

            k_src = K[cavity_coords[src_global, 0], cavity_coords[src_global, 1], cavity_coords[src_global, 2]]
            k_dst = K[valid_nc[connected, 0], valid_nc[connected, 1], valid_nc[connected, 2]]
            k_avg = 0.5 * (k_src + k_dst)
            coeff = k_avg / max(viscosity, 1e-10)

            rows_list.append(src_global)
            cols_list.append(dst_global)
            vals_list.append(coeff)

        if rows_list:
            off_rows = np.concatenate(rows_list)
            off_cols = np.concatenate(cols_list)
            off_vals = np.concatenate(vals_list)
        else:
            off_rows = np.array([], dtype=int)
            off_cols = np.array([], dtype=int)
            off_vals = np.array([], dtype=float)

        diag_vals = np.zeros(n_voxels)
        np.add.at(diag_vals, off_rows, -off_vals)

        gate_mask = off_rows == gate_linear
        off_vals[gate_mask] = 0.0
        diag_vals[gate_linear] = 1.0

        all_rows = np.concatenate([off_rows, np.arange(n_voxels)])
        all_cols = np.concatenate([off_cols, np.arange(n_voxels)])
        all_vals = np.concatenate([off_vals, diag_vals])

        A = sparse.csr_matrix((all_vals, (all_rows, all_cols)), shape=(n_voxels, n_voxels))

        try:
            p_vec = spsolve(A, rhs)
            if np.any(~np.isfinite(p_vec)):
                logger.warning("Sparse solve returned NaN/inf, falling back to zeros")
                p_vec = np.nan_to_num(p_vec, nan=0.0, posinf=0.0, neginf=0.0)
        except Exception:
            logger.warning("Sparse solve failed, using zeros")
            p_vec = np.zeros(n_voxels)

        pressure = np.zeros(shape)
        pressure[cavity_coords[:, 0], cavity_coords[:, 1], cavity_coords[:, 2]] = p_vec
        return pressure

    def _simulate_fill_dijkstra(
        self, voxels: np.ndarray, vel_mag: np.ndarray,
        gate_voxel: tuple[int, int, int], pitch: float,
        material: MaterialProperties,
    ) -> tuple[np.ndarray, list[np.ndarray]]:
        """Dijkstra-based fill front propagation."""
        shape = voxels.shape
        fill_time = np.full(shape, np.inf)

        if not voxels[gate_voxel]:
            cavity_coords = np.argwhere(voxels)
            if len(cavity_coords) == 0:
                return fill_time, []
            dists = np.linalg.norm(cavity_coords - np.array(gate_voxel), axis=1)
            nearest = cavity_coords[int(np.argmin(dists))]
            gate_voxel = (int(nearest[0]), int(nearest[1]), int(nearest[2]))

        fill_time[gate_voxel] = 0.0

        heap: list[tuple[float, tuple[int, int, int]]] = [(0.0, gate_voxel)]
        neighbors = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))

        while heap:
            t_curr, (x, y, z) = heapq.heappop(heap)
            if t_curr > fill_time[x, y, z]:
                continue

            for dx, dy, dz in neighbors:
                nx, ny, nz = x + dx, y + dy, z + dz
                if (0 <= nx < shape[0] and 0 <= ny < shape[1]
                        and 0 <= nz < shape[2] and voxels[nx, ny, nz]):
                    v = max(vel_mag[nx, ny, nz], 1e-6)
                    dt = pitch / v
                    new_time = t_curr + dt
                    if new_time < fill_time[nx, ny, nz]:
                        fill_time[nx, ny, nz] = new_time
                        heapq.heappush(heap, (new_time, (nx, ny, nz)))

        filled_times = fill_time[voxels & (fill_time < np.inf)]
        frames = []
        if len(filled_times) > 0:
            max_t = float(np.max(filled_times))
            n_frames = min(self.config.animation_frames, self.config.time_steps)
            for i in range(n_frames):
                t = max_t * (i + 1) / n_frames
                frame = (fill_time <= t) & voxels
                frames.append(frame.astype(np.uint8))

        return fill_time, frames

    def _detect_defects(
        self, voxels: np.ndarray, fill_time: np.ndarray,
        pressure: np.ndarray, vel_mag: np.ndarray,
        origin: np.ndarray, pitch: float, fill_fraction: float,
    ) -> list[FlowDefect]:
        defects: list[FlowDefect] = []
        cavity_count = int(np.sum(voxels))

        if fill_fraction < 0.99:
            unfilled = voxels & (fill_time >= np.inf)
            n_unfilled = int(np.sum(unfilled))
            if n_unfilled > 0:
                coords = np.argwhere(unfilled)
                center = origin + coords.mean(axis=0) * pitch
                defects.append(FlowDefect(
                    defect_type="short_shot",
                    position=center,
                    severity=1.0 - fill_fraction,
                    description=f"Fill {fill_fraction:.1%}, {n_unfilled}/{cavity_count} unfilled",
                ))

        if self.config.detect_air_traps:
            filled = voxels & (fill_time < np.inf)
            unfilled_cavity = voxels & ~filled
            if np.any(unfilled_cavity):
                labeled, n_regions = ndimage.label(unfilled_cavity)
                for r in range(1, min(n_regions + 1, 20)):
                    region = labeled == r
                    region_size = int(np.sum(region))
                    if region_size < 3:
                        continue
                    dilated = ndimage.binary_dilation(region)
                    boundary = dilated & ~region & voxels
                    if np.all(filled[boundary]) if np.any(boundary) else False:
                        coords = np.argwhere(region)
                        center = origin + coords.mean(axis=0) * pitch
                        defects.append(FlowDefect(
                            defect_type="air_trap",
                            position=center,
                            severity=min(region_size / max(cavity_count * 0.01, 1), 1.0),
                            description=f"Enclosed air pocket: {region_size} voxels",
                        ))

        if self.config.detect_weld_lines:
            filled_times = fill_time.copy()
            filled_times[~voxels | (fill_time >= np.inf)] = 0
            if np.any(filled_times > 0):
                grad = np.array(np.gradient(filled_times, pitch))
                grad_mag = np.sqrt(np.sum(grad ** 2, axis=0))
                active = voxels & (grad_mag > 0)
                if np.any(active):
                    p95 = float(np.percentile(grad_mag[active], 95))
                    weld_mask = active & (grad_mag > p95)
                    n_weld = int(np.sum(weld_mask))
                    if n_weld > 5:
                        coords = np.argwhere(weld_mask)
                        center = origin + coords.mean(axis=0) * pitch
                        defects.append(FlowDefect(
                            defect_type="weld_line",
                            position=center,
                            severity=min(n_weld / max(cavity_count * 0.02, 1), 1.0),
                            description=f"Potential weld line: {n_weld} voxels (gradient > {p95:.1f})",
                        ))

        filled_vel = vel_mag[voxels & (fill_time < np.inf)]
        if len(filled_vel) > 10:
            pos_vel = filled_vel[filled_vel > 0]
            p5 = float(np.percentile(pos_vel, 5)) if len(pos_vel) > 0 else 0
            slow_mask = voxels & (vel_mag < p5 * 0.5) & (vel_mag > 0)
            n_slow = int(np.sum(slow_mask))
            if n_slow > cavity_count * 0.05:
                coords = np.argwhere(slow_mask)
                center = origin + coords.mean(axis=0) * pitch
                defects.append(FlowDefect(
                    defect_type="slow_fill",
                    position=center,
                    severity=min(n_slow / max(cavity_count * 0.1, 1), 1.0),
                    description=f"Low velocity region: {n_slow} voxels",
                ))

        return defects
