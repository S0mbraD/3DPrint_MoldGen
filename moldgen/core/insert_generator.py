"""内嵌支撑板生成器 — 置于硅胶教具内部的结构加固板
==================================================

核心概念:
  支撑板是置于硅胶教具 **内部** 的刚性结构板，目的是:
    1. 为教具提供内部骨骼/组织的触感
    2. 通过锚固结构（网孔/凸起/沟槽等）与硅胶牢固结合
    3. 通过细小支撑立柱穿过模具壁固定位置

  工艺流程:
    1. 3D打印支撑板（含锚固特征）
    2. 将支撑板通过立柱悬挂在模具空腔中
    3. 灌注硅胶，硅胶包裹支撑板并渗入锚固特征
    4. 脱模后剪断立柱，支撑板永久嵌入硅胶内

板型:
  flat       — 平面截面挤出板（经典方式）
  conformal  — 仿形板: 沿模型内表面偏移，跟随曲面轮廓
  ribbed     — 加强筋板: 平板 + 交叉肋条
  lattice    — 格栅结构: 轻量化点阵

锚固类型:
  mesh_holes — 贯穿孔（硅胶渗透结合）
  bumps      — 表面凸起（机械互锁）
  grooves    — 表面沟槽（键槽结合）
  dovetail   — 燕尾榫（强力互锁）
  diamond    — 菱形纹理（纹理结合）
"""

from __future__ import annotations

import contextlib
import logging
import math
import time
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


def _clean_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
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


# ═══════════════════════ Enums ══════════════════════════════════════════

class OrganType(StrEnum):
    SOLID = "solid"
    HOLLOW = "hollow"
    TUBULAR = "tubular"
    LIMB = "limb"
    SHEET = "sheet"
    GENERAL = "general"


class InsertType(StrEnum):
    FLAT = "flat"
    CONFORMAL = "conformal"
    RIBBED = "ribbed"       # legacy — now use flat + add_ribs=True
    LATTICE = "lattice"     # legacy — now use flat + add_mesh_holes=True


class AnchorType(StrEnum):
    """Interlocking style applied to plate edges/surface."""
    MESH_HOLES = "mesh_holes"
    BUMPS = "bumps"
    GROOVES = "grooves"
    DOVETAIL = "dovetail"
    DIAMOND = "diamond"


ORGAN_ANCHOR_MAP: dict[OrganType, AnchorType] = {
    OrganType.SOLID: AnchorType.MESH_HOLES,
    OrganType.HOLLOW: AnchorType.GROOVES,
    OrganType.TUBULAR: AnchorType.BUMPS,
    OrganType.LIMB: AnchorType.MESH_HOLES,
    OrganType.SHEET: AnchorType.DIAMOND,
    OrganType.GENERAL: AnchorType.MESH_HOLES,
}

# Legacy aliases
SkeletonType = InsertType
SkeletonConfig = None  # filled below


# ═══════════════════════ Config ═════════════════════════════════════════

@dataclass
class InsertConfig:
    # Base plate geometry: flat or conformal
    thickness: float = 2.0
    insert_type: InsertType = InsertType.FLAT
    margin: float = 1.5
    min_area_ratio: float = 0.15
    internal_offset: float = 5.0      # how deep inside model the plate sits (mm)
    plate_scale: float = 0.55         # fraction of model cross-section for plate

    # Conformal params (only used when insert_type == CONFORMAL)
    conformal_offset: float = 3.0
    conformal_smoothing: int = 2

    # ── Optional features (toggles applied to any base plate) ──
    add_mesh_holes: bool = False       # through-holes for silicone penetration
    mesh_hole_density: float = 0.3     # holes per unit area
    mesh_hole_size: float = 2.0        # hole diameter (mm)
    hole_pattern: str = "hex"          # geometric: "hex"|"grid"|"diamond"|"voronoi"
                                       # TPMS: "gyroid"|"schwarz_p"|"schwarz_d"|"neovius"|"lidinoid"|"iwp"|"frd"
    variable_density: bool = False     # field-driven radius modulation
    density_field: str = "edge"        # "edge"|"center"|"radial"|"stress"|"uniform"
    density_min_factor: float = 0.4    # at low field value, radius × this factor
    density_max_factor: float = 1.0    # at high field value, radius × this factor
    tpms_cell_size: float | None = None  # TPMS unit cell period (mm); None → auto
    tpms_z_slice: float = 0.0         # z-coordinate for TPMS 2D slice evaluation
    max_holes: int = 300              # upper bound on hole count

    add_ribs: bool = False             # reinforcement ribs on plate surface
    rib_height: float = 3.0
    rib_width: float = 1.5
    rib_spacing: float = 8.0

    add_interlocking: str | None = None  # "dovetail"|"diamond"|"grooves"|"bumps"|None
    interlock_feature_size: float = 2.0

    # Manual hole planning: list of {u, v, radius} dicts in mm relative to
    # plate centre.  If non-empty, only holes that overlap a painted region
    # are carved; holes outside all regions are skipped.
    custom_hole_regions: list[dict] | None = None

    # Manual rib planning: list of {u, v, radius} dicts defining regions
    # where ribs should appear.  If non-empty, rib displacement is only
    # applied to vertices within a painted region.
    custom_rib_regions: list[dict] | None = None

    # Legacy compat fields (mapped to new feature toggles internally)
    organ_type: OrganType = OrganType.GENERAL
    anchor_type: AnchorType | None = None
    anchor_density: float = 0.3
    anchor_feature_size: float = 2.0

    # Lattice (legacy — mapped to flat + mesh_holes internally)
    lattice_cell_size: float = 5.0
    lattice_strut_diameter: float = 1.2
    lattice_type: str = "bcc"

    # Support pillars (connect plate to mold shell)
    pillar_diameter: float = 2.0
    pillar_count: int = 4
    pillar_side: str = "auto"


SkeletonConfig = InsertConfig  # legacy alias


# ═══════════════════════ Data Classes ═══════════════════════════════════

@dataclass
class PillarInfo:
    start: np.ndarray
    end: np.ndarray
    direction: np.ndarray
    length: float
    diameter: float
    mold_hole_center: np.ndarray

    def to_dict(self) -> dict:
        return {
            "start": self.start.tolist(),
            "end": self.end.tolist(),
            "direction": self.direction.tolist(),
            "length": round(self.length, 2),
            "diameter": round(self.diameter, 2),
            "mold_hole_center": self.mold_hole_center.tolist(),
        }


@dataclass
class InsertPosition:
    origin: np.ndarray
    normal: np.ndarray
    plane_d: float
    score: float = 0.0
    section_area: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "origin": self.origin.tolist(),
            "normal": self.normal.tolist(),
            "plane_d": float(self.plane_d),
            "score": float(self.score),
            "section_area": float(self.section_area),
            "reason": self.reason,
        }


@dataclass
class AnchorFeature:
    type: AnchorType
    positions: np.ndarray
    feature_size: float
    count: int

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "count": self.count,
            "feature_size": self.feature_size,
        }


@dataclass
class InsertPlate:
    mesh: MeshData
    position: InsertPosition
    insert_type: str = "flat"
    anchor: AnchorFeature | None = None
    thickness: float = 2.0
    pillars: list[PillarInfo] = field(default_factory=list)
    pillar_mesh: MeshData | None = None
    skeleton_type: str = ""
    n_pillars: int = 0
    volume: float = 0.0
    center: list[float] = field(default_factory=lambda: [0, 0, 0])
    features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "face_count": self.mesh.face_count,
            "vertex_count": self.mesh.vertex_count,
            "thickness": self.thickness,
            "insert_type": self.insert_type,
            "skeleton_type": self.insert_type,
            "position": self.position.to_dict(),
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "n_pillars": len(self.pillars),
            "pillars": [p.to_dict() for p in self.pillars],
            "volume": round(self.volume, 2),
            "center": self.center,
            "features": self.features,
            "has_pillar_mesh": self.pillar_mesh is not None,
        }


# Legacy alias
SkeletonResult = InsertPlate


@dataclass
class InsertResult:
    plates: list[InsertPlate] = field(default_factory=list)
    positions_analyzed: list[InsertPosition] = field(default_factory=list)
    assembly_valid: bool = False
    validation_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_plates": len(self.plates),
            "plates": [p.to_dict() for p in self.plates],
            "positions_analyzed": [p.to_dict() for p in self.positions_analyzed],
            "assembly_valid": self.assembly_valid,
            "validation_messages": self.validation_messages,
        }


# ═══════════════════════ Generator ═════════════════════════════════════

class InsertGenerator:
    """内嵌支撑板生成器 — 在模型内部生成结构加固板 + 锚固特征 + 支撑立柱"""

    def __init__(self, config: InsertConfig | None = None):
        self.config = config or InsertConfig()
        self._subdivision_boost: float = 1.0

    # ── Public API ────────────────────────────────────────────────

    def analyze_positions(self, model: MeshData, n_candidates: int = 5) -> list[InsertPosition]:
        tm = model.to_trimesh()
        if len(tm.faces) > 15000:
            try:
                tm = tm.simplify_quadric_decimation(15000)
            except Exception:
                pass

        center = model.center
        positions: list[InsertPosition] = []

        for axis_idx, axis_name in enumerate(["X", "Y", "Z"]):
            normal = np.zeros(3)
            normal[axis_idx] = 1.0
            lo = float(model.bounds[0, axis_idx])
            hi = float(model.bounds[1, axis_idx])
            span = hi - lo

            for frac in [0.3, 0.5, 0.7]:
                plane_d = lo + span * frac
                origin = center.copy()
                origin[axis_idx] = plane_d
                area = self._estimate_section_area(tm, normal, plane_d)
                if area < 1.0:
                    continue
                score = self._score_position(model, normal, plane_d, area, axis_idx)
                positions.append(InsertPosition(
                    origin=origin, normal=normal, plane_d=plane_d,
                    score=score, section_area=area,
                    reason=f"{axis_name}轴 {frac*100:.0f}% 截面",
                ))

        positions.sort(key=lambda p: p.score, reverse=True)
        return positions[:n_candidates]

    def generate_plate(self, model: MeshData, position: InsertPosition) -> InsertPlate:
        """Generate base plate (flat or conformal), then apply optional features.

        For conformal plates, holes and ribs are integrated directly into
        the parametric grid (clean, uniform geometry).  For flat/legacy
        plates, features are applied as post-processing.
        """
        cfg = self.config
        itype = cfg.insert_type
        features_applied: list[str] = []

        # --- Conformal: generate → refine → carve with quality iteration ---
        if itype == InsertType.CONFORMAL:
            want_holes = bool(cfg.add_mesh_holes)
            want_ribs = bool(cfg.add_ribs)

            plate_mesh = self._generate_conformal(
                model, position,
                integrate_holes=want_holes,
                integrate_ribs=want_ribs,
            )

            # Auto-iterative quality analysis: if hole circularity is
            # too low, boost the subdivision cap and regenerate once.
            if want_holes:
                quality = self._assess_hole_quality(plate_mesh, position, model)
                logger.info("Quality iter 0: circ_mean=%.3f, circ_gt90=%.0f%%",
                            quality["circ_mean"], quality["circ_gt90_pct"])
                if quality["circ_mean"] < 0.88 or quality["circ_gt90_pct"] < 70:
                    logger.info("Quality below threshold — re-generating with 1.5x cap")
                    saved_max = self._iterative_subdivide.__defaults__  # type: ignore[attr-defined]
                    self._subdivision_boost = 1.5
                    plate_mesh = self._generate_conformal(
                        model, position,
                        integrate_holes=want_holes,
                        integrate_ribs=want_ribs,
                    )
                    self._subdivision_boost = 1.0
                    q2 = self._assess_hole_quality(plate_mesh, position, model)
                    logger.info("Quality iter 1: circ_mean=%.3f, circ_gt90=%.0f%%",
                                q2["circ_mean"], q2["circ_gt90_pct"])

            if want_holes:
                features_applied.append("mesh_holes")
            if want_ribs:
                features_applied.append("ribs")

        else:
            # Flat / legacy types
            if itype == InsertType.RIBBED:
                plate_mesh = self._generate_flat(model, position)
                cfg.add_ribs = True
            elif itype == InsertType.LATTICE:
                plate_mesh = self._generate_flat(model, position)
                cfg.add_mesh_holes = True
            else:
                plate_mesh = self._generate_flat(model, position)

            # Post-hoc features for flat plates
            if cfg.add_mesh_holes:
                n_holes = max(4, int(
                    plate_mesh.area * cfg.mesh_hole_density
                    / (cfg.mesh_hole_size ** 2)
                ))
                n_holes = min(n_holes, 50)
                plate_mesh, _ = self._add_mesh_holes(
                    plate_mesh, n_holes, cfg.mesh_hole_size,
                )
                features_applied.append("mesh_holes")

            if cfg.add_ribs:
                plate_mesh = self._apply_ribs(plate_mesh, position)
                features_applied.append("ribs")

        # Ensure plate sits inside the model (conformal plates are already
        # surface-projected; _ensure_interior would destructively scale ribs)
        if itype != InsertType.CONFORMAL:
            plate_mesh = self._ensure_interior(plate_mesh, model)

        # Interlocking features (post-hoc for all plate types)
        if cfg.add_interlocking:
            interlock_type = cfg.add_interlocking
            n_feat = max(6, int(plate_mesh.area * 0.15 / (cfg.interlock_feature_size ** 2)))
            n_feat = min(n_feat, 36)
            if interlock_type == "dovetail":
                plate_mesh, _ = self._add_dovetail(plate_mesh, n_feat, cfg.interlock_feature_size)
            elif interlock_type == "diamond":
                plate_mesh, _ = self._add_diamond(plate_mesh, n_feat, cfg.interlock_feature_size)
            elif interlock_type == "grooves":
                plate_mesh, _ = self._add_grooves(plate_mesh, n_feat, cfg.interlock_feature_size)
            elif interlock_type == "bumps":
                plate_mesh, _ = self._add_bumps(plate_mesh, n_feat, cfg.interlock_feature_size)
            features_applied.append(f"interlock_{interlock_type}")

        plate_data = MeshData.from_trimesh(plate_mesh)
        vol = float(plate_mesh.volume) if plate_mesh.is_watertight else 0.0

        effective_type = itype.value
        if itype in (InsertType.RIBBED, InsertType.LATTICE):
            effective_type = "flat"

        plate = InsertPlate(
            mesh=plate_data, position=position,
            insert_type=effective_type, thickness=cfg.thickness,
            volume=vol, center=model.center.tolist(),
            features=features_applied,
        )
        return plate

    def add_anchor(self, plate: InsertPlate) -> InsertPlate:
        """Legacy anchor method — now features are applied in generate_plate.
        Kept for backward compatibility; only runs if no features were applied."""
        cfg = self.config
        if plate.features:
            # Features already applied in generate_plate
            anchor_type_name = "none"
            for f in plate.features:
                if f.startswith("interlock_"):
                    anchor_type_name = f.replace("interlock_", "")
                elif f == "mesh_holes":
                    anchor_type_name = "mesh_holes"
            if anchor_type_name != "none":
                try:
                    at = AnchorType(anchor_type_name)
                except ValueError:
                    at = AnchorType.MESH_HOLES
                plate.anchor = AnchorFeature(
                    type=at,
                    positions=np.array([]),
                    feature_size=cfg.anchor_feature_size,
                    count=len(plate.features),
                )
            return plate

        anchor_type = cfg.anchor_type or ORGAN_ANCHOR_MAP.get(cfg.organ_type, AnchorType.MESH_HOLES)
        plate_tm = plate.mesh.to_trimesh()
        surface_area = plate_tm.area
        n_features = min(8, max(3, int(surface_area * cfg.anchor_density / (cfg.anchor_feature_size ** 2))))

        if anchor_type == AnchorType.MESH_HOLES:
            plate_tm, positions = self._add_mesh_holes(plate_tm, n_features, cfg.anchor_feature_size)
        elif anchor_type == AnchorType.BUMPS:
            plate_tm, positions = self._add_bumps(plate_tm, n_features, cfg.anchor_feature_size)
        elif anchor_type == AnchorType.GROOVES:
            plate_tm, positions = self._add_grooves(plate_tm, n_features, cfg.anchor_feature_size)
        elif anchor_type == AnchorType.DOVETAIL:
            plate_tm, positions = self._add_dovetail(plate_tm, n_features, cfg.anchor_feature_size)
        else:
            plate_tm, positions = self._add_diamond(plate_tm, n_features, cfg.anchor_feature_size)

        plate.mesh = MeshData.from_trimesh(plate_tm)
        plate.anchor = AnchorFeature(
            type=anchor_type, positions=positions,
            feature_size=cfg.anchor_feature_size, count=len(positions),
        )
        return plate

    def generate_pillars(self, plate: InsertPlate, model: MeshData) -> InsertPlate:
        """Generate support pillars from plate outward through model surface.

        Pillars are cast strictly along the configured pillar_side direction
        so they emerge from a predictable face of the mold.
        """
        cfg = self.config
        plate_tm = plate.mesh.to_trimesh()
        tm_model = model.to_trimesh()
        model_center = np.asarray(model.center, dtype=np.float64)

        pillar_dir = self._get_pillar_direction(model, cfg.pillar_side)

        n_cands = max(cfg.pillar_count * 5, 20)
        try:
            pts, _ = trimesh.sample.sample_surface(plate_tm, n_cands)
        except Exception:
            pts = plate_tm.vertices[
                np.random.choice(len(plate_tm.vertices), min(n_cands, len(plate_tm.vertices)), replace=False)
            ]

        # Only keep points on the pillar-facing side of the plate
        plate_center = (plate_tm.bounds[0] + plate_tm.bounds[1]) / 2
        offsets = pts - plate_center
        facing_scores = offsets @ pillar_dir
        # Keep points with positive facing score (on the pillar side)
        facing_mask = facing_scores > np.median(facing_scores)
        candidates = pts[facing_mask] if np.sum(facing_mask) >= cfg.pillar_count else pts

        # Spread pillar attachment points evenly
        selected = self._farthest_point_sampling(candidates, cfg.pillar_count)

        pillars: list[PillarInfo] = []
        pillar_meshes: list[trimesh.Trimesh] = []

        for pt in selected:
            # Pillars go strictly along pillar_dir (not blended with radial)
            direction = pillar_dir.copy()

            # Ray-cast from attachment point along pillar_dir to find model surface
            exit_pt = self._ray_cast(pt, direction, tm_model)
            if exit_pt is None:
                # Try slight angular offsets if direct ray misses
                for angle_off in [0.1, -0.1, 0.2, -0.2]:
                    perturbed = direction.copy()
                    perp_idx = int(np.argmin(np.abs(direction)))
                    perturbed[perp_idx] += angle_off
                    perturbed /= np.linalg.norm(perturbed) + 1e-12
                    exit_pt = self._ray_cast(pt, perturbed, tm_model)
                    if exit_pt is not None:
                        direction = perturbed
                        break
            if exit_pt is None:
                exit_pt = pt + direction * float(np.max(model.extents)) * 0.4

            # Pillar extends from plate through model surface and into mold wall
            mold_exit = exit_pt + direction * 20.0

            length = float(np.linalg.norm(mold_exit - pt))
            if length < 1.0:
                continue

            pillars.append(PillarInfo(
                start=pt.copy(), end=mold_exit.copy(),
                direction=direction.copy(), length=length,
                diameter=cfg.pillar_diameter,
                mold_hole_center=exit_pt + direction * 5.0,
            ))
            cyl = self._make_strut(pt, mold_exit, cfg.pillar_diameter / 2.0)
            if cyl is not None:
                pillar_meshes.append(cyl)

        plate.pillars = pillars
        plate.n_pillars = len(pillars)
        if pillar_meshes:
            combined = trimesh.util.concatenate(pillar_meshes)
            _clean_mesh(combined)
            plate.pillar_mesh = MeshData.from_trimesh(combined)
        return plate

    def generate_locating_slots(self, plate: InsertPlate, mold_shells: list[MeshData]) -> list[dict]:
        return [p.to_dict() for p in plate.pillars]

    def validate_assembly(
        self, model: MeshData, plates: list[InsertPlate],
        mold_shells: list[MeshData] | None = None,
    ) -> tuple[bool, list[str]]:
        messages: list[str] = []
        all_valid = True
        model_bounds = model.bounds

        for i, plate in enumerate(plates):
            plate_tm = plate.mesh.to_trimesh()
            plate_bounds = np.array([plate_tm.vertices.min(axis=0), plate_tm.vertices.max(axis=0)])

            margin = self.config.margin
            expanded = np.array([model_bounds[0] - margin, model_bounds[1] + margin])
            if np.any(plate_bounds[0] < expanded[0] - 1.0) or np.any(plate_bounds[1] > expanded[1] + 1.0):
                messages.append(f"板{i+1}: 超出模型边界")
                all_valid = False

            if plate.thickness < 1.0:
                messages.append(f"板{i+1}: 厚度过薄({plate.thickness}mm)")
                all_valid = False

            if plate.anchor is None:
                messages.append(f"板{i+1}: 未添加锚固结构，硅胶结合可能不牢固")

            if len(plate.pillars) < 2:
                messages.append(f"板{i+1}: 支撑立柱不足（{len(plate.pillars)}根）")

        if all_valid and not messages:
            messages.append("装配验证通过")
        return all_valid, messages

    def full_pipeline(
        self, model: MeshData, mold_shells: list[MeshData] | None = None,
        n_plates: int = 1,
    ) -> InsertResult:
        t0 = time.perf_counter()

        positions = self.analyze_positions(model, n_candidates=max(n_plates * 2, 5))
        plates: list[InsertPlate] = []

        for pos in positions[:n_plates]:
            plate = self.generate_plate(model, pos)
            plate = self.add_anchor(plate)
            plate = self.generate_pillars(plate, model)
            plates.append(plate)

        is_valid, msgs = self.validate_assembly(model, plates, mold_shells)
        elapsed = time.perf_counter() - t0
        logger.info("Insert pipeline: %d plates, %.2fs", len(plates), elapsed)

        return InsertResult(
            plates=plates, positions_analyzed=positions,
            assembly_valid=is_valid, validation_messages=msgs,
        )

    # ═══════════════════════ Plate Generators ═══════════════════════════

    def _generate_flat(self, model: MeshData, pos: InsertPosition) -> trimesh.Trimesh:
        tm = model.to_trimesh()
        cfg = self.config
        plate = self._get_cross_section(tm, pos.normal, pos.plane_d, cfg.thickness)
        if plate is None:
            plate = self._generate_fallback_plate(model, pos)
        return plate

    def _generate_conformal(
        self,
        model: MeshData,
        pos: InsertPosition,
        *,
        integrate_holes: bool = False,
        integrate_ribs: bool = False,
    ) -> trimesh.Trimesh:
        """Three-stage conformal plate generation (generate → refine → carve).

        Stage 1 — Base grid:  moderate-resolution parametric grid projected
                  onto the model surface.  No features yet.
        Stage 2 — Refine:     iterative ``trimesh.remesh.subdivide`` until
                  the average face area is small enough for clean features.
        Stage 3 — Carve:      holes via face-removal on the dense mesh
                  (smooth circular edges);  ribs via vertex-normal
                  displacement (smooth continuous ridges).
        """
        # ── Stage 1: base conformal grid ──
        plate = self._conformal_base_grid(model, pos)
        if plate is None or len(plate.faces) < 4:
            return self._generate_flat(model, pos)

        if not integrate_holes and not integrate_ribs:
            return plate

        # ── Stage 2: iterative subdivision ──
        cfg = self.config
        target_area = self._target_face_area_for_features(cfg)
        boost = getattr(self, "_subdivision_boost", 1.0)
        max_f = int(500_000 * boost)
        plate = self._iterative_subdivide(plate, target_area, max_iters=5, max_faces=max_f)
        logger.info(
            "After subdivision: %d faces, avg_area=%.3f mm2 (target=%.3f)",
            len(plate.faces), plate.area / max(len(plate.faces), 1), target_area,
        )

        # ── Stage 3: carve features ──
        normal = np.asarray(pos.normal, dtype=np.float64)
        up = normal / (np.linalg.norm(normal) + 1e-12)
        arb = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0.0, 1, 0])
        u_ax = np.cross(up, arb); u_ax /= (np.linalg.norm(u_ax) + 1e-12)
        v_ax = np.cross(up, u_ax); v_ax /= (np.linalg.norm(v_ax) + 1e-12)
        centroid = plate.vertices.mean(axis=0)
        half_span = float(np.max(model.extents)) * cfg.plate_scale * 0.55

        if integrate_ribs:
            plate = self._carve_ribs(plate, up, u_ax, v_ax, centroid, half_span)

        if integrate_holes:
            plate = self._carve_holes(plate, up, u_ax, v_ax, centroid, half_span)

        _clean_mesh(plate)
        return plate

    # ------------------------------------------------------------------
    # Stage 1 helper: base conformal grid (no features)
    # ------------------------------------------------------------------

    def _conformal_base_grid(
        self, model: MeshData, pos: InsertPosition,
    ) -> trimesh.Trimesh | None:
        """Moderate-resolution conformal grid projection."""
        tm = model.to_trimesh()
        cfg = self.config
        normal = np.asarray(pos.normal, dtype=np.float64)
        plane_d = pos.plane_d

        up = normal / (np.linalg.norm(normal) + 1e-12)
        arb = np.array([1, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1, 0])
        u_ax = np.cross(up, arb); u_ax /= (np.linalg.norm(u_ax) + 1e-12)
        v_ax = np.cross(up, u_ax); v_ax /= (np.linalg.norm(v_ax) + 1e-12)

        center = np.asarray(model.center, dtype=np.float64)
        plane_origin = center + up * (plane_d - np.dot(center, up))
        half_span = float(np.max(model.extents)) * cfg.plate_scale * 0.55

        grid_res = min(60, max(15, int(half_span * 2 / 2.0)))

        lu = np.linspace(-half_span, half_span, grid_res)
        lv = np.linspace(-half_span, half_span, grid_res)
        gu, gv = np.meshgrid(lu, lv, indexing="ij")
        flat_u, flat_v = gu.ravel(), gv.ravel()
        n_pts = len(flat_u)

        grid_3d = (plane_origin[None, :]
                   + flat_u[:, None] * u_ax[None, :]
                   + flat_v[:, None] * v_ax[None, :])

        tree = cKDTree(tm.vertices)
        dists, indices = tree.query(grid_3d, k=1, workers=-1)
        max_dist = half_span * 0.8
        valid = dists < max_dist

        if np.sum(valid) < 9:
            return None

        surf_pts = tm.vertices[indices]
        surf_normals = np.asarray(tm.vertex_normals, dtype=np.float64)[indices]
        sn_len = np.linalg.norm(surf_normals, axis=1, keepdims=True)
        sn_unit = surf_normals / (sn_len + 1e-12)
        offset = cfg.conformal_offset

        close_mask = dists < offset * 5
        inner = np.where(
            close_mask[:, None],
            surf_pts + sn_unit * (-offset),
            grid_3d - up[None, :] * offset,
        )
        outer_dir = np.where(close_mask[:, None], sn_unit, up[None, :])
        outer = inner + outer_dir * cfg.thickness

        ri, ci = np.meshgrid(
            np.arange(grid_res - 1), np.arange(grid_res - 1), indexing="ij",
        )
        ri, ci = ri.ravel(), ci.ravel()
        tl = ri * grid_res + ci
        tr, bl, br = tl + 1, tl + grid_res, tl + grid_res + 1

        qv = valid[tl] & valid[tr] & valid[bl] & valid[br]
        tl, tr, bl, br = tl[qv], tr[qv], bl[qv], br[qv]

        if len(tl) < 4:
            return None

        inner_f = np.vstack([
            np.column_stack([tl, tr, br]),
            np.column_stack([tl, br, bl]),
        ])
        outer_f = np.vstack([
            np.column_stack([tl + n_pts, br + n_pts, tr + n_pts]),
            np.column_stack([tl + n_pts, bl + n_pts, br + n_pts]),
        ])
        plate = trimesh.Trimesh(
            vertices=np.vstack([inner, outer]),
            faces=np.vstack([inner_f, outer_f]),
            process=True,
        )
        _clean_mesh(plate)
        return plate

    # ------------------------------------------------------------------
    # Stage 2 helper: iterative subdivision
    # ------------------------------------------------------------------

    @staticmethod
    def _target_face_area_for_features(cfg: "InsertConfig") -> float:
        """Target avg face area for smooth features.

        Target edge ≈ hole_diameter / 14 → ~44 boundary edges per hole.
        For ribs: rib_width / 5 → ≥5 edges across a rib.
        """
        targets: list[float] = []
        if cfg.add_mesh_holes and cfg.mesh_hole_size > 0:
            from moldgen.core.tpms import TPMS_REGISTRY
            div = 18 if cfg.hole_pattern in TPMS_REGISTRY else 14
            edge = cfg.mesh_hole_size / div
            targets.append(edge * edge * 0.433)
        if cfg.add_ribs and cfg.rib_width > 0:
            edge = cfg.rib_width / 5
            targets.append(edge * edge * 0.433)
        return min(targets) if targets else 1.0

    @staticmethod
    def _iterative_subdivide(
        plate: trimesh.Trimesh,
        target_area: float,
        max_iters: int = 5,
        max_faces: int = 500_000,
    ) -> trimesh.Trimesh:
        """Subdivide until average face area ≤ *target_area*."""
        for i in range(max_iters):
            avg = plate.area / max(len(plate.faces), 1)
            if avg <= target_area:
                break
            if len(plate.faces) * 4 > max_faces:
                logger.info("Subdivision capped at %d faces (limit %d)",
                            len(plate.faces), max_faces)
                break
            try:
                nv, nf = trimesh.remesh.subdivide(plate.vertices, plate.faces)
                plate = trimesh.Trimesh(vertices=nv, faces=nf, process=True)
            except Exception:
                break
        return plate

    # ------------------------------------------------------------------
    # Stage 3a: carve holes (face-removal on dense mesh)
    # ------------------------------------------------------------------

    def _carve_holes(
        self,
        plate: trimesh.Trimesh,
        up: np.ndarray,
        u_ax: np.ndarray,
        v_ax: np.ndarray,
        centroid: np.ndarray,
        half_span: float,
    ) -> trimesh.Trimesh:
        """Remove faces inside holes, then snap boundary vertices to circles.

        Improvement over v1: pre-subdivides faces near hole boundaries so
        the carved edge follows the circle more closely, producing rounder
        holes even on coarse meshes.  Variable-radius holes (from TPMS
        adaptive sizing) are handled natively.

        If ``config.custom_hole_regions`` is set, only holes whose centre
        falls inside at least one painted region are carved.
        """
        cfg = self.config
        holes = self._hole_layout(half_span, cfg)
        if not holes:
            return plate

        if cfg.custom_hole_regions:
            holes = self._filter_holes_by_regions(holes, cfg.custom_hole_regions)
            if not holes:
                return plate

        holes_arr = np.array(holes, dtype=np.float64)
        from moldgen.core.tpms import TPMS_REGISTRY

        pattern = cfg.hole_pattern
        # ── Phase 0: adaptive pre-subdivision near hole boundaries ────
        plate = self._subdivide_near_holes(plate, holes_arr, u_ax, v_ax, centroid, passes=2)

        # ── Phase 1: face removal — shape depends on pattern (nTopology-style distinction)
        fc = plate.triangles_center
        fc_c = fc - centroid
        fu = fc_c @ u_ax
        fv = fc_c @ v_ax

        keep = np.ones(len(plate.faces), dtype=bool)
        for hu, hv, hr in holes:
            safe_r = max(float(hr), 1e-6)
            if pattern in TPMS_REGISTRY:
                du = (fu - hu) / safe_r
                dv = (fv - hv) / safe_r
                keep &= (np.abs(du) ** 2.15 + np.abs(dv) ** 2.15) >= 1.0
            elif pattern == "grid":
                keep &= np.maximum(np.abs(fu - hu), np.abs(fv - hv)) >= safe_r * 0.96
            elif pattern == "diamond":
                du, dv = (fu - hu) / safe_r, (fv - hv) / safe_r
                keep &= (np.abs(du) + np.abs(dv)) >= 1.02
            else:
                keep &= (fu - hu) ** 2 + (fv - hv) ** 2 >= hr * hr

        n_removed = int(np.sum(~keep))
        if n_removed == 0:
            return plate

        result = plate.copy()
        result.update_faces(keep)
        result.remove_unreferenced_vertices()

        # ── Phase 2: circular snap only when holes are rotationally symmetric ──────────
        if pattern not in TPMS_REGISTRY and pattern not in ("grid", "diamond"):
            result = self._snap_hole_boundaries(result, holes_arr, u_ax, v_ax, centroid)

        # ── Phase 3: boundary smoothing ─────────────
        result = self._smooth_boundary_ring(result, iterations=3)

        logger.info(
            "Carved %d faces for %d holes pattern=%s (%.1f%% removed)",
            n_removed, len(holes), pattern, 100 * n_removed / len(plate.faces),
        )
        return result

    @staticmethod
    def _subdivide_near_holes(
        plate: trimesh.Trimesh,
        holes_arr: np.ndarray,
        u_ax: np.ndarray,
        v_ax: np.ndarray,
        centroid: np.ndarray,
        passes: int = 2,
    ) -> trimesh.Trimesh:
        """Locally subdivide faces near hole boundaries for smoother carving.

        For each pass, identifies faces whose centroid is in the annular ring
        [0.7r, 1.3r] around any hole and subdivides only those faces.
        """
        for _ in range(passes):
            fc = plate.triangles_center
            fc_c = fc - centroid
            fu = fc_c @ u_ax
            fv = fc_c @ v_ax

            near_boundary = np.zeros(len(plate.faces), dtype=bool)
            for hu, hv, hr in holes_arr:
                d2 = (fu - hu) ** 2 + (fv - hv) ** 2
                inner = (0.7 * hr) ** 2
                outer = (1.3 * hr) ** 2
                near_boundary |= (d2 >= inner) & (d2 <= outer)

            face_idx = np.where(near_boundary)[0]
            if len(face_idx) == 0 or len(face_idx) > len(plate.faces) * 0.6:
                break

            try:
                verts, faces = trimesh.remesh.subdivide(
                    plate.vertices, plate.faces, face_index=face_idx,
                )
                plate = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
            except Exception as exc:
                logger.debug("Pre-subdivision pass failed: %s", exc)
                break
        return plate

    @staticmethod
    def _filter_holes_by_regions(
        holes: list[tuple[float, float, float]],
        regions: list[dict],
    ) -> list[tuple[float, float, float]]:
        """Keep only holes whose centre overlaps at least one painted region."""
        kept: list[tuple[float, float, float]] = []
        for hu, hv, hr in holes:
            for reg in regions:
                ru, rv, rr = reg["u"], reg["v"], reg["radius"]
                if (hu - ru) ** 2 + (hv - rv) ** 2 <= (rr + hr) ** 2:
                    kept.append((hu, hv, hr))
                    break
        return kept

    @staticmethod
    def _find_boundary_verts(faces: np.ndarray) -> np.ndarray:
        """Return sorted array of boundary vertex indices (vectorised)."""
        f = faces
        edges = np.vstack([
            np.sort(f[:, [0, 1]], axis=1),
            np.sort(f[:, [1, 2]], axis=1),
            np.sort(f[:, [0, 2]], axis=1),
        ])
        _, inv, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
        boundary_mask = counts[inv] == 1
        bv = np.unique(edges[boundary_mask])
        return bv

    @staticmethod
    def _snap_hole_boundaries(
        plate: trimesh.Trimesh,
        holes_arr: np.ndarray,
        u_ax: np.ndarray,
        v_ax: np.ndarray,
        centroid: np.ndarray,
    ) -> trimesh.Trimesh:
        """Project boundary vertices onto nearest ideal circle in u-v space.

        For each boundary vertex within 40 % of hole radius from the ideal
        circle, snap its u-v position to the exact circle perimeter while
        preserving its height component.
        """
        bv_idx = InsertGenerator._find_boundary_verts(plate.faces)
        if len(bv_idx) == 0:
            return plate

        verts = plate.vertices.copy()
        bv_pos = verts[bv_idx]

        centered = bv_pos - centroid
        bu = centered @ u_ax
        bv = centered @ v_ax

        hu, hv, hr = holes_arr[:, 0], holes_arr[:, 1], holes_arr[:, 2]

        du = bu[:, None] - hu[None, :]
        dv = bv[:, None] - hv[None, :]
        dist_to_center = np.sqrt(du ** 2 + dv ** 2)
        dist_to_circle = np.abs(dist_to_center - hr[None, :])

        nearest_hole = np.argmin(dist_to_circle, axis=1)
        nearest_dist = dist_to_circle[np.arange(len(bv_idx)), nearest_hole]

        snap_threshold = hr[nearest_hole] * 0.4
        snap_mask = nearest_dist < snap_threshold
        if np.sum(snap_mask) == 0:
            return plate

        si = np.where(snap_mask)[0]
        hi = nearest_hole[si]
        d = dist_to_center[si, hi]
        safe_d = np.maximum(d, 1e-9)
        target_r = hr[hi]

        new_u = hu[hi] + (bu[si] - hu[hi]) / safe_d * target_r
        new_v = hv[hi] + (bv[si] - hv[hi]) / safe_d * target_r

        verts[bv_idx[si]] += ((new_u - bu[si])[:, None] * u_ax[None, :]
                              + (new_v - bv[si])[:, None] * v_ax[None, :])

        logger.info("Boundary snap: %d / %d boundary vertices projected to circles",
                     int(snap_mask.sum()), len(bv_idx))
        return trimesh.Trimesh(vertices=verts, faces=plate.faces.copy(), process=True)

    @staticmethod
    def _smooth_boundary_ring(
        plate: trimesh.Trimesh, iterations: int = 2,
    ) -> trimesh.Trimesh:
        """Laplacian smoothing of vertices in the 1-ring around boundaries.

        Uses sparse adjacency matrix for vectorised computation.
        """
        from scipy.sparse import csr_matrix

        bv_set = set(InsertGenerator._find_boundary_verts(plate.faces).tolist())
        if not bv_set:
            return plate

        n_v = len(plate.vertices)
        f = plate.faces
        rows = np.concatenate([f[:, 0], f[:, 1], f[:, 2],
                               f[:, 1], f[:, 2], f[:, 0]])
        cols = np.concatenate([f[:, 1], f[:, 2], f[:, 0],
                               f[:, 0], f[:, 1], f[:, 2]])
        adj = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n_v, n_v))

        # 1-ring: interior vertices adjacent to at least one boundary vertex
        ring_set: set[int] = set()
        for bv in bv_set:
            ring_set.update(adj[bv].indices.tolist())
        ring_set -= bv_set
        if not ring_set:
            return plate

        ring_idx = np.array(sorted(ring_set))
        verts = plate.vertices.copy()

        for _ in range(iterations):
            nbs_sum = np.asarray(adj[ring_idx].dot(verts))
            degree = np.asarray(adj[ring_idx].sum(axis=1)).ravel()[:, None]
            nbs_avg = nbs_sum / np.maximum(degree, 1)
            verts[ring_idx] = verts[ring_idx] * 0.5 + nbs_avg * 0.5

        return trimesh.Trimesh(vertices=verts, faces=plate.faces.copy(), process=True)

    # ------------------------------------------------------------------
    # Quality assessment (auto-iterative analysis)
    # ------------------------------------------------------------------

    def _assess_hole_quality(
        self,
        plate: trimesh.Trimesh,
        pos: InsertPosition,
        model: MeshData,
    ) -> dict:
        """Compute hole circularity metrics for iterative quality control."""
        from collections import defaultdict

        bv_idx = self._find_boundary_verts(plate.faces)
        if len(bv_idx) == 0:
            return {"circ_mean": 1.0, "circ_gt90_pct": 100.0, "n_holes": 0}

        f = plate.faces
        edges = np.vstack([
            np.sort(f[:, [0, 1]], axis=1),
            np.sort(f[:, [1, 2]], axis=1),
            np.sort(f[:, [0, 2]], axis=1),
        ])
        _, inv, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
        b_edges = edges[counts[inv] == 1]
        adj: dict[int, set[int]] = defaultdict(set)
        for a, b in b_edges:
            adj[a].add(b)
            adj[b].add(a)
        visited: set[int] = set()
        loops: list[list[int]] = []
        for start in adj:
            if start in visited:
                continue
            loop: list[int] = []
            stack = [start]
            while stack:
                v = stack.pop()
                if v in visited:
                    continue
                visited.add(v)
                loop.append(v)
                stack.extend(adj[v] - visited)
            loops.append(loop)

        hole_loops = [l for l in loops if 8 <= len(l) < 300]
        if not hole_loops:
            return {"circ_mean": 1.0, "circ_gt90_pct": 100.0, "n_holes": 0}

        circs = []
        for loop in hole_loops:
            pts = plate.vertices[loop]
            c = pts.mean(axis=0)
            d = np.linalg.norm(pts - c, axis=1)
            circs.append(1 - d.std() / max(d.mean(), 0.01))
        ca = np.array(circs)
        return {
            "circ_mean": float(ca.mean()),
            "circ_gt90_pct": float(100 * (ca > 0.90).sum() / len(ca)),
            "n_holes": len(hole_loops),
        }

    # ------------------------------------------------------------------
    # Stage 3b: carve ribs (vertex-normal displacement on dense mesh)
    # ------------------------------------------------------------------

    def _carve_ribs(
        self,
        plate: trimesh.Trimesh,
        up: np.ndarray,
        u_ax: np.ndarray,
        v_ax: np.ndarray,
        centroid: np.ndarray,
        half_span: float,
    ) -> trimesh.Trimesh:
        """Displace outer vertices along normals with a smooth cosine profile.

        Instead of a binary step (0 or rib_height), uses a raised-cosine
        cross-section: vertices at the rib centre get full height, those at
        the edge taper smoothly to zero.  This eliminates the sharp step
        transition and produces printable, organic-looking ridges.
        """
        cfg = self.config
        verts = plate.vertices.copy()
        fn = np.asarray(plate.face_normals, dtype=np.float64)

        # Robust outer-only vertex normals via face accumulation
        face_outer = np.einsum("ij,j->i", fn, up) > 0
        ofi = np.where(face_outer)[0]
        v_normals = np.zeros_like(verts)
        np.add.at(v_normals, plate.faces[ofi, 0], fn[ofi])
        np.add.at(v_normals, plate.faces[ofi, 1], fn[ofi])
        np.add.at(v_normals, plate.faces[ofi, 2], fn[ofi])
        vn_len = np.linalg.norm(v_normals, axis=1, keepdims=True)
        vn_unit = v_normals / (vn_len + 1e-12)

        outer = (vn_len.ravel() > 0.5) & (np.einsum("ij,j->i", vn_unit, up) > 0.2)

        vc = verts - centroid
        vu = vc @ u_ax
        vv = vc @ v_ax

        # Compute per-vertex distance to nearest rib centre-line
        dist_field = self._rib_distance_field(vu, vv, half_span, cfg)

        hw = cfg.rib_width / 2
        within_rib = outer & (dist_field < hw)

        # Apply custom rib region mask if provided
        if cfg.custom_rib_regions:
            region_mask = np.zeros(len(verts), dtype=bool)
            for reg in cfg.custom_rib_regions:
                ru, rv, rr = reg["u"], reg["v"], reg["radius"]
                region_mask |= (vu - ru) ** 2 + (vv - rv) ** 2 <= rr * rr
            within_rib &= region_mask

        n_moved = int(np.sum(within_rib))
        if n_moved == 0:
            return plate

        # Raised-cosine profile: 1.0 at centre, 0.0 at hw
        t = dist_field[within_rib] / hw
        profile = 0.5 * (1.0 + np.cos(np.pi * np.clip(t, 0, 1)))

        verts[within_rib] += vn_unit[within_rib] * (cfg.rib_height * profile[:, None])
        result = trimesh.Trimesh(
            vertices=verts, faces=plate.faces.copy(), process=True,
        )
        logger.info("Rib displacement: %d vertices, cosine profile, max=%.1f mm",
                     n_moved, cfg.rib_height)
        return result

    # ------------------------------------------------------------------
    # Parametric feature helpers (used by _generate_conformal)
    # ------------------------------------------------------------------

    @staticmethod
    def _hole_layout(
        half_span: float, cfg: "InsertConfig",
    ) -> list[tuple[float, float, float]]:
        """Dispatch to pattern-specific hole layout.  Returns [(u, v, radius)].

        Geometric patterns (hex, grid, voronoi) use direct placement.
        TPMS patterns (gyroid, schwarz_p, schwarz_d, neovius, lidinoid,
        iwp, frd) use the implicit-field library in ``tpms.py`` with
        local-extrema detection for mathematically precise placement.
        """
        from moldgen.core.tpms import generate_tpms_holes, apply_field_modulation, TPMS_REGISTRY

        pattern = cfg.hole_pattern
        tpms_cell_size = getattr(cfg, "tpms_cell_size", None) or cfg.mesh_hole_size * 3.0
        tpms_z_slice = getattr(cfg, "tpms_z_slice", 0.0)
        max_holes = getattr(cfg, "max_holes", 300)

        # TPMS-based patterns — use the implicit-field pipeline
        if pattern in TPMS_REGISTRY:
            density_field = cfg.density_field if cfg.variable_density else None
            holes = generate_tpms_holes(
                tpms_name=pattern,
                half_span=half_span,
                hole_diameter=cfg.mesh_hole_size,
                cell_size=tpms_cell_size,
                z_slice=tpms_z_slice,
                adaptive_radius=True,
                max_holes=max_holes,
                density_field=density_field,
                density_min=cfg.density_min_factor,
                density_max=cfg.density_max_factor,
            )
            return holes

        # Geometric patterns
        dispatchers: dict[str, object] = {
            "hex": InsertGenerator._layout_hex,
            "grid": InsertGenerator._layout_grid,
            "diamond": InsertGenerator._layout_diamond_geo,
            "voronoi": InsertGenerator._layout_voronoi,
        }
        fn = dispatchers.get(pattern, InsertGenerator._layout_hex)
        holes = fn(half_span, cfg)  # type: ignore[operator]

        # Apply field-driven radius modulation (continuous, not binary)
        if cfg.variable_density:
            holes = InsertGenerator._apply_variable_density(
                holes, half_span,
                field_type=cfg.density_field,
                min_factor=cfg.density_min_factor,
                max_factor=cfg.density_max_factor,
            )
        return holes

    # ── Geometric layout helpers ──────────────────────────────────────

    @staticmethod
    def _layout_hex(
        half_span: float, cfg: "InsertConfig",
    ) -> list[tuple[float, float, float]]:
        """Classic hex-grid hole centres in u-v space."""
        hole_r = cfg.mesh_hole_size / 2
        plate_area = (2 * half_span) ** 2
        n_target = max(4, int(plate_area * cfg.mesh_hole_density / (cfg.mesh_hole_size ** 2)))
        n_target = min(n_target, 300)

        spacing = np.sqrt(plate_area / max(n_target, 1)) * 0.92
        margin = hole_r * 1.5
        lo, hi = -half_span + margin, half_span - margin

        centres: list[tuple[float, float, float]] = []
        row = 0
        v = lo
        while v < hi:
            u_off = (spacing * 0.5) * (row % 2)
            u = lo + u_off
            while u < hi:
                centres.append((float(u), float(v), float(hole_r)))
                u += spacing
            v += spacing * np.sqrt(3) / 2
            row += 1
        if len(centres) > n_target:
            step = max(1, len(centres) // n_target)
            centres = centres[::step][:n_target]
        return centres

    @staticmethod
    def _layout_grid(
        half_span: float, cfg: "InsertConfig",
    ) -> list[tuple[float, float, float]]:
        """Square grid pattern."""
        hole_r = cfg.mesh_hole_size / 2
        plate_area = (2 * half_span) ** 2
        n_target = max(4, int(plate_area * cfg.mesh_hole_density / (cfg.mesh_hole_size ** 2)))
        n_target = min(n_target, 300)
        spacing = np.sqrt(plate_area / max(n_target, 1))
        margin = hole_r * 1.5
        lo, hi = -half_span + margin, half_span - margin

        centres: list[tuple[float, float, float]] = []
        v = lo
        while v < hi:
            u = lo
            while u < hi:
                centres.append((float(u), float(v), float(hole_r)))
                u += spacing
            v += spacing
        return centres[:n_target]

    @staticmethod
    def _layout_diamond_geo(
        half_span: float, cfg: "InsertConfig",
    ) -> list[tuple[float, float, float]]:
        """Diamond geometric pattern: 45°-rotated square grid."""
        hole_r = cfg.mesh_hole_size / 2
        plate_area = (2 * half_span) ** 2
        n_target = max(4, int(plate_area * cfg.mesh_hole_density / (cfg.mesh_hole_size ** 2)))
        n_target = min(n_target, 300)
        spacing = np.sqrt(plate_area / max(n_target, 1))
        margin = hole_r * 1.5
        lo, hi = -half_span + margin, half_span - margin
        cos45, sin45 = np.cos(np.pi / 4), np.sin(np.pi / 4)
        centres: list[tuple[float, float, float]] = []
        ext = half_span * 1.6
        v = -ext
        while v < ext:
            u = -ext
            while u < ext:
                ru = u * cos45 - v * sin45
                rv = u * sin45 + v * cos45
                if lo <= ru <= hi and lo <= rv <= hi:
                    centres.append((float(ru), float(rv), float(hole_r)))
                u += spacing
            v += spacing
        return centres[:n_target]

    @staticmethod
    def _layout_voronoi(
        half_span: float, cfg: "InsertConfig",
    ) -> list[tuple[float, float, float]]:
        """Voronoi-based stochastic pattern with 5× Lloyd relaxation."""
        hole_r = cfg.mesh_hole_size / 2
        plate_area = (2 * half_span) ** 2
        n_target = max(4, int(plate_area * cfg.mesh_hole_density / (cfg.mesh_hole_size ** 2)))
        n_target = min(n_target, 300)
        margin = hole_r * 1.5
        lo, hi = -half_span + margin, half_span - margin
        rng = np.random.default_rng(42)
        pts = rng.uniform(lo, hi, size=(n_target * 2, 2))
        from scipy.spatial import Voronoi
        for _ in range(5):
            try:
                vor = Voronoi(pts)
                new_pts = []
                for i, reg_idx in enumerate(vor.point_region):
                    region = vor.regions[reg_idx]
                    if -1 in region or len(region) == 0:
                        new_pts.append(pts[i])
                        continue
                    verts = vor.vertices[region]
                    centroid = verts.mean(axis=0)
                    centroid = np.clip(centroid, lo, hi)
                    new_pts.append(centroid)
                pts = np.array(new_pts)
            except Exception as exc:
                logger.debug("Voronoi Lloyd iteration failed: %s", exc)
                break
        pts = pts[(pts[:, 0] >= lo) & (pts[:, 0] <= hi) & (pts[:, 1] >= lo) & (pts[:, 1] <= hi)]
        return [(float(p[0]), float(p[1]), float(hole_r)) for p in pts[:n_target]]

    # ── Variable density (legacy compat — new code uses tpms.apply_field_modulation) ──

    @staticmethod
    def _apply_variable_density(
        holes: list[tuple[float, float, float]],
        half_span: float,
        field_type: str = "edge",
        min_factor: float = 0.3,
        max_factor: float = 1.0,
    ) -> list[tuple[float, float, float]]:
        """Field-driven radius modulation.  Smoothly varies hole *size* instead
        of binary removal for nTopology-style graded perforations.
        """
        from moldgen.core.tpms import _field_value
        result: list[tuple[float, float, float]] = []
        for u, v, r in holes:
            t = _field_value(u, v, half_span, field_type)
            factor = min_factor + (max_factor - min_factor) * t
            new_r = r * factor
            if new_r >= r * 0.3:
                result.append((u, v, new_r))
        return result

    @staticmethod
    def _rib_vertex_mask(
        flat_u: np.ndarray,
        flat_v: np.ndarray,
        half_span: float,
        cfg: "InsertConfig",
    ) -> np.ndarray:
        """Boolean mask selecting vertices that sit on a rib cross-hatch line."""
        hw = cfg.rib_width / 2
        spacing = cfg.rib_spacing
        mask = np.zeros(len(flat_u), dtype=bool)

        n_u = max(1, int(2 * half_span / spacing))
        for i in range(n_u):
            u_pos = -half_span + (i + 0.5) * 2 * half_span / n_u
            mask |= np.abs(flat_u - u_pos) < hw

        n_v = max(1, int(2 * half_span / spacing))
        for i in range(n_v):
            v_pos = -half_span + (i + 0.5) * 2 * half_span / n_v
            mask |= np.abs(flat_v - v_pos) < hw

        return mask

    @staticmethod
    def _rib_distance_field(
        flat_u: np.ndarray,
        flat_v: np.ndarray,
        half_span: float,
        cfg: "InsertConfig",
    ) -> np.ndarray:
        """Signed distance from each vertex to the nearest rib centre-line.

        Used by the raised-cosine rib profile to smoothly taper the
        displacement from full height at the centre to zero at the edge.
        """
        spacing = cfg.rib_spacing
        dist = np.full(len(flat_u), float("inf"))

        n_u = max(1, int(2 * half_span / spacing))
        for i in range(n_u):
            u_pos = -half_span + (i + 0.5) * 2 * half_span / n_u
            dist = np.minimum(dist, np.abs(flat_u - u_pos))

        n_v = max(1, int(2 * half_span / spacing))
        for i in range(n_v):
            v_pos = -half_span + (i + 0.5) * 2 * half_span / n_v
            dist = np.minimum(dist, np.abs(flat_v - v_pos))

        return dist

    def _adaptive_grid_res(
        self,
        half_span: float,
        integrate_holes: bool,
        integrate_ribs: bool,
    ) -> int:
        """Compute grid resolution so features have enough cells to look clean.

        For holes: ~20 cells per hole gives a good circular approximation.
        For ribs:  >=3 grid points across each rib width for a smooth profile.
        """
        cfg = self.config
        span = 2 * half_span

        # Baseline: reasonable display quality
        res_base = max(20, int(span / 2.0))

        # Holes: need spacing small enough that each hole covers ~20 cells
        res_holes = 0
        if integrate_holes and cfg.mesh_hole_size > 0:
            hole_r = cfg.mesh_hole_size / 2
            target_cells = 20
            max_spacing = hole_r / np.sqrt(target_cells / np.pi)
            res_holes = int(np.ceil(span / max_spacing))

        # Ribs: >=3 points per rib width
        res_ribs = 0
        if integrate_ribs and cfg.rib_width > 0:
            max_spacing_rib = cfg.rib_width / 3.0
            res_ribs = int(np.ceil(span / max_spacing_rib))

        grid_res = max(res_base, res_holes, res_ribs)

        boost = getattr(cfg, "_grid_res_boost", 1.0)
        if boost > 1.0:
            grid_res = int(grid_res * boost)

        grid_res = min(grid_res, 200)

        logger.info(
            "Adaptive grid: span=%.0fmm, base=%d, holes=%d, ribs=%d -> res=%d (spacing=%.2fmm)",
            span, res_base, res_holes, res_ribs, grid_res, span / grid_res,
        )
        return grid_res

    # ------------------------------------------------------------------
    # Mesh quality analysis (iterative convergence)
    # ------------------------------------------------------------------

    @staticmethod
    def analyze_plate_quality(
        plate_mesh: trimesh.Trimesh,
        cfg: "InsertConfig",
        grid_res: int,
        half_span: float,
    ) -> dict:
        """Compute quality metrics for a conformal plate.

        Returns a dict of metrics and a boolean ``converged`` flag.
        """
        n_faces = len(plate_mesh.faces)
        total_area = plate_mesh.area
        avg_area = total_area / max(n_faces, 1)
        spacing = 2 * half_span / max(grid_res, 1)

        metrics: dict = {
            "grid_res": grid_res,
            "spacing_mm": round(spacing, 3),
            "n_faces": n_faces,
            "total_area_mm2": round(total_area, 1),
            "avg_face_area_mm2": round(avg_area, 3),
        }

        converged = True

        if cfg.add_mesh_holes and cfg.mesh_hole_size > 0:
            hole_r = cfg.mesh_hole_size / 2
            cells_per_hole = np.pi * (hole_r / max(spacing, 0.01)) ** 2
            metrics["cells_per_hole"] = round(cells_per_hole, 1)
            if cells_per_hole < 12:
                converged = False
                metrics["hole_quality"] = "LOW — increase grid_res"
            elif cells_per_hole < 20:
                metrics["hole_quality"] = "MEDIUM"
            else:
                metrics["hole_quality"] = "HIGH"

        if cfg.add_ribs and cfg.rib_width > 0:
            pts_per_rib = cfg.rib_width / max(spacing, 0.01)
            metrics["pts_per_rib_width"] = round(pts_per_rib, 1)
            if pts_per_rib < 2:
                converged = False
                metrics["rib_quality"] = "LOW — increase grid_res"
            elif pts_per_rib < 3:
                metrics["rib_quality"] = "MEDIUM"
            else:
                metrics["rib_quality"] = "HIGH"

        metrics["converged"] = converged
        return metrics

    def _generate_ribbed(self, model: MeshData, pos: InsertPosition) -> trimesh.Trimesh:
        flat = self._generate_flat(model, pos)
        cfg = self.config
        normal = pos.normal
        main_ax = int(np.argmax(np.abs(normal)))
        bounds = np.array([flat.vertices.min(axis=0), flat.vertices.max(axis=0)])
        center = (bounds[0] + bounds[1]) / 2
        extents = bounds[1] - bounds[0]
        axes = [i for i in range(3) if i != main_ax]

        ribs: list[trimesh.Trimesh] = []
        for ax_idx in axes:
            lo = float(bounds[0][ax_idx]) + cfg.rib_spacing / 2
            hi = float(bounds[1][ax_idx]) - cfg.rib_spacing / 2
            n_ribs = max(1, int((hi - lo) / cfg.rib_spacing) + 1)
            for ri in range(n_ribs):
                pos_val = lo + ri * cfg.rib_spacing if n_ribs > 1 else (lo + hi) / 2
                rib_ext = [0.0, 0.0, 0.0]
                rib_ext[ax_idx] = cfg.rib_width
                other = [a for a in axes if a != ax_idx][0] if len(axes) > 1 else axes[0]
                rib_ext[other] = float(extents[other]) * 0.9
                rib_ext[main_ax] = cfg.rib_height
                rib_c = center.copy()
                rib_c[ax_idx] = pos_val
                rib_c[main_ax] += (cfg.thickness / 2 + cfg.rib_height / 2) * (1 if normal[main_ax] >= 0 else -1)
                rib = trimesh.creation.box(extents=rib_ext)
                rib.apply_translation(rib_c)
                ribs.append(rib)

        if not ribs:
            return flat
        try:
            combined = trimesh.util.concatenate([flat] + ribs)
            _clean_mesh(combined)
            return combined
        except Exception:
            return flat

    def _apply_ribs(self, plate_mesh: trimesh.Trimesh, pos: InsertPosition) -> trimesh.Trimesh:
        """Add reinforcement ribs ON the plate surface by extruding face strips.

        Algorithm:
          1. Project face centroids to a local u-v coordinate system on the
             plate's reference plane.
          2. Select grid-aligned strips of faces for each rib line.
          3. Extrude each selected face outward along its own normal by
             *rib_height*, creating triangular prisms that naturally follow
             the surface curvature.
        """
        cfg = self.config
        if len(plate_mesh.faces) < 4:
            return plate_mesh

        normal = np.asarray(pos.normal, dtype=np.float64)
        up = normal / (np.linalg.norm(normal) + 1e-12)
        arb = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0.0, 1, 0])
        u_ax = np.cross(up, arb); u_ax /= (np.linalg.norm(u_ax) + 1e-12)
        v_ax = np.cross(up, u_ax); v_ax /= (np.linalg.norm(v_ax) + 1e-12)

        fc = plate_mesh.triangles_center
        fn = plate_mesh.face_normals
        centroid = fc.mean(axis=0)

        u_coords = (fc - centroid) @ u_ax
        v_coords = (fc - centroid) @ v_ax
        u_span = float(u_coords.max() - u_coords.min())
        v_span = float(v_coords.max() - v_coords.min())

        # Outer-facing faces: normal has positive component along `up`
        outer_mask = np.einsum("ij,j->i", fn, up) > 0
        if np.sum(outer_mask) < 2:
            outer_mask = np.ones(len(fn), dtype=bool)

        rib_faces: set[int] = set()

        for coord, span in [(u_coords, u_span), (v_coords, v_span)]:
            n_ribs = max(1, int(span / cfg.rib_spacing))
            c_min = float(coord.min())
            for ri in range(n_ribs):
                c_pos = c_min + (ri + 0.5) * span / n_ribs
                strip = (np.abs(coord - c_pos) < cfg.rib_width * 0.6) & outer_mask
                rib_faces.update(np.where(strip)[0].tolist())

        if not rib_faces:
            return plate_mesh

        prisms: list[trimesh.Trimesh] = []
        for fi in rib_faces:
            tri = plate_mesh.triangles[fi]         # (3, 3)
            n_vec = fn[fi]
            n_len = np.linalg.norm(n_vec)
            if n_len < 1e-10:
                continue
            n_vec = n_vec / n_len

            outer = tri + n_vec * cfg.rib_height
            verts = np.vstack([tri, outer])        # (6, 3)
            faces = np.array([
                [0, 2, 1], [3, 4, 5],             # caps
                [0, 3, 5], [0, 5, 2],             # sides
                [2, 5, 4], [2, 4, 1],
                [1, 4, 3], [1, 3, 0],
            ])
            prisms.append(trimesh.Trimesh(vertices=verts, faces=faces, process=False))

        if not prisms:
            return plate_mesh

        MAX_PRISMS = 400
        if len(prisms) > MAX_PRISMS:
            step = max(1, len(prisms) // MAX_PRISMS)
            prisms = prisms[::step][:MAX_PRISMS]

        try:
            combined = trimesh.util.concatenate([plate_mesh] + prisms)
            _clean_mesh(combined)
            logger.info("Ribs: %d face prisms on plate (%d total faces)", len(prisms), len(combined.faces))
            return combined
        except Exception:
            return plate_mesh

    def _generate_lattice(self, model: MeshData, pos: InsertPosition) -> trimesh.Trimesh:
        cfg = self.config
        normal = np.asarray(pos.normal, dtype=np.float64)
        extents = model.extents
        center = np.asarray(model.center, dtype=np.float64)
        main_ax = int(np.argmax(np.abs(normal)))
        axes = [i for i in range(3) if i != main_ax]
        cell = cfg.lattice_cell_size
        r = cfg.lattice_strut_diameter / 2

        span = [float(extents[axes[0]]) * cfg.plate_scale,
                float(extents[axes[1]]) * cfg.plate_scale if len(axes) > 1 else cell * 2,
                cfg.thickness]
        nx = max(2, min(6, int(span[0] / cell)))
        ny = max(2, min(6, int(span[1] / cell)))
        nz = max(1, min(2, int(span[2] / cell) + 1))

        origin = center.copy()
        origin[axes[0]] -= nx * cell / 2
        if len(axes) > 1:
            origin[axes[1]] -= ny * cell / 2
        origin[main_ax] -= nz * cell / 2

        endpoints: list[tuple[np.ndarray, np.ndarray]] = []
        for ix in range(nx + 1):
            for iy in range(ny + 1):
                for iz in range(nz + 1):
                    pt = origin.copy()
                    pt[axes[0]] += ix * cell
                    if len(axes) > 1:
                        pt[axes[1]] += iy * cell
                    pt[main_ax] += iz * cell

                    if ix < nx:
                        end = pt.copy(); end[axes[0]] += cell
                        endpoints.append((pt.copy(), end))
                    if len(axes) > 1 and iy < ny:
                        end = pt.copy(); end[axes[1]] += cell
                        endpoints.append((pt.copy(), end))
                    if iz < nz:
                        end = pt.copy(); end[main_ax] += cell
                        endpoints.append((pt.copy(), end))

        MAX_STRUTS = 120
        if len(endpoints) > MAX_STRUTS:
            step = max(1, len(endpoints) // MAX_STRUTS)
            endpoints = endpoints[::step][:MAX_STRUTS]

        parts: list[trimesh.Trimesh] = []
        for p1, p2 in endpoints:
            s = self._make_strut(p1, p2, r)
            if s is not None:
                parts.append(s)

        if not parts:
            return self._generate_flat(model, pos)
        combined = trimesh.util.concatenate(parts)
        _clean_mesh(combined)
        return combined

    # ═══════════════════════ Interior Clipping ══════════════════════════

    def _ensure_interior(self, plate: trimesh.Trimesh, model: MeshData) -> trimesh.Trimesh:
        """Scale and clip plate to sit inside the model with clearance."""
        cfg = self.config
        model_bounds = model.bounds
        model_center = np.asarray(model.center, dtype=np.float64)
        model_extents = model_bounds[1] - model_bounds[0]

        plate_bounds = np.array([plate.vertices.min(axis=0), plate.vertices.max(axis=0)])
        plate_center = (plate_bounds[0] + plate_bounds[1]) / 2
        plate_extents = plate_bounds[1] - plate_bounds[0]

        max_allowed = model_extents - 2 * cfg.internal_offset
        max_allowed = np.maximum(max_allowed, cfg.thickness * 3)

        scale_factors = max_allowed / (plate_extents + 1e-6)
        scale = float(np.min(scale_factors))
        if scale < 1.0:
            plate.vertices = (plate.vertices - plate_center) * scale + model_center
        else:
            plate.apply_translation(model_center - plate_center)

        return plate

    # ═══════════════════════ Anchor Features ═══════════════════════════

    def _add_mesh_holes(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        """Cut through-holes in the plate for silicone penetration.

        Strategy:
          1. Watertight plate → manifold3d boolean subtraction (precise).
          2. Non-watertight (conformal) → subdivide mesh to increase face
             density, then remove faces within hole radius.
        """
        points = self._sample_pts(plate, n * 3)
        selected = self._farthest_point_sampling(points, n)

        if plate.is_watertight:
            result = self._boolean_mesh_holes(plate, selected, size)
            if result is not None:
                logger.info("Mesh holes: boolean cut %d holes", len(selected))
                return result, selected

        work = self._subdivide_for_holes(plate, size)
        result = self._face_removal_mesh_holes(work, selected, size)
        return result, selected

    def _subdivide_for_holes(
        self, plate: trimesh.Trimesh, hole_size: float,
    ) -> trimesh.Trimesh:
        """Subdivide a mesh until faces are small enough for clean hole cutting."""
        target_area = (hole_size * 0.4) ** 2
        avg_area = plate.area / max(len(plate.faces), 1)
        result = plate
        for _ in range(3):
            if avg_area <= target_area:
                break
            try:
                new_v, new_f = trimesh.remesh.subdivide(
                    result.vertices, result.faces,
                )
                result = trimesh.Trimesh(vertices=new_v, faces=new_f, process=True)
                avg_area = result.area / max(len(result.faces), 1)
            except Exception:
                break
        logger.info(
            "Subdivide for holes: %d → %d faces (avg area %.2f mm²)",
            len(plate.faces), len(result.faces), avg_area,
        )
        return result

    def _boolean_mesh_holes(
        self, plate: trimesh.Trimesh, centers: np.ndarray, size: float,
    ) -> trimesh.Trimesh | None:
        avg_normal = self._plate_avg_normal(plate)
        result = plate
        holes_cut = 0
        for pt in centers:
            local_n = self._local_face_normal(result, pt, avg_normal)
            hole = trimesh.creation.cylinder(
                radius=size / 2, height=self.config.thickness * 4, sections=12,
            )
            rot = self._align_z_to(local_n)
            hole.apply_transform(rot)
            hole.apply_translation(pt)
            new_result = self._manifold_subtract(result, hole)
            if new_result is not None:
                result = new_result
                holes_cut += 1
        return result if holes_cut > 0 else None

    def _face_removal_mesh_holes(
        self, plate: trimesh.Trimesh, centers: np.ndarray, size: float,
    ) -> trimesh.Trimesh:
        """Remove faces whose centroid or any vertex is within the hole radius."""
        radius = size / 2
        face_centers = plate.triangles_center
        face_verts = plate.triangles
        keep = np.ones(len(plate.faces), dtype=bool)

        for pt in centers:
            cd = np.linalg.norm(face_centers - pt, axis=1)
            v0 = np.linalg.norm(face_verts[:, 0] - pt, axis=1)
            v1 = np.linalg.norm(face_verts[:, 1] - pt, axis=1)
            v2 = np.linalg.norm(face_verts[:, 2] - pt, axis=1)
            hit = (cd < radius) | (v0 < radius) | (v1 < radius) | (v2 < radius)
            keep &= ~hit

        n_removed = int(np.sum(~keep))
        if n_removed == 0:
            logger.warning("Mesh holes: no faces removed (hole_size=%.1fmm)", size)
            return plate

        result = plate.copy()
        result.update_faces(keep)
        result.remove_unreferenced_vertices()
        logger.info("Mesh holes (face-removal): removed %d / %d faces", n_removed, len(plate.faces))
        return result

    # ─── boolean / geometry helpers for mesh holes ────────────

    def _plate_avg_normal(self, plate: trimesh.Trimesh) -> np.ndarray:
        fn = plate.face_normals
        if len(fn) > 0:
            avg = fn.mean(axis=0)
            nrm = np.linalg.norm(avg)
            if nrm > 1e-10:
                return avg / nrm
        return np.array([0.0, 0.0, 1.0])

    def _local_face_normal(
        self, plate: trimesh.Trimesh, point: np.ndarray, fallback: np.ndarray,
    ) -> np.ndarray:
        try:
            _, _, face_idx = plate.nearest.on_surface([point])
            if face_idx is not None and len(face_idx) > 0:
                n = plate.face_normals[face_idx[0]]
                if np.linalg.norm(n) > 1e-10:
                    return n
        except Exception:
            pass
        return fallback

    @staticmethod
    def _align_z_to(target: np.ndarray) -> np.ndarray:
        """4x4 rotation that maps +Z to *target*."""
        z = np.array([0.0, 0.0, 1.0])
        t = target / (np.linalg.norm(target) + 1e-12)
        dot = float(np.dot(z, t))
        if dot > 1.0 - 1e-8:
            return np.eye(4)
        if dot < -1.0 + 1e-8:
            arb = np.array([1.0, 0.0, 0.0]) if abs(z[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            perp = np.cross(z, arb)
            perp /= np.linalg.norm(perp)
            return trimesh.transformations.rotation_matrix(np.pi, perp)
        axis = np.cross(z, t)
        axis /= np.linalg.norm(axis)
        angle = np.arccos(np.clip(dot, -1.0, 1.0))
        return trimesh.transformations.rotation_matrix(angle, axis)

    @staticmethod
    def _manifold_subtract(
        mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh,
    ) -> trimesh.Trimesh | None:
        try:
            import manifold3d
            m_a = manifold3d.Manifold(manifold3d.Mesh(
                vert_properties=np.asarray(mesh_a.vertices, dtype=np.float32),
                tri_verts=np.asarray(mesh_a.faces, dtype=np.uint32),
            ))
            m_b = manifold3d.Manifold(manifold3d.Mesh(
                vert_properties=np.asarray(mesh_b.vertices, dtype=np.float32),
                tri_verts=np.asarray(mesh_b.faces, dtype=np.uint32),
            ))
            diff = m_a - m_b
            out = diff.to_mesh()
            tm = trimesh.Trimesh(
                vertices=np.asarray(out.vert_properties[:, :3]),
                faces=np.asarray(out.tri_verts), process=True,
            )
            if len(tm.faces) > 4:
                return tm
        except Exception:
            pass
        try:
            r = mesh_a.difference(mesh_b)
            if r is not None and len(r.faces) > 4:
                return r
        except Exception:
            pass
        return None

    @staticmethod
    def _manifold_union(
        mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh,
    ) -> trimesh.Trimesh | None:
        try:
            import manifold3d
            m_a = manifold3d.Manifold(manifold3d.Mesh(
                vert_properties=np.asarray(mesh_a.vertices, dtype=np.float32),
                tri_verts=np.asarray(mesh_a.faces, dtype=np.uint32),
            ))
            m_b = manifold3d.Manifold(manifold3d.Mesh(
                vert_properties=np.asarray(mesh_b.vertices, dtype=np.float32),
                tri_verts=np.asarray(mesh_b.faces, dtype=np.uint32),
            ))
            uni = m_a + m_b
            out = uni.to_mesh()
            tm = trimesh.Trimesh(
                vertices=np.asarray(out.vert_properties[:, :3]),
                faces=np.asarray(out.tri_verts), process=True,
            )
            if len(tm.faces) > 4:
                return tm
        except Exception:
            pass
        try:
            r = mesh_a.union(mesh_b)
            if r is not None and len(r.faces) > 4:
                return r
        except Exception:
            pass
        return None

    def _interlock_surface_frames(
        self, plate: trimesh.Trimesh, points: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Per sample: surface anchor, inward axis (into plate solid), tangent, bitangent."""
        pts = np.asarray(points, dtype=np.float64)
        n_pts = len(pts)
        if n_pts == 0:
            z = np.zeros((0, 3))
            return z, z, z, z
        verts = np.asarray(plate.vertices, dtype=np.float64)
        faces = np.asarray(plate.faces, dtype=np.int64)
        tree = cKDTree(verts)
        _, vi = tree.query(pts, k=1)
        vi = np.atleast_1d(np.asarray(vi, dtype=np.int64))
        closest = verts[vi]
        c = np.asarray(plate.centroid, dtype=np.float64)
        fn = np.asarray(plate.face_normals, dtype=np.float64)
        n_out = np.zeros((n_pts, 3), dtype=np.float64)
        for i in range(n_pts):
            v = int(vi[i])
            inc = np.where((faces == v).any(axis=1))[0]
            if len(inc) == 0:
                n = np.array([0.0, 0.0, 1.0], dtype=np.float64)
            else:
                n = fn[int(inc[0])].copy()
            outv = closest[i] - c
            if np.dot(n, outv) < 0:
                n = -n
            nn = float(np.linalg.norm(n))
            n_out[i] = n / nn if nn > 1e-12 else np.array([0.0, 0.0, 1.0], dtype=np.float64)
        inward = -n_out
        arb = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        t = np.cross(inward, np.tile(arb, (n_pts, 1)))
        bad = np.linalg.norm(t, axis=1) < 1e-9
        if np.any(bad):
            arb2 = np.array([0.0, 1.0, 0.0], dtype=np.float64)
            t[bad] = np.cross(inward[bad], arb2)
        t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
        bit = np.cross(t, inward)
        bit /= np.linalg.norm(bit, axis=1, keepdims=True) + 1e-12
        return closest, inward, t, bit

    def _oriented_box_cutter(
        self,
        center: np.ndarray,
        tangent: np.ndarray,
        bitangent: np.ndarray,
        inward: np.ndarray,
        ext_t: float,
        ext_b: float,
        ext_in: float,
    ) -> trimesh.Trimesh:
        b = trimesh.creation.box(extents=[ext_t, ext_b, ext_in])
        T = np.eye(4)
        T[:3, 0] = tangent
        T[:3, 1] = bitangent
        T[:3, 2] = inward
        T[:3, 3] = center
        b.apply_transform(T)
        return b

    def _trapezoid_cutter_mesh(
        self,
        center: np.ndarray,
        tangent: np.ndarray,
        bitangent: np.ndarray,
        inward: np.ndarray,
        top_w: float,
        bot_w: float,
        d: float,
        h: float,
    ) -> trimesh.Trimesh:
        half_h = h / 2
        verts = np.array([
            [-top_w / 2, -d / 2, -half_h], [top_w / 2, -d / 2, -half_h],
            [bot_w / 2, -d / 2, half_h], [-bot_w / 2, -d / 2, half_h],
            [-top_w / 2, d / 2, -half_h], [top_w / 2, d / 2, -half_h],
            [bot_w / 2, d / 2, half_h], [-bot_w / 2, d / 2, half_h],
        ], dtype=np.float64)
        faces = np.array([
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
            [0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7],
        ], dtype=np.int64)
        T = np.eye(4)
        T[:3, 0] = tangent
        T[:3, 1] = bitangent
        T[:3, 2] = inward
        T[:3, 3] = center
        m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
        m.apply_transform(T)
        return m

    def _add_bumps(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        points = self._sample_pts(plate, max(n * 6, 24))
        selected = self._farthest_point_sampling(points, min(n, len(points)))
        closest, inward, _, _ = self._interlock_surface_frames(plate, selected)
        outward = -inward
        result = plate
        for i in range(len(selected)):
            ctr = closest[i] + outward[i] * (size * 0.35)
            bump = trimesh.creation.icosphere(radius=size * 0.45, subdivisions=1)
            bump.apply_translation(ctr)
            nu = self._manifold_union(result, bump)
            if nu is not None and len(nu.faces) > 4:
                result = nu
            else:
                with contextlib.suppress(Exception):
                    r = result.union(bump)
                    if r is not None and len(r.faces) > 4:
                        result = r
        return result, selected

    def _add_grooves(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        points = self._sample_pts(plate, max(n * 8, 32))
        selected = self._farthest_point_sampling(points, min(n, len(points)))
        closest, inward, t, bit = self._interlock_surface_frames(plate, selected)
        depth = max(self.config.thickness * 0.95, size * 1.1)
        L, W = size * 5.0, size * 0.5
        result = plate
        for i in range(len(selected)):
            ctr = closest[i] + inward[i] * (depth * 0.48)
            cutter = self._oriented_box_cutter(
                ctr, t[i], bit[i], inward[i], L, W, depth,
            )
            nu = self._manifold_subtract(result, cutter)
            if nu is not None and len(nu.faces) > 4:
                result = nu
        return result, selected

    def _add_dovetail(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        """Carve dovetail pockets into the outer face (silicone interlock), not protrusions."""
        points = self._sample_pts(plate, max(n * 8, 32))
        selected = self._farthest_point_sampling(points, min(n, len(points)))
        closest, inward, t, bit = self._interlock_surface_frames(plate, selected)
        depth = max(self.config.thickness * 0.9, size * 1.2)
        top_w, bot_w, d = size * 1.15, size * 0.42, size * 0.65
        result = plate
        for i in range(len(selected)):
            ctr = closest[i] + inward[i] * (depth * 0.48)
            cutter = self._trapezoid_cutter_mesh(
                ctr, t[i], bit[i], inward[i], top_w, bot_w, d, depth,
            )
            nu = self._manifold_subtract(result, cutter)
            if nu is not None and len(nu.faces) > 4:
                result = nu
        return result, selected

    def _add_diamond(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        points = self._sample_pts(plate, max(n * 8, 32))
        selected = self._farthest_point_sampling(points, min(n, len(points)))
        closest, inward, t, bit = self._interlock_surface_frames(plate, selected)
        h = max(self.config.thickness * 0.55, size * 0.75)
        s = size * 0.55
        result = plate
        for i in range(len(selected)):
            ctr = closest[i] + inward[i] * (h * 0.45)
            diamond = trimesh.creation.box(extents=[s, s, h])
            rot_loc = trimesh.transformations.rotation_matrix(np.pi / 4, [0, 0, 1])
            T = np.eye(4)
            T[:3, 0] = t[i]
            T[:3, 1] = bit[i]
            T[:3, 2] = inward[i]
            T[:3, 3] = ctr
            diamond.apply_transform(T @ rot_loc)
            nu = self._manifold_union(result, diamond)
            if nu is not None and len(nu.faces) > 4:
                result = nu
            else:
                with contextlib.suppress(Exception):
                    r = result.union(diamond)
                    if r is not None and len(r.faces) > 4:
                        result = r
        return result, selected

    # ═══════════════════════ Helpers ════════════════════════════════════

    def _estimate_section_area(self, tm: trimesh.Trimesh, normal: np.ndarray, plane_d: float) -> float:
        verts = np.asarray(tm.vertices)
        dists = verts @ normal - plane_d
        near = np.abs(dists) < float(np.max(tm.extents)) * 0.05
        if np.sum(near) < 3:
            ext = tm.extents
            dims = [ext[i] for i in range(3) if abs(normal[i]) < 0.5]
            return dims[0] * dims[1] * 0.6 if len(dims) >= 2 else 0.0
        nv = verts[near]
        up = normal / (np.linalg.norm(normal) + 1e-12)
        arb = np.array([1, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1, 0])
        u = np.cross(up, arb); u /= np.linalg.norm(u) + 1e-12
        v = np.cross(up, u)
        pu, pv = nv @ u, nv @ v
        return float((pu.max() - pu.min()) * (pv.max() - pv.min()) * 0.65)

    def _score_position(self, model: MeshData, normal: np.ndarray, plane_d: float, area: float, axis_idx: int) -> float:
        ext = model.extents
        max_ca = max(ext[0]*ext[1], ext[0]*ext[2], ext[1]*ext[2])
        ar = area / max_ca if max_ca > 0 else 0
        cv = np.dot(model.center, normal)
        span = float(np.dot(ext, np.abs(normal)))
        centrality = max(0, min(1, 1 - 2 * abs(plane_d - cv) / span)) if span > 0 else 0.5
        return min(1.0, max(0.0, 0.5 * ar + 0.35 * centrality + 0.15 * (0.1 if axis_idx >= 0 else 0)))

    def _get_cross_section(
        self, tm: trimesh.Trimesh, normal: np.ndarray, plane_d: float,
        thickness: float = 2.0,
    ) -> trimesh.Trimesh | None:
        """Cross-section → Shapely polygon → watertight extruded solid.

        The resulting mesh is guaranteed watertight, enabling reliable
        boolean operations for mesh holes and other features.
        """
        try:
            work = tm
            if len(tm.faces) > 20000:
                try:
                    work = tm.simplify_quadric_decimation(20000)
                except Exception:
                    pass
            section = work.section(plane_origin=normal * plane_d, plane_normal=normal)
            if section is not None:
                planar, transform = section.to_2D()
                poly = planar.polygons_full[0] if planar.polygons_full else None
                if poly is not None:
                    if hasattr(poly, 'simplify') and len(poly.exterior.coords) > 200:
                        poly = poly.simplify(0.5, preserve_topology=True)
                    plate = trimesh.creation.extrude_polygon(poly, height=thickness)
                    plate.apply_translation([0, 0, -thickness / 2])
                    plate.apply_transform(np.linalg.inv(transform))
                    return plate
        except Exception:
            pass
        return None

    def _generate_fallback_plate(self, model: MeshData, pos: InsertPosition) -> trimesh.Trimesh:
        ext = model.extents
        normal = pos.normal
        main = int(np.argmax(np.abs(normal)))
        dims = [ext[i] * self.config.plate_scale for i in range(3)]
        dims[main] = 0.1
        plate = trimesh.creation.box(extents=dims)
        plate.apply_translation(pos.origin)
        return plate

    def _extrude_section(self, section: trimesh.Trimesh, normal: np.ndarray, thickness: float) -> trimesh.Trimesh:
        offset = normal * thickness / 2
        v1 = section.vertices - offset
        v2 = section.vertices + offset
        verts = np.vstack([v1, v2])
        nv = len(section.vertices)
        f1 = section.faces
        f2 = (section.faces + nv)[:, ::-1]
        faces = np.vstack([f1, f2])
        edges = section.edges_unique
        sides = []
        for e in edges:
            a, b = e
            sides.append([a, b, b + nv])
            sides.append([a, b + nv, a + nv])
        if sides:
            faces = np.vstack([faces, np.array(sides)])
        return trimesh.Trimesh(vertices=verts, faces=faces, process=True)

    def _sample_pts(self, tm: trimesh.Trimesh, n: int) -> np.ndarray:
        try:
            pts, _ = trimesh.sample.sample_surface(tm, n)
            return pts
        except Exception:
            return tm.vertices[:min(n, len(tm.vertices))]

    def _farthest_point_sampling(self, points: np.ndarray, n: int) -> np.ndarray:
        if len(points) <= n:
            return points
        sel = [0]
        dists = np.full(len(points), np.inf)
        for _ in range(n - 1):
            d = np.linalg.norm(points - points[sel[-1]], axis=1)
            dists = np.minimum(dists, d)
            sel.append(int(np.argmax(dists)))
        return points[sel]

    def _get_pillar_direction(self, model: MeshData, side: str) -> np.ndarray:
        """Determine the pillar exit direction based on config.

        Supports: auto (shortest axis, negative), bottom (-Y), top (+Y),
        back (-Z), front (+Z), left (-X), right (+X).
        """
        if side == "bottom":
            return np.array([0.0, -1.0, 0.0])
        if side == "top":
            return np.array([0.0, 1.0, 0.0])
        if side == "back":
            return np.array([0.0, 0.0, -1.0])
        if side == "front":
            return np.array([0.0, 0.0, 1.0])
        if side == "left":
            return np.array([-1.0, 0.0, 0.0])
        if side == "right":
            return np.array([1.0, 0.0, 0.0])
        # "auto": pick the shortest axis (flattest face → back of model)
        ext = np.asarray(model.extents, dtype=np.float64)
        shortest = int(np.argmin(ext))
        d = np.zeros(3)
        d[shortest] = -1.0
        return d

    def _ray_cast(self, origin: np.ndarray, direction: np.ndarray, mesh: trimesh.Trimesh) -> np.ndarray | None:
        """Cast ray from origin along direction and find first model surface hit.

        Ignores intersections too close to origin (< 0.5mm) to avoid self-hits
        when origin is near or on the mesh surface.
        """
        try:
            locs, _, _ = mesh.ray.intersects_location(
                ray_origins=[origin], ray_directions=[direction],
            )
            if len(locs) > 0:
                d = np.linalg.norm(locs - origin, axis=1)
                # Filter out self-intersection hits
                valid = d > 0.5
                if np.any(valid):
                    valid_locs = locs[valid]
                    valid_d = d[valid]
                    return valid_locs[np.argmin(valid_d)].copy()
        except Exception:
            pass
        return None

    def _make_strut(self, p1: np.ndarray, p2: np.ndarray, radius: float) -> trimesh.Trimesh | None:
        diff = p2 - p1
        length = float(np.linalg.norm(diff))
        if length < 1e-6:
            return None
        try:
            cyl = trimesh.creation.cylinder(radius=radius, height=length, sections=8)
            direction = diff / length
            z = np.array([0, 0, 1.0])
            dot = np.dot(z, direction)
            if abs(dot) > 0.999:
                T = np.eye(4)
                if dot < 0:
                    T[2, 2] = -1; T[1, 1] = -1
            else:
                ax = np.cross(z, direction)
                ax /= np.linalg.norm(ax) + 1e-12
                ang = math.acos(np.clip(dot, -1, 1))
                T = trimesh.transformations.rotation_matrix(ang, ax)
            T[:3, 3] = (p1 + p2) / 2
            cyl.apply_transform(T)
            return cyl
        except Exception:
            return None
