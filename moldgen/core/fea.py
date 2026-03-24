"""简化有限元分析模块 — 结构应力/位移/Von Mises 分析
==============================================================

基于弹簧质量系统近似的 FEA 求解器:
  1. 将三角网格边转化为弹簧系统
  2. 施加压力载荷 (法向均布力) 或重力载荷
  3. 稀疏矩阵求解位移场
  4. 计算 Von Mises 应力、应变、安全系数
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy import sparse
from scipy.sparse.linalg import spsolve

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


def _safe_float(v: float) -> float:
    if math.isnan(v) or math.isinf(v):
        return 0.0
    return v


@dataclass
class FEAConfig:
    youngs_modulus: float = 2000.0     # MPa (silicone rubber ~1-10, PLA ~2500)
    poissons_ratio: float = 0.4
    density: float = 1.1e-6            # kg/mm³ (1.1 g/cm³)
    yield_strength: float = 40.0       # MPa (PLA ~40, silicone ~5)
    # Load conditions
    pressure_load: float = 0.1         # MPa — internal cavity pressure
    gravity: bool = True
    gravity_direction: list[float] = field(default_factory=lambda: [0, 0, -1])
    # Fixed boundary: bottom N% of vertices
    fixed_fraction: float = 0.1
    # Solver
    max_vertices: int = 50000


@dataclass
class FEAResult:
    displacement: np.ndarray           # (N, 3) vertex displacements
    displacement_magnitude: np.ndarray # (N,) |displacement|
    von_mises_stress: np.ndarray       # (N,) Von Mises per vertex
    strain_energy: np.ndarray          # (N,) strain energy density
    safety_factor: np.ndarray          # (N,) yield_strength / von_mises
    max_displacement: float = 0.0
    max_stress: float = 0.0
    min_safety_factor: float = 0.0
    avg_stress: float = 0.0
    total_strain_energy: float = 0.0
    n_vertices: int = 0

    def to_dict(self) -> dict:
        sf = _safe_float
        return {
            "n_vertices": self.n_vertices,
            "max_displacement_mm": round(sf(self.max_displacement), 4),
            "max_stress_mpa": round(sf(self.max_stress), 3),
            "min_safety_factor": round(sf(self.min_safety_factor), 2),
            "avg_stress_mpa": round(sf(self.avg_stress), 3),
            "total_strain_energy": round(sf(self.total_strain_energy), 4),
        }

    def to_visualization_dict(self) -> dict:
        sf = _safe_float
        n = self.n_vertices
        return {
            "n_vertices": n,
            "displacement_magnitude": [
                round(sf(float(self.displacement_magnitude[i])), 5) for i in range(n)
            ],
            "von_mises_stress": [
                round(sf(float(self.von_mises_stress[i])), 5) for i in range(n)
            ],
            "safety_factor": [
                round(sf(float(min(self.safety_factor[i], 99.0))), 3) for i in range(n)
            ],
            "strain_energy": [
                round(sf(float(self.strain_energy[i])), 5) for i in range(n)
            ],
            "max_displacement_mm": round(sf(self.max_displacement), 4),
            "max_stress_mpa": round(sf(self.max_stress), 3),
            "min_safety_factor": round(sf(self.min_safety_factor), 2),
        }


class FEASolver:
    """Simplified structural FEA using spring-mass network on triangle mesh."""

    def __init__(self, config: FEAConfig | None = None):
        self.config = config or FEAConfig()

    def analyze(self, mesh: MeshData) -> FEAResult:
        t0 = time.perf_counter()
        c = self.config

        tm = mesh.to_trimesh()
        try:
            tm.update_faces(tm.nondegenerate_faces())
        except (AttributeError, Exception):
            pass
        tm.remove_unreferenced_vertices()

        if len(tm.vertices) > c.max_vertices:
            try:
                tm = tm.simplify_quadric_decimation(c.max_vertices)
            except Exception:
                pass

        verts = np.asarray(tm.vertices, dtype=np.float64)
        faces = np.asarray(tm.faces, dtype=np.int64)
        normals = np.asarray(tm.vertex_normals, dtype=np.float64)
        n = len(verts)

        logger.info("FEA: %d vertices, %d faces", n, len(faces))

        edges = tm.edges_unique
        n_edges = len(edges)

        E = c.youngs_modulus
        nu = c.poissons_ratio
        spring_k_base = E / (1.0 - nu * nu)

        rows, cols, vals = [], [], []

        for ei in range(n_edges):
            i, j = int(edges[ei, 0]), int(edges[ei, 1])
            diff = verts[j] - verts[i]
            length = np.linalg.norm(diff)
            if length < 1e-10:
                continue

            k = spring_k_base / (length + 1e-8)
            direction = diff / length

            for d in range(3):
                kd = k * direction[d] * direction[d] + k * 0.3
                rows.append(i * 3 + d); cols.append(i * 3 + d); vals.append(kd)
                rows.append(j * 3 + d); cols.append(j * 3 + d); vals.append(kd)
                rows.append(i * 3 + d); cols.append(j * 3 + d); vals.append(-kd)
                rows.append(j * 3 + d); cols.append(i * 3 + d); vals.append(-kd)

        K = sparse.coo_matrix(
            (vals, (rows, cols)), shape=(n * 3, n * 3),
        ).tocsr()

        F = np.zeros(n * 3)

        if c.pressure_load > 0:
            face_areas = tm.area_faces if hasattr(tm, 'area_faces') else np.ones(len(faces))
            vert_area = np.zeros(n)
            for fi in range(len(faces)):
                for vi in faces[fi]:
                    vert_area[vi] += face_areas[fi] / 3.0

            for vi in range(n):
                force = normals[vi] * c.pressure_load * vert_area[vi]
                F[vi * 3]     += force[0]
                F[vi * 3 + 1] += force[1]
                F[vi * 3 + 2] += force[2]

        if c.gravity:
            g_dir = np.array(c.gravity_direction, dtype=np.float64)
            g_dir = g_dir / (np.linalg.norm(g_dir) + 1e-12)
            g_accel = 9810.0  # mm/s²
            mass_per_vert = c.density * mesh.volume / n if n > 0 else 0
            for vi in range(n):
                F[vi * 3]     += mass_per_vert * g_accel * g_dir[0]
                F[vi * 3 + 1] += mass_per_vert * g_accel * g_dir[1]
                F[vi * 3 + 2] += mass_per_vert * g_accel * g_dir[2]

        heights = verts @ np.array(c.gravity_direction, dtype=np.float64)
        h_min = float(np.min(heights))
        h_range = float(np.max(heights)) - h_min
        threshold = h_min + h_range * c.fixed_fraction
        fixed_verts = np.where(heights <= threshold)[0]
        if len(fixed_verts) == 0:
            fixed_verts = np.argsort(heights)[:max(3, n // 20)]

        fixed_dofs = []
        for vi in fixed_verts:
            fixed_dofs.extend([vi * 3, vi * 3 + 1, vi * 3 + 2])

        penalty = float(K.diagonal().max()) * 1e6
        for dof in fixed_dofs:
            K[dof, dof] += penalty
            F[dof] = 0.0

        try:
            u = spsolve(K, F)
            if np.any(~np.isfinite(u)):
                u = np.nan_to_num(u, nan=0.0, posinf=0.0, neginf=0.0)
        except Exception as e:
            logger.warning("FEA solve failed: %s", e)
            u = np.zeros(n * 3)

        displacement = u.reshape(n, 3)
        disp_mag = np.linalg.norm(displacement, axis=1)

        von_mises = np.zeros(n)
        strain_energy = np.zeros(n)

        for ei in range(n_edges):
            i, j = int(edges[ei, 0]), int(edges[ei, 1])
            diff_orig = verts[j] - verts[i]
            l0 = np.linalg.norm(diff_orig)
            if l0 < 1e-10:
                continue
            diff_def = diff_orig + displacement[j] - displacement[i]
            l1 = np.linalg.norm(diff_def)
            strain = (l1 - l0) / (l0 + 1e-12)
            stress = E * strain

            von_mises[i] += stress * stress
            von_mises[j] += stress * stress
            strain_energy[i] += 0.5 * stress * strain * l0
            strain_energy[j] += 0.5 * stress * strain * l0

        edge_count = np.zeros(n)
        for ei in range(n_edges):
            edge_count[edges[ei, 0]] += 1
            edge_count[edges[ei, 1]] += 1
        edge_count = np.maximum(edge_count, 1)

        von_mises = np.sqrt(von_mises / edge_count)
        strain_energy = strain_energy / edge_count

        max_vm = float(np.max(von_mises)) if np.any(von_mises > 0) else 1e-8
        von_mises_norm = von_mises / max_vm

        safety = np.where(
            von_mises > 1e-10,
            c.yield_strength / von_mises,
            99.0,
        )

        max_disp = float(np.max(disp_mag))
        max_stress = float(np.max(von_mises))
        min_sf = float(np.min(safety))
        avg_stress = float(np.mean(von_mises))
        total_se = float(np.sum(strain_energy))

        elapsed = time.perf_counter() - t0
        logger.info(
            "FEA complete: max_disp=%.4f mm, max_stress=%.2f MPa, "
            "min_SF=%.2f, %.2fs",
            max_disp, max_stress, min_sf, elapsed,
        )

        return FEAResult(
            displacement=displacement,
            displacement_magnitude=disp_mag,
            von_mises_stress=von_mises_norm,
            strain_energy=strain_energy,
            safety_factor=safety,
            max_displacement=max_disp,
            max_stress=max_stress,
            min_safety_factor=min_sf,
            avg_stress=avg_stress,
            total_strain_energy=total_se,
            n_vertices=n,
        )
