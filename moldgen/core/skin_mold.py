"""Skin mold generation for medical teaching models.

Workflow:
  1. Original model (e.g. arm) is the target shape.
  2. Core (模芯) = inward-offset solid, 3D-printed in hard material.
  3. Skin mold (蒙皮模具) = external mold wrapping the original surface.
  4. Pour silicone between core and mold → soft skin layer (蒙皮).

v2 upgrades:
  - Morphological closing + Gaussian EDT smoothing for robust core
  - Curvature-adaptive variable thickness
  - Collision-aware registration placement
  - Proper watertight hollow core via boolean
  - Mesh decimation for controllable face count
  - Per-vertex thickness map for visualization
  - Direction-aware drain holes
  - Core support pegs for stable positioning during pour

References:
  - Moldflow thin-wall injection: Hele-Shaw cavity-fill model
  - SolidWorks Mold Tools: core/cavity offset + parting surfaces
  - 3-matic (Materialise): anatomical model shell/offset operations
  - nTopology: implicit SDF offset + curvature field operations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import trimesh

from moldgen.core.boolean_ops import boolean_subtract, boolean_union
from moldgen.core.mesh_data import MeshData
from moldgen.core.mesh_repair import repair_trimesh as _repair_trimesh
from moldgen.core.mold_builder import MoldBuilder, MoldConfig, MoldResult

logger = logging.getLogger(__name__)

_MAX_CORE_FACES = 120_000
_MIN_VOXEL_FILL_RATIO = 0.01


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SkinMoldConfig:
    """All parameters for skin-mold generation."""

    # ── Skin layer ──
    skin_thickness: float = 3.0
    variable_thickness: bool = False
    min_skin_thickness: float = 2.0
    max_skin_thickness: float = 5.0
    curvature_influence: float = 0.5  # 0=uniform, 1=fully curvature-driven

    # ── Core (模芯) ──
    core_resolution: int = 64
    core_smoothing: int = 2
    core_clearance: float = 0.3
    core_shell_thickness: float = 0.0  # 0=solid; >0=hollow shell (mm)
    core_drain_holes: bool = False
    core_drain_diameter: float = 5.0
    core_drain_count: int = 2
    core_max_faces: int = _MAX_CORE_FACES
    core_morphological_closing: int = 2  # iterations of binary closing

    # ── Support pegs (支撑柱) ──
    add_support_pegs: bool = True
    peg_count: int = 3
    peg_diameter: float = 4.0
    peg_height: float = 6.0

    # ── Registration features (定位特征) ──
    registration_type: str = "pin"  # "pin" | "key"
    registration_count: int = 4
    registration_diameter: float = 5.0
    registration_height: float = 8.0
    registration_tolerance: float = 0.2
    registration_taper: float = 2.0

    # ── Outer mold (外模) ──
    mold_wall_thickness: float = 5.0
    mold_clearance: float = 0.15
    mold_shell_type: str = "box"
    mold_margin: float = 10.0
    parting_style: str = "flat"
    parting_surface_type: str = "flat"
    add_alignment_pins: bool = True
    add_screw_holes: bool = False
    screw_size: str = "M4"
    n_screws: int = 4


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RegistrationFeature:
    position: np.ndarray
    direction: np.ndarray
    diameter: float
    height: float
    feature_type: str = "pin"

    def to_dict(self) -> dict:
        return {
            "position": [round(float(v), 3) for v in self.position],
            "direction": [round(float(v), 3) for v in self.direction],
            "diameter": round(self.diameter, 2),
            "height": round(self.height, 2),
            "type": self.feature_type,
        }


@dataclass
class SkinMoldResult:
    core_mesh: MeshData
    mold_result: MoldResult
    registration_features: list[RegistrationFeature] = field(default_factory=list)
    skin_volume: float = 0.0
    core_volume: float = 0.0
    original_volume: float = 0.0
    skin_thickness_stats: dict = field(default_factory=dict)
    core_is_hollow: bool = False
    thickness_map: list[float] | None = None  # per-vertex thickness for visualization

    def to_dict(self) -> dict:
        d: dict = {
            "core": {
                "face_count": self.core_mesh.face_count,
                "vertex_count": self.core_mesh.vertex_count,
                "volume": round(self.core_volume, 2),
                "is_hollow": self.core_is_hollow,
            },
            "mold": self.mold_result.to_dict(),
            "registration": [f.to_dict() for f in self.registration_features],
            "skin_volume": round(self.skin_volume, 2),
            "original_volume": round(self.original_volume, 2),
            "skin_thickness_stats": self.skin_thickness_stats,
            "has_thickness_map": self.thickness_map is not None,
        }
        return d


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _align_cylinder(cyl: trimesh.Trimesh, direction: np.ndarray) -> None:
    """Rotate a Z-axis cylinder to align with *direction*."""
    z = np.array([0.0, 0.0, 1.0])
    if np.allclose(direction, z) or np.allclose(direction, -z):
        if np.dot(direction, z) < 0:
            cyl.apply_transform(
                trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]),
            )
        return
    axis = np.cross(z, direction)
    al = np.linalg.norm(axis)
    if al < 1e-9:
        return
    axis /= al
    angle = np.arccos(np.clip(np.dot(z, direction), -1, 1))
    cyl.apply_transform(trimesh.transformations.rotation_matrix(angle, axis))


def _safe_volume(tm: trimesh.Trimesh) -> float:
    try:
        return float(tm.volume) if tm.is_watertight else 0.0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class SkinMoldGenerator:
    """Generate a core + skin-mold pair for medical teaching models."""

    def __init__(self, config: SkinMoldConfig | None = None) -> None:
        self.config = config or SkinMoldConfig()

    # ── Public API ──

    def generate(
        self,
        model: MeshData,
        direction: np.ndarray | None = None,
    ) -> SkinMoldResult:
        """Full pipeline: core → registration → skin mold."""
        cfg = self.config
        if direction is None:
            direction = np.array([0.0, 0.0, 1.0])
        direction = direction / (np.linalg.norm(direction) + 1e-12)

        tm_model = model.to_trimesh()
        tm_model = self._ensure_quality(tm_model)
        original_volume = _safe_volume(tm_model)

        # 1. Build core
        logger.info(
            "Generating core: skin=%.1fmm, res=%d, variable=%s",
            cfg.skin_thickness, cfg.core_resolution, cfg.variable_thickness,
        )
        core_tm = self._generate_core(tm_model)
        if core_tm is None:
            raise ValueError(
                f"Core generation failed — model may be too thin for "
                f"skin_thickness={cfg.skin_thickness}mm."
            )
        core_volume = _safe_volume(core_tm)

        # 2. Optional hollow
        if cfg.core_shell_thickness > 0:
            core_tm = self._hollow_core(core_tm, direction)

        # 3. Support pegs on the core bottom (keeps core stable during pour)
        if cfg.add_support_pegs:
            core_tm = self._add_support_pegs(core_tm, tm_model, direction)

        # 4. Registration features
        reg_features = self._generate_registration(tm_model, core_tm, direction)
        core_tm = self._apply_registration_to_core(core_tm, reg_features)

        core_mesh = MeshData.from_trimesh(core_tm)

        # 5. Outer skin mold
        mold_result = self._generate_skin_mold(model, direction, reg_features)

        # 6. Thickness analysis
        skin_volume = max(0.0, original_volume - core_volume)
        thickness_stats, thickness_map = self._compute_thickness_analysis(
            tm_model, core_tm,
        )

        return SkinMoldResult(
            core_mesh=core_mesh,
            mold_result=mold_result,
            registration_features=reg_features,
            skin_volume=skin_volume,
            core_volume=core_volume,
            original_volume=original_volume,
            skin_thickness_stats=thickness_stats,
            core_is_hollow=cfg.core_shell_thickness > 0,
            thickness_map=thickness_map,
        )

    # ══════════════════════════════════════════════════════════════════
    #  Core Generation (v2: morphological closing + Gaussian smoothed EDT)
    # ══════════════════════════════════════════════════════════════════

    def _generate_core(self, tm_model: trimesh.Trimesh) -> trimesh.Trimesh | None:
        """Generate core via SDF-based inward offset.

        v2 improvements over v1:
        - Morphological binary closing before EDT (fills pinholes/cracks)
        - Gaussian smoothing on EDT field (eliminates voxel staircase)
        - Curvature-adaptive variable offset when enabled
        - Automatic mesh decimation to cap face count
        """
        from scipy.ndimage import (
            binary_closing,
            distance_transform_edt,
            gaussian_filter,
        )
        from skimage.measure import marching_cubes

        cfg = self.config
        offset = cfg.skin_thickness + cfg.core_clearance

        extents = tm_model.bounds[1] - tm_model.bounds[0]
        max_ext = float(np.max(extents))
        pitch = max_ext / cfg.core_resolution
        pad = 4

        origin = tm_model.bounds[0] - pitch * pad
        grid_shape = tuple(int(np.ceil(e / pitch)) + 2 * pad for e in extents)

        # Step 1: voxelize interior
        interior = self._voxelize_interior(tm_model, grid_shape, origin, pitch)
        fill_ratio = float(np.sum(interior)) / max(1, np.prod(grid_shape))
        if fill_ratio < _MIN_VOXEL_FILL_RATIO:
            logger.warning("Voxelization too sparse (%.4f), model may be non-watertight", fill_ratio)
            return None

        # Step 2: morphological closing (fill small holes and cracks)
        if cfg.core_morphological_closing > 0:
            interior = binary_closing(
                interior, iterations=cfg.core_morphological_closing,
            ).astype(bool)

        # Step 3: EDT with real-unit sampling
        edt = distance_transform_edt(interior, sampling=(pitch, pitch, pitch))

        # Step 4: Gaussian smooth the EDT to eliminate staircase artifacts
        sigma_voxels = 0.8
        edt_smooth = gaussian_filter(edt, sigma=sigma_voxels)
        edt_smooth[~interior] = 0.0

        # Step 5: determine iso-level (variable or uniform)
        if cfg.variable_thickness:
            level_field = self._compute_variable_offset_field(
                tm_model, edt_smooth, interior, origin, pitch, grid_shape,
            )
        else:
            level_field = None

        max_edt = float(np.max(edt_smooth))
        if max_edt < offset:
            logger.warning(
                "Model thin: max_edt=%.2f < offset=%.2f, reducing level",
                max_edt, offset,
            )
            offset = max(max_edt * 0.55, cfg.min_skin_thickness)
            if offset < cfg.min_skin_thickness * 0.5:
                return None

        # Step 6: marching cubes
        if level_field is not None:
            volume = edt_smooth - level_field
            volume[~interior] = -1.0
            level_val = 0.0
        else:
            volume = edt_smooth
            level_val = offset

        try:
            verts, faces, normals, _ = marching_cubes(
                volume, level=level_val,
                spacing=(pitch, pitch, pitch),
            )
        except Exception:
            logger.exception("Marching cubes failed for core")
            return None

        if len(faces) < 10:
            return None

        verts += origin
        core = trimesh.Trimesh(vertices=verts, faces=faces, process=True)

        # Step 7: Laplacian smoothing
        if cfg.core_smoothing > 0:
            try:
                trimesh.smoothing.filter_laplacian(
                    core, iterations=cfg.core_smoothing, lamb=0.5,
                )
            except Exception:
                pass

        # Step 8: decimation to keep face count manageable
        core = self._decimate_mesh(core, cfg.core_max_faces)

        # Step 9: repair
        _repair_trimesh(core)

        logger.info(
            "Core generated: %d faces, volume=%.1fmm³, pitch=%.3fmm",
            len(core.faces), _safe_volume(core), pitch,
        )
        return core

    def _compute_variable_offset_field(
        self,
        tm_model: trimesh.Trimesh,
        edt: np.ndarray,
        interior: np.ndarray,
        origin: np.ndarray,
        pitch: float,
        grid_shape: tuple,
    ) -> np.ndarray:
        """Build a per-voxel offset field based on surface curvature.

        High curvature (convex bumps like knuckles) → thicker skin
        Low curvature (flat areas like forearm) → thinner skin
        """
        from scipy.ndimage import gaussian_filter

        cfg = self.config
        t_min = cfg.min_skin_thickness + cfg.core_clearance
        t_max = cfg.max_skin_thickness + cfg.core_clearance
        alpha = cfg.curvature_influence

        # Compute discrete mean curvature at model vertices
        try:
            curv = trimesh.curvature.discrete_mean_curvature_measure(
                tm_model, tm_model.vertices, radius=pitch * 4,
            )
            curv = np.abs(curv)
        except Exception:
            logger.warning("Curvature computation failed, using uniform offset")
            return np.full(grid_shape, cfg.skin_thickness + cfg.core_clearance)

        # Normalize curvature to [0,1]
        c_max = float(np.percentile(curv, 97)) if len(curv) > 0 else 1e-6
        curv_norm = np.clip(curv / max(c_max, 1e-8), 0.0, 1.0)

        # Map curvature to offset: high curvature → thicker
        per_vert_offset = t_min + (t_max - t_min) * curv_norm * alpha
        per_vert_offset += (1.0 - alpha) * (cfg.skin_thickness + cfg.core_clearance)

        # Scatter vertex offsets to the voxel grid via nearest-neighbor
        offset_field = np.full(grid_shape, cfg.skin_thickness + cfg.core_clearance)
        coords = np.argwhere(interior)
        if len(coords) == 0:
            return offset_field

        world_pts = origin + coords.astype(np.float64) * pitch
        try:
            _, _, face_ids = tm_model.nearest.on_surface(world_pts)
            face_verts = tm_model.faces[face_ids]
            vert_offsets_at_faces = per_vert_offset[face_verts].mean(axis=1)
            for idx, c in enumerate(coords):
                offset_field[c[0], c[1], c[2]] = vert_offsets_at_faces[idx]
        except Exception:
            pass

        # Smooth the offset field for continuity
        offset_field = gaussian_filter(offset_field, sigma=1.5)

        return offset_field

    # ══════════════════════════════════════════════════════════════════
    #  Voxelization
    # ══════════════════════════════════════════════════════════════════

    def _voxelize_interior(
        self,
        tm: trimesh.Trimesh,
        grid_shape: tuple,
        origin: np.ndarray,
        pitch: float,
    ) -> np.ndarray:
        """Robust boolean voxel grid of model interior (filled, not surface-only)."""
        try:
            vox = tm.voxelized(pitch)
            # .fill() converts surface voxelization to solid interior
            try:
                filled = vox.fill()
                matrix = filled.matrix
            except Exception:
                from scipy.ndimage import binary_fill_holes
                matrix = binary_fill_holes(vox.matrix)

            padded = np.zeros(grid_shape, dtype=bool)
            s = matrix.shape
            ox = int(round((vox.transform[0, 3] - origin[0]) / pitch))
            oy = int(round((vox.transform[1, 3] - origin[1]) / pitch))
            oz = int(round((vox.transform[2, 3] - origin[2]) / pitch))
            ox = max(0, ox)
            oy = max(0, oy)
            oz = max(0, oz)
            sx = min(s[0], grid_shape[0] - ox)
            sy = min(s[1], grid_shape[1] - oy)
            sz = min(s[2], grid_shape[2] - oz)
            if sx > 0 and sy > 0 and sz > 0:
                padded[ox:ox + sx, oy:oy + sy, oz:oz + sz] = matrix[:sx, :sy, :sz]
            if np.any(padded):
                return padded
        except Exception:
            pass

        # Fallback: chunked point-in-mesh queries
        grid = np.zeros(grid_shape, dtype=bool)
        chunk_x = max(1, min(8, grid_shape[0]))
        for x0 in range(0, grid_shape[0], chunk_x):
            x1 = min(x0 + chunk_x, grid_shape[0])
            nx = x1 - x0
            yz = np.mgrid[0:grid_shape[1], 0:grid_shape[2]]
            n_yz = grid_shape[1] * grid_shape[2]
            for xi in range(nx):
                pts = np.column_stack([
                    np.full(n_yz, origin[0] + (x0 + xi) * pitch),
                    yz[0].ravel() * pitch + origin[1],
                    yz[1].ravel() * pitch + origin[2],
                ])
                try:
                    grid[x0 + xi] = tm.contains(pts).reshape(
                        grid_shape[1], grid_shape[2],
                    )
                except Exception:
                    pass

        return grid

    # ══════════════════════════════════════════════════════════════════
    #  Hollow Core (v2: boolean-based watertight)
    # ══════════════════════════════════════════════════════════════════

    def _hollow_core(
        self, core: trimesh.Trimesh, direction: np.ndarray,
    ) -> trimesh.Trimesh:
        """Create a watertight hollow shell via SDF offset + boolean."""
        from scipy.ndimage import distance_transform_edt, gaussian_filter
        from skimage.measure import marching_cubes

        cfg = self.config
        shell_t = cfg.core_shell_thickness

        extents = core.bounds[1] - core.bounds[0]
        max_ext = float(np.max(extents))
        pitch = max_ext / min(cfg.core_resolution, 80)
        pad = 3

        origin = core.bounds[0] - pitch * pad
        gs = tuple(int(np.ceil(e / pitch)) + 2 * pad for e in extents)

        interior = self._voxelize_interior(core, gs, origin, pitch)
        if not np.any(interior):
            return core

        edt = distance_transform_edt(interior, sampling=(pitch, pitch, pitch))
        edt = gaussian_filter(edt, sigma=0.6)
        edt[~interior] = 0.0

        if float(np.max(edt)) <= shell_t:
            logger.warning("Core too thin to hollow (max_edt=%.2f <= shell=%.2f)", np.max(edt), shell_t)
            return core

        try:
            verts, faces, _, _ = marching_cubes(
                edt, level=shell_t, spacing=(pitch, pitch, pitch),
            )
        except Exception:
            return core

        inner_core = trimesh.Trimesh(
            vertices=verts + origin, faces=faces, process=True,
        )
        inner_core = self._decimate_mesh(inner_core, cfg.core_max_faces // 2)

        # Boolean subtract inner from outer for watertight shell
        result = boolean_subtract(core, inner_core)
        if result is not None and len(result.faces) > 20:
            _repair_trimesh(result)
            if cfg.core_drain_holes:
                result = self._add_drain_holes(result, direction)
            logger.info(
                "Core hollowed: shell=%.1fmm, faces=%d",
                shell_t, len(result.faces),
            )
            return result

        logger.warning("Boolean hollow failed, keeping solid core")
        return core

    def _add_drain_holes(
        self, core: trimesh.Trimesh, direction: np.ndarray,
    ) -> trimesh.Trimesh:
        """Add drain holes at the bottom of a hollow core, direction-aware."""
        cfg = self.config
        n_holes = max(1, cfg.core_drain_count)
        centroid = core.centroid.copy()

        # "Bottom" is the negative direction side
        bottom_h = float(core.bounds[0] @ direction / (np.linalg.norm(direction) + 1e-12))
        # Project centroid onto direction
        c_h = float(centroid @ direction)
        base_center = centroid + direction * (bottom_h - c_h + 2.0)

        up = direction
        arb = np.array([1, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1, 0])
        u_ax = np.cross(up, arb)
        u_ax /= np.linalg.norm(u_ax) + 1e-12

        core_h = float(np.ptp(core.vertices @ direction))
        cyl_h = core_h * 0.4

        for i in range(n_holes):
            angle = 2.0 * np.pi * i / n_holes
            offset = u_ax * (cfg.core_drain_diameter * 1.5) * (1 if n_holes > 1 else 0)
            rot_offset = (
                offset * np.cos(angle)
                + np.cross(up, offset) * np.sin(angle)
            )

            cyl = trimesh.creation.cylinder(
                radius=cfg.core_drain_diameter / 2,
                height=cyl_h,
                sections=16,
            )
            _align_cylinder(cyl, direction)
            cyl.apply_translation(base_center + rot_offset)

            cut = boolean_subtract(core, cyl)
            if cut is not None and len(cut.faces) > 10:
                core = cut

        return core

    # ══════════════════════════════════════════════════════════════════
    #  Support Pegs (支撑柱 — holds core in position during pour)
    # ══════════════════════════════════════════════════════════════════

    def _add_support_pegs(
        self,
        core: trimesh.Trimesh,
        tm_model: trimesh.Trimesh,
        direction: np.ndarray,
    ) -> trimesh.Trimesh:
        """Add pegs extending from core bottom through the mold floor.

        These pegs keep the core suspended at the correct position while
        silicone is poured into the gap.
        """
        cfg = self.config
        n = cfg.peg_count
        if n <= 0:
            return core

        up = direction
        arb = np.array([1, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1, 0])
        u_ax = np.cross(up, arb)
        u_ax /= np.linalg.norm(u_ax) + 1e-12
        v_ax = np.cross(up, u_ax)
        v_ax /= np.linalg.norm(v_ax) + 1e-12

        # Bottom of core along direction
        core_heights = core.vertices @ direction
        bottom_h = float(np.min(core_heights))
        centroid = core.centroid.copy()

        # Peg placement radius: ~60% of model projection radius
        proj_u = core.vertices @ u_ax
        proj_v = core.vertices @ v_ax
        max_r = float(np.max(np.sqrt(proj_u ** 2 + proj_v ** 2)))
        peg_r = max_r * 0.55

        for i in range(n):
            angle = 2.0 * np.pi * i / n
            pos = (
                centroid
                + u_ax * peg_r * np.cos(angle)
                + v_ax * peg_r * np.sin(angle)
            )
            # Move to bottom of core along direction
            pos_h = float(pos @ direction)
            pos = pos + direction * (bottom_h - pos_h)

            peg = trimesh.creation.cylinder(
                radius=cfg.peg_diameter / 2,
                height=cfg.peg_height,
                sections=12,
            )
            _align_cylinder(peg, -direction)
            peg.apply_translation(pos - direction * cfg.peg_height / 2)

            merged = boolean_union(core, peg)
            if merged is not None and len(merged.faces) > len(core.faces) // 2:
                core = merged

        logger.info("Added %d support pegs (d=%.1fmm, h=%.1fmm)", n, cfg.peg_diameter, cfg.peg_height)
        return core

    # ══════════════════════════════════════════════════════════════════
    #  Registration Features (v2: collision-aware placement)
    # ══════════════════════════════════════════════════════════════════

    def _generate_registration(
        self,
        tm_model: trimesh.Trimesh,
        core: trimesh.Trimesh,
        direction: np.ndarray,
    ) -> list[RegistrationFeature]:
        """Place registration pins around parting plane, avoiding model collision."""
        cfg = self.config
        n = cfg.registration_count
        if n <= 0:
            return []

        center = tm_model.centroid.copy()
        parting_h = float(center @ direction)

        up = direction
        arb = np.array([1, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1, 0])
        u_ax = np.cross(up, arb)
        u_ax /= np.linalg.norm(u_ax) + 1e-12
        v_ax = np.cross(up, u_ax)
        v_ax /= np.linalg.norm(v_ax) + 1e-12

        # Compute per-angle max radius of the model projection
        verts = tm_model.vertices
        proj_u = verts @ u_ax
        proj_v = verts @ v_ax
        angles = np.arctan2(proj_v, proj_u)
        radii = np.sqrt(proj_u ** 2 + proj_v ** 2)

        n_angle_bins = max(n * 8, 32)
        angle_bins = np.linspace(-np.pi, np.pi, n_angle_bins + 1)
        max_r_per_bin = np.zeros(n_angle_bins)
        for bi in range(n_angle_bins):
            mask = (angles >= angle_bins[bi]) & (angles < angle_bins[bi + 1])
            if np.any(mask):
                max_r_per_bin[bi] = float(np.max(radii[mask]))

        features: list[RegistrationFeature] = []
        candidate_angles = np.linspace(0, 2 * np.pi, n * 12, endpoint=False)
        used_angles: list[float] = []
        min_sep = 2 * np.pi / (n * 1.5)

        for _ in range(n):
            best_angle = None
            best_clearance = -1.0

            for ca in candidate_angles:
                # Skip if too close to already-used angles
                if any(abs(ca - ua) < min_sep or abs(ca - ua - 2 * np.pi) < min_sep for ua in used_angles):
                    continue

                # Find model radius at this angle
                bi = int((ca + np.pi) / (2 * np.pi) * n_angle_bins) % n_angle_bins
                local_r = max_r_per_bin[bi]
                clearance = cfg.mold_wall_thickness - (local_r * 0.05)

                if clearance > best_clearance:
                    best_clearance = clearance
                    best_angle = ca

            if best_angle is None:
                best_angle = 2.0 * np.pi * len(features) / n + np.pi / n

            used_angles.append(best_angle)

            # Pin radius: model outline + margin
            bi = int((best_angle + np.pi) / (2 * np.pi) * n_angle_bins) % n_angle_bins
            local_r = max_r_per_bin[bi]
            pin_r = local_r + cfg.mold_wall_thickness * 0.45 + cfg.registration_diameter

            pos = (
                center
                + u_ax * pin_r * np.cos(best_angle)
                + v_ax * pin_r * np.sin(best_angle)
            )
            pos_h = float(pos @ direction)
            pos = pos + direction * (parting_h - pos_h)

            features.append(RegistrationFeature(
                position=pos,
                direction=direction.copy(),
                diameter=cfg.registration_diameter,
                height=cfg.registration_height,
                feature_type=cfg.registration_type,
            ))

        logger.info("Generated %d registration features (collision-aware)", n)
        return features

    def _apply_registration_to_core(
        self,
        core: trimesh.Trimesh,
        features: list[RegistrationFeature],
    ) -> trimesh.Trimesh:
        """Add registration pin/key geometry to core mesh."""
        cfg = self.config

        for feat in features:
            r = feat.diameter / 2.0 - cfg.registration_tolerance
            h = feat.height

            if feat.feature_type == "key":
                pin = trimesh.creation.box(
                    extents=[r * 1.6, r * 1.0, h],
                )
            else:
                pin = trimesh.creation.cylinder(radius=r, height=h, sections=16)

            _align_cylinder(pin, feat.direction)
            pin.apply_translation(feat.position + feat.direction * h / 2)

            merged = boolean_union(core, pin)
            if merged is not None and len(merged.faces) > len(core.faces) // 3:
                core = merged

        return core

    # ══════════════════════════════════════════════════════════════════
    #  Skin Mold Generation
    # ══════════════════════════════════════════════════════════════════

    def _generate_skin_mold(
        self,
        model: MeshData,
        direction: np.ndarray,
        reg_features: list[RegistrationFeature],
    ) -> MoldResult:
        """Generate outer mold. Cavity = original model surface."""
        cfg = self.config

        mold_cfg = MoldConfig(
            wall_thickness=cfg.mold_wall_thickness,
            clearance=cfg.mold_clearance,
            shell_type=cfg.mold_shell_type,
            margin=cfg.mold_margin,
            parting_style=cfg.parting_style,
            parting_surface_type=cfg.parting_surface_type,
            add_alignment_pins=cfg.add_alignment_pins,
            add_screw_holes=cfg.add_screw_holes,
            screw_size=cfg.screw_size,
            n_screws=cfg.n_screws,
        )

        builder = MoldBuilder(mold_cfg)
        mold = builder.build_two_part_mold(model, direction)

        # Cut registration receptacles + support peg holes into mold shells
        self._cut_registration_holes(mold, reg_features)
        if cfg.add_support_pegs:
            self._cut_support_peg_holes(mold, model, direction)

        return mold

    def _cut_registration_holes(
        self,
        mold: MoldResult,
        features: list[RegistrationFeature],
    ) -> None:
        """Subtract registration clearance holes from mold shells."""
        cfg = self.config
        for feat in features:
            r = feat.diameter / 2 + cfg.registration_tolerance
            h = feat.height + 5.0

            if feat.feature_type == "key":
                half_w = (feat.diameter / 2 + cfg.registration_tolerance) * 1.6
                half_d = (feat.diameter / 2 + cfg.registration_tolerance) * 1.0
                hole = trimesh.creation.box(extents=[half_w, half_d, h])
            else:
                hole = trimesh.creation.cylinder(radius=r, height=h, sections=16)

            _align_cylinder(hole, feat.direction)
            hole.apply_translation(feat.position + feat.direction * h / 2)

            for sh in mold.shells:
                tm_sh = sh.mesh.to_trimesh()
                cut = boolean_subtract(tm_sh, hole)
                if cut is not None and len(cut.faces) > 10:
                    sh.mesh = MeshData.from_trimesh(cut)

    def _cut_support_peg_holes(
        self,
        mold: MoldResult,
        model: MeshData,
        direction: np.ndarray,
    ) -> None:
        """Cut clearance holes for support pegs through the bottom mold shell."""
        cfg = self.config
        tm_model = model.to_trimesh()
        up = direction
        arb = np.array([1, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1, 0])
        u_ax = np.cross(up, arb)
        u_ax /= np.linalg.norm(u_ax) + 1e-12
        v_ax = np.cross(up, u_ax)
        v_ax /= np.linalg.norm(v_ax) + 1e-12

        centroid = tm_model.centroid.copy()
        bottom_h = float(np.min(tm_model.vertices @ direction))

        proj_u = tm_model.vertices @ u_ax
        proj_v = tm_model.vertices @ v_ax
        max_r = float(np.max(np.sqrt(proj_u ** 2 + proj_v ** 2)))
        peg_r = max_r * 0.55
        r = cfg.peg_diameter / 2 + 0.3
        h = cfg.peg_height + cfg.mold_wall_thickness + 5.0

        for i in range(cfg.peg_count):
            angle = 2.0 * np.pi * i / cfg.peg_count
            pos = centroid + u_ax * peg_r * np.cos(angle) + v_ax * peg_r * np.sin(angle)
            pos_h = float(pos @ direction)
            pos = pos + direction * (bottom_h - pos_h)

            cyl = trimesh.creation.cylinder(radius=r, height=h, sections=12)
            _align_cylinder(cyl, -direction)
            cyl.apply_translation(pos - direction * h / 2)

            for sh in mold.shells:
                sh_h = float(sh.mesh.to_trimesh().centroid @ direction)
                if sh_h < float(centroid @ direction):
                    tm_sh = sh.mesh.to_trimesh()
                    cut = boolean_subtract(tm_sh, cyl)
                    if cut is not None and len(cut.faces) > 10:
                        sh.mesh = MeshData.from_trimesh(cut)

    # ══════════════════════════════════════════════════════════════════
    #  Thickness Analysis (v2: per-vertex map + statistics)
    # ══════════════════════════════════════════════════════════════════

    def _compute_thickness_analysis(
        self,
        tm_model: trimesh.Trimesh,
        core: trimesh.Trimesh,
    ) -> tuple[dict, list[float] | None]:
        """Compute thickness stats AND per-vertex thickness map."""
        try:
            sample_pts = tm_model.vertices
            _, dists, _ = core.nearest.on_surface(sample_pts)
            dists = np.asarray(dists, dtype=np.float64)

            # Clamp outliers
            p99 = float(np.percentile(dists, 99))
            dists_clean = np.clip(dists, 0, p99 * 1.5)

            stats = {
                "min": round(float(np.min(dists_clean)), 2),
                "max": round(float(np.max(dists_clean)), 2),
                "mean": round(float(np.mean(dists_clean)), 2),
                "std": round(float(np.std(dists_clean)), 2),
                "median": round(float(np.median(dists_clean)), 2),
                "p5": round(float(np.percentile(dists_clean, 5)), 2),
                "p95": round(float(np.percentile(dists_clean, 95)), 2),
                "n_thin_spots": int(np.sum(dists_clean < self.config.min_skin_thickness)),
                "n_thick_spots": int(np.sum(dists_clean > self.config.max_skin_thickness)),
                "uniformity_score": round(
                    1.0 - min(1.0, float(np.std(dists_clean)) / max(float(np.mean(dists_clean)), 0.01)),
                    3,
                ),
            }

            # Normalize for visualization (0=thinnest, 1=thickest)
            d_min, d_max = float(np.min(dists_clean)), float(np.max(dists_clean))
            d_range = max(d_max - d_min, 1e-6)
            thickness_map = [
                round(float((d - d_min) / d_range), 4)
                for d in dists_clean
            ]

            return stats, thickness_map
        except Exception:
            logger.exception("Thickness analysis failed")
            return {}, None

    # ══════════════════════════════════════════════════════════════════
    #  Utilities
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _ensure_quality(tm: trimesh.Trimesh) -> trimesh.Trimesh:
        """Repair mesh without destroying geometry."""
        _repair_trimesh(tm)
        if not tm.is_watertight:
            # Try voxel-based repair instead of convex hull (preserves concavities)
            try:
                from scipy.ndimage import binary_fill_holes
                from skimage.measure import marching_cubes

                extents = tm.bounds[1] - tm.bounds[0]
                pitch = float(np.max(extents)) / 100
                vox = tm.voxelized(pitch)
                filled = binary_fill_holes(vox.matrix)
                verts, faces, _, _ = marching_cubes(
                    filled.astype(float), level=0.5,
                    spacing=(pitch, pitch, pitch),
                )
                verts += tm.bounds[0] - pitch
                repaired = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
                if repaired.is_watertight and abs(repaired.volume - tm.volume) / max(abs(tm.volume), 1) < 0.3:
                    logger.info("Voxel repair succeeded for non-watertight model")
                    return repaired
            except Exception:
                pass
        return tm

    @staticmethod
    def _decimate_mesh(tm: trimesh.Trimesh, max_faces: int) -> trimesh.Trimesh:
        """Reduce face count if exceeding limit."""
        if len(tm.faces) <= max_faces:
            return tm
        try:
            ratio = max_faces / len(tm.faces)
            decimated = tm.simplify_quadric_decimation(int(len(tm.faces) * ratio))
            if len(decimated.faces) > 10:
                logger.info(
                    "Decimated core: %d → %d faces",
                    len(tm.faces), len(decimated.faces),
                )
                return decimated
        except Exception:
            pass
        return tm
