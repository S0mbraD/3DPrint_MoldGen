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

    add_ribs: bool = False             # reinforcement ribs on plate surface
    rib_height: float = 3.0
    rib_width: float = 1.5
    rib_spacing: float = 8.0

    add_interlocking: str | None = None  # "dovetail"|"diamond"|"grooves"|"bumps"|None
    interlock_feature_size: float = 2.0

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
        """Generate base plate (flat or conformal), then apply optional features."""
        cfg = self.config
        itype = cfg.insert_type

        # Step 1: Generate base plate shape
        if itype == InsertType.CONFORMAL:
            plate_mesh = self._generate_conformal(model, position)
        elif itype == InsertType.RIBBED:
            # Legacy: map to flat + ribs
            plate_mesh = self._generate_flat(model, position)
            cfg.add_ribs = True
        elif itype == InsertType.LATTICE:
            # Legacy: map to flat + mesh holes
            plate_mesh = self._generate_flat(model, position)
            cfg.add_mesh_holes = True
        else:
            plate_mesh = self._generate_flat(model, position)

        # Step 2: Ensure plate is inside the model
        plate_mesh = self._ensure_interior(plate_mesh, model)

        # Step 3: Apply optional features to the base plate
        features_applied: list[str] = []

        if cfg.add_mesh_holes:
            n_holes = max(3, int(plate_mesh.area * cfg.mesh_hole_density / (cfg.mesh_hole_size ** 2)))
            n_holes = min(n_holes, 8)
            plate_mesh, _ = self._add_mesh_holes(plate_mesh, n_holes, cfg.mesh_hole_size)
            features_applied.append("mesh_holes")

        if cfg.add_ribs:
            plate_mesh = self._apply_ribs(plate_mesh, position)
            features_applied.append("ribs")

        if cfg.add_interlocking:
            interlock_type = cfg.add_interlocking
            n_feat = max(3, int(plate_mesh.area * 0.2 / (cfg.interlock_feature_size ** 2)))
            n_feat = min(n_feat, 6)
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
                plate.anchor = AnchorFeature(
                    type=AnchorType(anchor_type_name) if anchor_type_name in AnchorType.__members__.values() else AnchorType.MESH_HOLES,
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
        section = self._get_cross_section(tm, pos.normal, pos.plane_d)
        if section is None:
            section = self._generate_fallback_plate(model, pos)
        plate = self._extrude_section(section, pos.normal, cfg.thickness)
        return plate

    def _generate_conformal(self, model: MeshData, pos: InsertPosition) -> trimesh.Trimesh:
        """Conformal plate via grid projection — fast vectorized approach."""
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

        grid_res = min(30, max(8, int(half_span * 2 / 2.5)))

        lu = np.linspace(-half_span, half_span, grid_res)
        lv = np.linspace(-half_span, half_span, grid_res)
        gu, gv = np.meshgrid(lu, lv, indexing="ij")
        flat_u, flat_v = gu.ravel(), gv.ravel()
        n_pts = len(flat_u)

        grid_3d = (plane_origin[None, :] +
                    flat_u[:, None] * u_ax[None, :] +
                    flat_v[:, None] * v_ax[None, :])

        tree = cKDTree(tm.vertices)
        dists, indices = tree.query(grid_3d, k=1, workers=-1)
        max_dist = half_span * 0.8
        valid = dists < max_dist

        if np.sum(valid) < 9:
            return self._generate_flat(model, pos)

        surf_pts = tm.vertices[indices]
        surf_normals = np.asarray(tm.vertex_normals, dtype=np.float64)[indices]
        offset = cfg.conformal_offset

        close_mask = dists < offset * 5
        inner = np.where(close_mask[:, None],
                         surf_pts + surf_normals * (-offset),
                         grid_3d - up[None, :] * offset)
        outer = inner + up[None, :] * cfg.thickness

        ri, ci = np.meshgrid(np.arange(grid_res - 1), np.arange(grid_res - 1), indexing="ij")
        ri, ci = ri.ravel(), ci.ravel()
        tl = ri * grid_res + ci
        tr = tl + 1
        bl = tl + grid_res
        br = bl + 1

        quad_valid = valid[tl] & valid[tr] & valid[bl] & valid[br]
        tl, tr, bl, br = tl[quad_valid], tr[quad_valid], bl[quad_valid], br[quad_valid]

        if len(tl) < 4:
            return self._generate_flat(model, pos)

        inner_faces = np.vstack([np.column_stack([tl, tr, br]),
                                  np.column_stack([tl, br, bl])])
        outer_faces = np.vstack([np.column_stack([tl + n_pts, br + n_pts, tr + n_pts]),
                                  np.column_stack([tl + n_pts, bl + n_pts, br + n_pts])])

        all_verts = np.vstack([inner, outer])
        all_faces = np.vstack([inner_faces, outer_faces])

        plate = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
        _clean_mesh(plate)
        return plate

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
        """Add reinforcement ribs to an existing plate mesh."""
        cfg = self.config
        normal = pos.normal
        main_ax = int(np.argmax(np.abs(normal)))
        bounds = np.array([plate_mesh.vertices.min(axis=0), plate_mesh.vertices.max(axis=0)])
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
            return plate_mesh
        try:
            combined = trimesh.util.concatenate([plate_mesh] + ribs)
            _clean_mesh(combined)
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
        points = self._sample_pts(plate, n * 3)
        selected = self._farthest_point_sampling(points, n)
        result = plate
        for pt in selected:
            hole = trimesh.creation.cylinder(radius=size / 2, height=self.config.thickness * 3, sections=8)
            hole.apply_translation(pt)
            with contextlib.suppress(Exception):
                r = result.difference(hole)
                if r is not None and len(r.faces) > 4:
                    result = r
        return result, selected

    def _add_bumps(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        points = self._sample_pts(plate, n * 3)
        selected = self._farthest_point_sampling(points, n)
        result = plate
        for pt in selected:
            bump = trimesh.creation.icosphere(radius=size / 2, subdivisions=1)
            bump.apply_translation(pt)
            with contextlib.suppress(Exception):
                r = result.union(bump)
                if r is not None and len(r.faces) > 4:
                    result = r
        return result, selected

    def _add_grooves(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        points = self._sample_pts(plate, n * 2)
        selected = self._farthest_point_sampling(points, min(n, len(points)))
        result = plate
        for pt in selected:
            groove = trimesh.creation.box(extents=[size * 3, size * 0.5, self.config.thickness * 1.5])
            groove.apply_translation(pt)
            with contextlib.suppress(Exception):
                r = result.difference(groove)
                if r is not None and len(r.faces) > 4:
                    result = r
        return result, selected

    def _add_dovetail(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        points = self._sample_pts(plate, n * 2)
        selected = self._farthest_point_sampling(points, min(n, len(points)))
        result = plate
        for pt in selected:
            trap = trimesh.creation.box(extents=[size, size * 0.6, self.config.thickness * 0.4])
            trap.apply_translation(pt + np.array([0, 0, self.config.thickness * 0.3]))
            with contextlib.suppress(Exception):
                r = result.union(trap)
                if r is not None and len(r.faces) > 4:
                    result = r
        return result, selected

    def _add_diamond(self, plate: trimesh.Trimesh, n: int, size: float) -> tuple[trimesh.Trimesh, np.ndarray]:
        points = self._sample_pts(plate, n * 2)
        selected = self._farthest_point_sampling(points, min(n, len(points)))
        result = plate
        for pt in selected:
            diamond = trimesh.creation.box(extents=[size * 0.5, size * 0.5, self.config.thickness * 0.3])
            rot = trimesh.transformations.rotation_matrix(np.pi / 4, [0, 0, 1])
            diamond.apply_transform(rot)
            diamond.apply_translation(pt)
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

    def _get_cross_section(self, tm: trimesh.Trimesh, normal: np.ndarray, plane_d: float) -> trimesh.Trimesh | None:
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
                    mesh_2d = trimesh.creation.extrude_polygon(poly, height=0.1)
                    mesh_2d.apply_transform(np.linalg.inv(transform))
                    return mesh_2d
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
