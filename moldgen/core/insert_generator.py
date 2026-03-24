"""支撑板生成器 — 自动分析模型结构并生成内嵌支撑板 (v2: 多类型支撑板)

支持 4 种板型:
  flat     — 平面截面挤出 (经典方式)
  conformal — 仿形板: 沿模型表面偏移, 跟随曲面轮廓
  ribbed   — 加强筋板: 平板 + 交叉肋条, 提高结构刚度
  lattice  — 拓扑优化格栅: 轻量化点阵结构, 最大刚度/重量比
"""

from __future__ import annotations

import contextlib
import logging
import math
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


def _clean_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Remove degenerate faces and unreferenced vertices (trimesh 4.x compatible)."""
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


class OrganType(StrEnum):
    SOLID = "solid"       # 实质性器官 (肝/肾/脑)
    HOLLOW = "hollow"     # 空腔器官 (胃/膀胱)
    TUBULAR = "tubular"   # 管道结构 (血管/肠道)
    SHEET = "sheet"       # 组织片 (皮肤/肌肉)
    GENERAL = "general"


class InsertType(StrEnum):
    FLAT = "flat"
    CONFORMAL = "conformal"
    RIBBED = "ribbed"
    LATTICE = "lattice"


class AnchorType(StrEnum):
    MESH_HOLES = "mesh_holes"     # 网孔
    BUMPS = "bumps"               # 凸起
    GROOVES = "grooves"           # 沟槽
    DOVETAIL = "dovetail"         # 燕尾
    DIAMOND = "diamond"           # 菱形纹


ORGAN_ANCHOR_MAP: dict[OrganType, AnchorType] = {
    OrganType.SOLID: AnchorType.MESH_HOLES,
    OrganType.HOLLOW: AnchorType.GROOVES,
    OrganType.TUBULAR: AnchorType.BUMPS,
    OrganType.SHEET: AnchorType.DIAMOND,
    OrganType.GENERAL: AnchorType.MESH_HOLES,
}


@dataclass
class InsertConfig:
    thickness: float = 2.0          # 板厚 mm
    edge_chamfer: float = 0.5       # 边缘倒角 mm
    margin: float = 1.5             # 距模型边界裕量 mm
    min_area_ratio: float = 0.15    # 最小面积比（板/截面）
    insert_type: InsertType = InsertType.FLAT
    # Conformal params
    conformal_offset: float = 3.0   # offset distance from model surface (mm)
    conformal_smoothing: int = 2    # Laplacian smoothing iterations
    # Ribbed params
    rib_height: float = 3.0         # rib height above base plate (mm)
    rib_width: float = 1.5          # rib cross-section width (mm)
    rib_spacing: float = 8.0        # spacing between ribs (mm)
    # Lattice params
    lattice_cell_size: float = 5.0  # unit cell dimension (mm)
    lattice_strut_diameter: float = 1.2  # strut thickness (mm)
    lattice_type: str = "bcc"       # "bcc" | "octet" | "gyroid"
    # Organ / anchor
    organ_type: OrganType = OrganType.GENERAL
    anchor_type: AnchorType | None = None
    anchor_density: float = 0.3     # 锚固覆盖率 (0-1)
    anchor_feature_size: float = 2.0  # 锚固特征尺寸 mm


@dataclass
class InsertPosition:
    """描述支撑板放置位置"""
    origin: np.ndarray        # 板中心点
    normal: np.ndarray        # 板法线方向
    plane_d: float            # 平面方程 ax+by+cz=d
    score: float = 0.0        # 适合度评分 0-1
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
    """单个锚固特征"""
    type: AnchorType
    positions: np.ndarray   # (K, 3)
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
    """生成的支撑板"""
    mesh: MeshData
    position: InsertPosition
    insert_type: str = "flat"
    anchor: AnchorFeature | None = None
    thickness: float = 2.0
    locating_slots: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "face_count": self.mesh.face_count,
            "vertex_count": self.mesh.vertex_count,
            "thickness": self.thickness,
            "insert_type": self.insert_type,
            "position": self.position.to_dict(),
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "n_locating_slots": len(self.locating_slots),
        }


@dataclass
class InsertResult:
    """支撑板生成结果"""
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


class InsertGenerator:
    """支撑板生成器"""

    def __init__(self, config: InsertConfig | None = None):
        self.config = config or InsertConfig()

    def analyze_positions(self, model: MeshData, n_candidates: int = 5) -> list[InsertPosition]:
        """分析模型结构，找出最佳支撑板位置 (uses fast area estimation)"""
        tm = model.to_trimesh()
        # Decimate for analysis speed
        if len(tm.faces) > 15000:
            try:
                tm = tm.simplify_quadric_decimation(15000)
            except Exception:
                pass
        center = model.center
        positions: list[InsertPosition] = []

        # Strategy 1: Cross-section sweep along each principal axis
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

        # Strategy 2: Use PCA to find the flattest direction
        try:
            from sklearn.decomposition import PCA  # noqa: F811
            pca = PCA(n_components=3)
            pca.fit(model.vertices)
            for i, comp in enumerate(pca.components_):
                normal = comp / np.linalg.norm(comp)
                plane_d = float(np.dot(center, normal))
                area = self._estimate_section_area(tm, normal, plane_d)
                if area > 1.0:
                    score = self._score_position(model, normal, plane_d, area, -1)
                    positions.append(InsertPosition(
                        origin=center.copy(), normal=normal, plane_d=plane_d,
                        score=score * 0.9, section_area=area,
                        reason=f"PCA 主成分 {i+1}",
                    ))
        except ImportError:
            pass

        positions.sort(key=lambda p: p.score, reverse=True)
        return positions[:n_candidates]

    def generate_plate(
        self, model: MeshData, position: InsertPosition,
    ) -> InsertPlate:
        """在指定位置生成支撑板 (根据 insert_type 分发)"""
        cfg = self.config
        itype = cfg.insert_type

        if itype == InsertType.CONFORMAL:
            plate_mesh = self._generate_conformal(model, position)
        elif itype == InsertType.RIBBED:
            plate_mesh = self._generate_ribbed(model, position)
        elif itype == InsertType.LATTICE:
            plate_mesh = self._generate_lattice(model, position)
        else:
            plate_mesh = self._generate_flat(model, position)

        plate_data = MeshData.from_trimesh(plate_mesh)

        return InsertPlate(
            mesh=plate_data,
            position=position,
            insert_type=itype.value,
            thickness=cfg.thickness,
        )

    def _generate_flat(
        self, model: MeshData, position: InsertPosition,
    ) -> trimesh.Trimesh:
        """Classic flat cross-section plate."""
        tm = model.to_trimesh()
        cfg = self.config

        section = self._get_cross_section(tm, position.normal, position.plane_d)
        if section is None:
            section = self._generate_fallback_plate(model, position)

        plate_mesh = self._extrude_section(section, position.normal, cfg.thickness)
        return self._apply_chamfer(plate_mesh, cfg.edge_chamfer)

    def _generate_conformal(
        self, model: MeshData, position: InsertPosition,
    ) -> trimesh.Trimesh:
        """Conformal plate — grid-based surface projection (vectorized).

        Instead of section→extrude→project (slow), we directly sample a 2D
        grid on the cutting plane, project grid points onto the model surface
        via vectorized cKDTree query, then triangulate the grid.  O(grid_res²)
        with no Python loops in the hot path.
        """
        import time
        t0 = time.perf_counter()

        tm = model.to_trimesh()
        cfg = self.config
        normal = np.asarray(position.normal, dtype=np.float64)
        plane_d = position.plane_d

        # Build local coordinate frame on the cutting plane
        up = normal / (np.linalg.norm(normal) + 1e-12)
        arb = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0.0, 1, 0])
        u_ax = np.cross(up, arb);  u_ax /= (np.linalg.norm(u_ax) + 1e-12)
        v_ax = np.cross(up, u_ax); v_ax /= (np.linalg.norm(v_ax) + 1e-12)

        # Model bounds projected onto the cutting plane
        center = np.asarray(model.center, dtype=np.float64)
        plane_origin = center + up * (plane_d - np.dot(center, up))
        extents = model.extents
        half_span = float(np.max(extents)) * 0.55

        # Adaptive grid resolution: enough detail but bounded
        grid_res = min(40, max(10, int(half_span * 2 / 2.0)))
        logger.info("Conformal: grid %dx%d, span=%.1f", grid_res, grid_res, half_span * 2)

        # Generate grid points on cutting plane (vectorized)
        lu = np.linspace(-half_span, half_span, grid_res)
        lv = np.linspace(-half_span, half_span, grid_res)
        gu, gv = np.meshgrid(lu, lv, indexing="ij")
        flat_u = gu.ravel()
        flat_v = gv.ravel()
        n_pts = len(flat_u)
        grid_3d = (plane_origin[np.newaxis, :]
                    + flat_u[:, np.newaxis] * u_ax[np.newaxis, :]
                    + flat_v[:, np.newaxis] * v_ax[np.newaxis, :])

        # Vectorized nearest-surface query
        tree = cKDTree(tm.vertices)
        dists, indices = tree.query(grid_3d, k=1, workers=-1)
        model_normals = np.asarray(tm.vertex_normals, dtype=np.float64)

        # Mask: only keep grid points near the model surface
        max_dist = half_span * 0.8
        valid = dists < max_dist

        # Check if the nearest surface point is actually "inside" the model outline
        nearest_pts = tm.vertices[indices]
        proj_u = np.sum((nearest_pts - plane_origin) * u_ax, axis=1)
        proj_v = np.sum((nearest_pts - plane_origin) * v_ax, axis=1)
        in_range = (np.abs(proj_u) < half_span * 0.95) & (np.abs(proj_v) < half_span * 0.95)
        valid &= in_range

        if np.sum(valid) < 9:
            logger.warning("Conformal: too few valid points (%d), falling back", np.sum(valid))
            return self._generate_flat(model, position)

        # Project valid grid points onto model surface + offset
        surf_pts = tm.vertices[indices]
        surf_normals = model_normals[indices]
        offset_amount = cfg.conformal_offset

        close_mask = dists < offset_amount * 5
        inner_verts = np.where(
            close_mask[:, np.newaxis],
            surf_pts + surf_normals * offset_amount,
            grid_3d + up[np.newaxis, :] * offset_amount,
        )
        outer_verts = inner_verts + up[np.newaxis, :] * cfg.thickness

        # Build quad grid → triangles (vectorized, no Python loops)
        row_idx = np.arange(grid_res - 1)
        col_idx = np.arange(grid_res - 1)
        ri, ci = np.meshgrid(row_idx, col_idx, indexing="ij")
        ri = ri.ravel()
        ci = ci.ravel()

        tl = ri * grid_res + ci
        tr = ri * grid_res + ci + 1
        bl = (ri + 1) * grid_res + ci
        br = (ri + 1) * grid_res + ci + 1

        # Only keep quads where all 4 corners are valid
        quad_valid = valid[tl] & valid[tr] & valid[bl] & valid[br]
        tl = tl[quad_valid]
        tr = tr[quad_valid]
        bl = bl[quad_valid]
        br = br[quad_valid]

        if len(tl) < 4:
            logger.warning("Conformal: too few valid quads (%d), falling back", len(tl))
            return self._generate_flat(model, position)

        # Inner face triangles (2 per quad)
        inner_f1 = np.column_stack([tl, tr, br])
        inner_f2 = np.column_stack([tl, br, bl])
        inner_faces = np.vstack([inner_f1, inner_f2])

        # Outer faces (reversed winding)
        outer_f1 = np.column_stack([tl + n_pts, br + n_pts, tr + n_pts])
        outer_f2 = np.column_stack([tl + n_pts, bl + n_pts, br + n_pts])
        outer_faces = np.vstack([outer_f1, outer_f2])

        # Side faces along boundary (edge quads where one neighbor is invalid)
        all_verts = np.vstack([inner_verts, outer_verts])
        all_faces = np.vstack([inner_faces, outer_faces])

        # Build boundary edges from the valid mask grid
        boundary_edges = []
        for ri_b in range(grid_res):
            for ci_b in range(grid_res):
                idx_here = ri_b * grid_res + ci_b
                if not valid[idx_here]:
                    continue
                # Right neighbor
                if ci_b + 1 < grid_res:
                    idx_right = idx_here + 1
                    if not valid[idx_right]:
                        boundary_edges.append((idx_here, idx_here))
                elif valid[idx_here]:
                    boundary_edges.append((idx_here, idx_here))
                # Bottom neighbor
                if ri_b + 1 < grid_res:
                    idx_below = idx_here + grid_res
                    if not valid[idx_below]:
                        boundary_edges.append((idx_here, idx_here))

        # Connect inner and outer shells along boundary with simple side quads
        valid_boundary = set()
        for ri_b in range(grid_res):
            for ci_b in range(grid_res):
                idx_c = ri_b * grid_res + ci_b
                if not valid[idx_c]:
                    continue
                is_boundary = False
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = ri_b + dr, ci_b + dc
                    if nr < 0 or nr >= grid_res or nc < 0 or nc >= grid_res:
                        is_boundary = True
                        break
                    if not valid[nr * grid_res + nc]:
                        is_boundary = True
                        break
                if is_boundary:
                    valid_boundary.add(idx_c)

        # Create side triangles for boundary edges
        side_faces_list = []
        boundary_sorted = sorted(valid_boundary)
        for i_b in range(len(boundary_sorted) - 1):
            a = boundary_sorted[i_b]
            b = boundary_sorted[i_b + 1]
            # Only connect adjacent grid points
            ra, ca = divmod(a, grid_res)
            rb, cb = divmod(b, grid_res)
            if abs(ra - rb) + abs(ca - cb) == 1:
                side_faces_list.append([a, b, b + n_pts])
                side_faces_list.append([a, b + n_pts, a + n_pts])

        if side_faces_list:
            all_faces = np.vstack([all_faces, np.array(side_faces_list, dtype=np.int64)])

        plate = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
        _clean_mesh(plate)

        elapsed = time.perf_counter() - t0
        logger.info(
            "Conformal plate: %d verts, %d faces, %.2fs",
            len(plate.vertices), len(plate.faces), elapsed,
        )
        return plate

    def _generate_ribbed(
        self, model: MeshData, position: InsertPosition,
    ) -> trimesh.Trimesh:
        """Plate with cross-pattern reinforcement ribs."""
        flat_plate = self._generate_flat(model, position)
        cfg = self.config

        normal = position.normal
        abs_n = np.abs(normal)
        main_ax = int(np.argmax(abs_n))

        bounds = np.array([flat_plate.vertices.min(axis=0), flat_plate.vertices.max(axis=0)])
        center = (bounds[0] + bounds[1]) / 2
        extents = bounds[1] - bounds[0]

        axes = [i for i in range(3) if i != main_ax]
        if len(axes) < 2:
            return flat_plate

        ribs: list[trimesh.Trimesh] = []

        for ax_idx in axes:
            lo = float(bounds[0][ax_idx]) + cfg.rib_spacing / 2
            hi = float(bounds[1][ax_idx]) - cfg.rib_spacing / 2
            n_ribs = max(1, int((hi - lo) / cfg.rib_spacing) + 1)

            for ri in range(n_ribs):
                pos_val = lo + ri * cfg.rib_spacing if n_ribs > 1 else (lo + hi) / 2

                rib_extents = [0.0, 0.0, 0.0]
                rib_extents[ax_idx] = cfg.rib_width
                other_ax = [a for a in axes if a != ax_idx][0] if len(axes) > 1 else axes[0]
                rib_extents[other_ax] = float(extents[other_ax]) * 0.9
                rib_extents[main_ax] = cfg.rib_height

                rib_center = center.copy()
                rib_center[ax_idx] = pos_val
                rib_center[main_ax] += (cfg.thickness / 2 + cfg.rib_height / 2) * (
                    1 if normal[main_ax] >= 0 else -1
                )

                rib = trimesh.creation.box(extents=rib_extents)
                rib.apply_translation(rib_center)
                ribs.append(rib)

        if not ribs:
            return flat_plate

        try:
            all_parts = [flat_plate] + ribs
            combined = trimesh.util.concatenate(all_parts)
            _clean_mesh(combined)
            return combined
        except Exception:
            return flat_plate

    def _generate_lattice(
        self, model: MeshData, position: InsertPosition,
    ) -> trimesh.Trimesh:
        """BCC lattice — pre-compute all strut endpoints, batch-create, cap at 200 struts."""
        import time
        t0 = time.perf_counter()

        cfg = self.config
        normal = np.asarray(position.normal, dtype=np.float64)
        extents = model.extents
        center = np.asarray(model.center, dtype=np.float64)

        abs_n = np.abs(normal)
        main_ax = int(np.argmax(abs_n))
        axes = [i for i in range(3) if i != main_ax]

        cell = cfg.lattice_cell_size
        r = cfg.lattice_strut_diameter / 2

        span = [float(extents[axes[0]]) * 0.6, 0.0, cfg.thickness]
        span[1] = float(extents[axes[1]]) * 0.6 if len(axes) > 1 else cell * 2

        nx = max(2, min(8, int(span[0] / cell)))
        ny = max(2, min(8, int(span[1] / cell)))
        nz = max(1, min(3, int(span[2] / cell) + 1))

        logger.info("Lattice: grid %dx%dx%d, cell=%.1f", nx, ny, nz, cell)

        origin = center.copy()
        origin[axes[0]] -= nx * cell / 2
        origin[axes[1]] -= ny * cell / 2 if len(axes) > 1 else 0
        origin[main_ax] -= nz * cell / 2

        # Pre-compute all strut endpoints (vectorized)
        endpoints: list[tuple[np.ndarray, np.ndarray]] = []

        for ix in range(nx + 1):
            for iy in range(ny + 1):
                for iz in range(nz + 1):
                    pt = origin.copy()
                    pt[axes[0]] += ix * cell
                    if len(axes) > 1:
                        pt[axes[1]] += iy * cell
                    pt[main_ax] += iz * cell

                    # Edge struts
                    if ix < nx:
                        end = pt.copy(); end[axes[0]] += cell
                        endpoints.append((pt.copy(), end))
                    if len(axes) > 1 and iy < ny:
                        end = pt.copy(); end[axes[1]] += cell
                        endpoints.append((pt.copy(), end))
                    if iz < nz:
                        end = pt.copy(); end[main_ax] += cell
                        endpoints.append((pt.copy(), end))

                    # BCC diagonal struts (corner → cell center)
                    if ix < nx and iy < ny and iz < nz:
                        cc = pt.copy()
                        cc[axes[0]] += cell / 2
                        if len(axes) > 1:
                            cc[axes[1]] += cell / 2
                        cc[main_ax] += cell / 2
                        for dx in [0, cell]:
                            for dy in [0, cell]:
                                for dz in [0, cell]:
                                    corner = pt.copy()
                                    corner[axes[0]] += dx
                                    if len(axes) > 1:
                                        corner[axes[1]] += dy
                                    corner[main_ax] += dz
                                    endpoints.append((cc.copy(), corner))

        # Cap strut count for performance
        MAX_STRUTS = 200
        if len(endpoints) > MAX_STRUTS:
            step = len(endpoints) // MAX_STRUTS
            endpoints = endpoints[::step][:MAX_STRUTS]

        logger.info("Lattice: %d struts to generate", len(endpoints))

        # Batch-create struts using low-poly cylinders (4 sections)
        struts: list[trimesh.Trimesh] = []
        for p1, p2 in endpoints:
            s = self._make_strut_fast(p1, p2, r)
            if s is not None:
                struts.append(s)

        if not struts:
            return self._generate_flat(model, position)

        combined = trimesh.util.concatenate(struts)
        _clean_mesh(combined)

        elapsed = time.perf_counter() - t0
        logger.info("Lattice: %d verts, %d faces, %.2fs", len(combined.vertices), len(combined.faces), elapsed)
        return combined

    def _make_strut_fast(
        self, p1: np.ndarray, p2: np.ndarray, radius: float,
    ) -> trimesh.Trimesh | None:
        """Ultra-fast strut: 4-section cylinder with direct transform."""
        diff = p2 - p1
        length = float(np.linalg.norm(diff))
        if length < 1e-6:
            return None
        try:
            cyl = trimesh.creation.cylinder(radius=radius, height=length, sections=4)
            direction = diff / length
            z = np.array([0.0, 0.0, 1.0])
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

    def add_anchor(self, plate: InsertPlate) -> InsertPlate:
        """为支撑板添加锚固结构 (capped at 8 features to avoid slow booleans)"""
        cfg = self.config
        anchor_type = cfg.anchor_type or ORGAN_ANCHOR_MAP.get(cfg.organ_type, AnchorType.MESH_HOLES)

        plate_tm = plate.mesh.to_trimesh()
        surface_area = plate_tm.area
        n_features = min(8, max(4, int(surface_area * cfg.anchor_density / (cfg.anchor_feature_size ** 2))))

        if anchor_type == AnchorType.MESH_HOLES:
            plate_tm, feature_positions = self._add_mesh_holes(plate_tm, n_features, cfg.anchor_feature_size)
        elif anchor_type == AnchorType.BUMPS:
            plate_tm, feature_positions = self._add_bumps(plate_tm, n_features, cfg.anchor_feature_size)
        elif anchor_type == AnchorType.GROOVES:
            plate_tm, feature_positions = self._add_grooves(plate_tm, n_features, cfg.anchor_feature_size)
        elif anchor_type == AnchorType.DOVETAIL:
            plate_tm, feature_positions = self._add_dovetail(plate_tm, n_features, cfg.anchor_feature_size)
        else:  # DIAMOND
            plate_tm, feature_positions = self._add_diamond(plate_tm, n_features, cfg.anchor_feature_size)

        plate.mesh = MeshData.from_trimesh(plate_tm)
        plate.anchor = AnchorFeature(
            type=anchor_type,
            positions=feature_positions,
            feature_size=cfg.anchor_feature_size,
            count=len(feature_positions),
        )
        return plate

    def generate_locating_slots(
        self, plate: InsertPlate, mold_shells: list[MeshData],
    ) -> list[dict]:
        """在模具壳体上生成支撑板定位槽"""
        slots = []
        pos = plate.position
        half_t = plate.thickness / 2.0 + self.config.margin * 0.3

        for i, _shell_data in enumerate(mold_shells):
            slot_vertices = []
            slot_origin = pos.origin.copy()
            for sign in [-1, 1]:
                offset = pos.normal * half_t * sign
                slot_vertices.append(slot_origin + offset)

            slot_info = {
                "shell_index": i,
                "origin": slot_origin.tolist(),
                "normal": pos.normal.tolist(),
                "width": float(plate.thickness + self.config.margin * 0.6),
                "depth": 1.5,
            }
            slots.append(slot_info)

        plate.locating_slots = slots
        return slots

    def validate_assembly(
        self, model: MeshData, plates: list[InsertPlate],
        mold_shells: list[MeshData] | None = None,
    ) -> tuple[bool, list[str]]:
        """验证支撑板装配可行性"""
        messages: list[str] = []
        all_valid = True

        model_bounds = model.bounds

        for i, plate in enumerate(plates):
            plate_tm = plate.mesh.to_trimesh()
            plate_bounds = np.array([plate_tm.vertices.min(axis=0), plate_tm.vertices.max(axis=0)])

            # Check 1: Plate within model bounds (with margin)
            margin = self.config.margin
            expanded_bounds = np.array([
                model_bounds[0] - margin,
                model_bounds[1] + margin,
            ])
            if np.any(plate_bounds[0] < expanded_bounds[0] - 1.0) or \
               np.any(plate_bounds[1] > expanded_bounds[1] + 1.0):
                messages.append(f"板{i+1}: 超出模型边界")
                all_valid = False

            # Check 2: Minimum thickness check
            if plate.thickness < 1.0:
                messages.append(f"板{i+1}: 厚度过薄({plate.thickness}mm)，建议>=1.5mm")
                all_valid = False

            # Check 3: Plate area check
            if plate.position.section_area < 10.0:
                messages.append(f"板{i+1}: 截面积过小({plate.position.section_area:.1f}mm²)")

            # Check 4: Anchor feature check
            if plate.anchor is None:
                messages.append(f"板{i+1}: 未添加锚固结构，硅胶结合可能不牢固")

            # Check 5: Plate intersection check (AABB overlap, fast)
            for j in range(i + 1, len(plates)):
                other_tm = plates[j].mesh.to_trimesh()
                other_bounds = np.array([other_tm.vertices.min(axis=0), other_tm.vertices.max(axis=0)])
                if (np.all(plate_bounds[0] < other_bounds[1]) and
                    np.all(other_bounds[0] < plate_bounds[1])):
                    messages.append(f"板{i+1}与板{j+1}: 包围盒重叠，可能存在干涉")

        if all_valid and not messages:
            messages.append("装配验证通过")

        return all_valid, messages

    def full_pipeline(
        self, model: MeshData, mold_shells: list[MeshData] | None = None,
        n_plates: int = 1,
    ) -> InsertResult:
        """完整支撑板生成流程 (optimized: skip slow anchor booleans for conformal/lattice)"""
        import time
        t0 = time.perf_counter()

        positions = self.analyze_positions(model, n_candidates=max(n_plates * 2, 5))
        plates: list[InsertPlate] = []

        for pos in positions[:n_plates]:
            plate = self.generate_plate(model, pos)
            # Skip anchor booleans for complex types (they already have structural features)
            if self.config.insert_type == InsertType.FLAT:
                plate = self.add_anchor(plate)
            if mold_shells:
                self.generate_locating_slots(plate, mold_shells)
            plates.append(plate)

        is_valid, msgs = self.validate_assembly(model, plates, mold_shells)

        elapsed = time.perf_counter() - t0
        logger.info("Insert pipeline: %d plates, %.2fs", len(plates), elapsed)

        return InsertResult(
            plates=plates,
            positions_analyzed=positions,
            assembly_valid=is_valid,
            validation_messages=msgs,
        )

    # ── Private helpers ──────────────────────────────────────────────

    def _estimate_section_area(
        self, tm: trimesh.Trimesh, normal: np.ndarray, plane_d: float,
    ) -> float:
        """Fast section area estimate using vertex projection (no boolean/section)."""
        verts = np.asarray(tm.vertices)
        dists = verts @ normal - plane_d
        near_mask = np.abs(dists) < float(np.max(tm.extents)) * 0.05
        if np.sum(near_mask) < 3:
            extents = tm.extents
            cross_dims = [extents[i] for i in range(3) if abs(normal[i]) < 0.5]
            if len(cross_dims) >= 2:
                return cross_dims[0] * cross_dims[1] * 0.6
            return 0.0

        near_verts = verts[near_mask]
        # Project onto plane local coordinates
        up = normal / (np.linalg.norm(normal) + 1e-12)
        arb = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0.0, 1, 0])
        u = np.cross(up, arb); u /= np.linalg.norm(u) + 1e-12
        v = np.cross(up, u)
        proj_u = near_verts @ u
        proj_v = near_verts @ v
        u_range = float(proj_u.max() - proj_u.min())
        v_range = float(proj_v.max() - proj_v.min())
        return u_range * v_range * 0.65

    def _score_position(
        self, model: MeshData, normal: np.ndarray, plane_d: float,
        area: float, axis_idx: int,
    ) -> float:
        extents = model.extents
        max_cross_area = max(
            extents[0] * extents[1],
            extents[0] * extents[2],
            extents[1] * extents[2],
        )
        area_ratio = area / max_cross_area if max_cross_area > 0 else 0

        center_val = np.dot(model.center, normal)
        span = float(np.dot(model.extents, np.abs(normal)))
        centrality = 1.0 - 2.0 * abs(plane_d - center_val) / span if span > 0 else 0.5
        centrality = max(0.0, min(1.0, centrality))

        # Axis alignment bonus
        axis_bonus = 0.1 if axis_idx >= 0 else 0.0

        score = 0.5 * area_ratio + 0.35 * centrality + 0.15 * axis_bonus
        return min(1.0, max(0.0, score))

    def _get_cross_section(
        self, tm: trimesh.Trimesh, normal: np.ndarray, plane_d: float,
    ) -> trimesh.Trimesh | None:
        try:
            # Decimate before section to avoid hanging on dense meshes
            work_tm = tm
            if len(tm.faces) > 20000:
                try:
                    work_tm = tm.simplify_quadric_decimation(20000)
                except Exception:
                    pass

            section = work_tm.section(plane_origin=normal * plane_d, plane_normal=normal)
            if section is not None:
                planar, transform = section.to_2D()
                polygon = planar.polygons_full[0] if planar.polygons_full else None
                if polygon is not None:
                    # Simplify polygon to max ~200 coords to keep extrude fast
                    if hasattr(polygon, 'simplify') and len(polygon.exterior.coords) > 200:
                        polygon = polygon.simplify(0.5, preserve_topology=True)
                    mesh_2d = trimesh.creation.extrude_polygon(polygon, height=0.1)
                    mesh_2d.apply_transform(np.linalg.inv(transform))
                    return mesh_2d
        except Exception:
            logger.debug("Cross section failed, using fallback")
        return None

    def _generate_fallback_plate(
        self, model: MeshData, position: InsertPosition,
    ) -> trimesh.Trimesh:
        extents = model.extents
        normal = position.normal
        abs_normal = np.abs(normal)
        main_axis = int(np.argmax(abs_normal))
        dims = [extents[i] * 0.6 for i in range(3)]
        dims[main_axis] = 0.1

        plate = trimesh.creation.box(extents=dims)
        plate.apply_translation(position.origin)
        return plate

    def _extrude_section(
        self, section: trimesh.Trimesh, normal: np.ndarray, thickness: float,
    ) -> trimesh.Trimesh:
        offset = normal * thickness / 2.0
        v1 = section.vertices - offset
        v2 = section.vertices + offset
        combined_vertices = np.vstack([v1, v2])
        n_verts = len(section.vertices)
        f1 = section.faces
        f2 = section.faces + n_verts
        f2 = f2[:, ::-1]
        all_faces = np.vstack([f1, f2])

        edges = section.edges_unique
        side_faces = []
        for e in edges:
            a, b = e
            side_faces.append([a, b, b + n_verts])
            side_faces.append([a, b + n_verts, a + n_verts])

        if side_faces:
            all_faces = np.vstack([all_faces, np.array(side_faces)])

        result = trimesh.Trimesh(vertices=combined_vertices, faces=all_faces, process=True)
        return result

    def _apply_chamfer(self, mesh: trimesh.Trimesh, radius: float) -> trimesh.Trimesh:
        if radius <= 0:
            return mesh
        # Chamfer approximation: slight scale-smooth on boundary edges
        # Full chamfer is complex; return as-is for FDM-compatible output
        return mesh

    def _sample_surface_points(
        self, tm: trimesh.Trimesh, n_points: int,
    ) -> np.ndarray:
        points, _ = trimesh.sample.sample_surface(tm, n_points)
        return points

    # ── Anchor generation methods ────────────────────────────────────

    def _add_mesh_holes(
        self, plate: trimesh.Trimesh, n_holes: int, hole_size: float,
    ) -> tuple[trimesh.Trimesh, np.ndarray]:
        """Add through-holes for silicone penetration"""
        points = self._sample_surface_points(plate, n_holes * 3)
        selected = self._farthest_point_sampling(points, n_holes)

        result = plate
        for pt in selected:
            hole = trimesh.creation.cylinder(
                radius=hole_size / 2.0, height=self.config.thickness * 3,
                sections=8,
            )
            hole.apply_translation(pt)
            with contextlib.suppress(Exception):
                result = result.difference(hole)

        return result, selected

    def _add_bumps(
        self, plate: trimesh.Trimesh, n_bumps: int, bump_size: float,
    ) -> tuple[trimesh.Trimesh, np.ndarray]:
        """Add protruding bumps for mechanical interlock"""
        points = self._sample_surface_points(plate, n_bumps * 3)
        selected = self._farthest_point_sampling(points, n_bumps)

        result = plate
        for pt in selected:
            bump = trimesh.creation.icosphere(radius=bump_size / 2.0, subdivisions=1)
            bump.apply_translation(pt)
            with contextlib.suppress(Exception):
                result = result.union(bump)

        return result, selected

    def _add_grooves(
        self, plate: trimesh.Trimesh, n_grooves: int, groove_size: float,
    ) -> tuple[trimesh.Trimesh, np.ndarray]:
        """Add surface grooves for silicone keying"""
        points = self._sample_surface_points(plate, n_grooves * 2)
        selected = self._farthest_point_sampling(points, min(n_grooves, len(points)))

        result = plate
        for pt in selected:
            groove = trimesh.creation.box(
                extents=[groove_size * 3, groove_size * 0.5, self.config.thickness * 1.5],
            )
            groove.apply_translation(pt)
            with contextlib.suppress(Exception):
                result = result.difference(groove)

        return result, selected

    def _add_dovetail(
        self, plate: trimesh.Trimesh, n_features: int, size: float,
    ) -> tuple[trimesh.Trimesh, np.ndarray]:
        """Add dovetail-shaped anchors"""
        points = self._sample_surface_points(plate, n_features * 2)
        selected = self._farthest_point_sampling(points, min(n_features, len(points)))

        result = plate
        for pt in selected:
            trap = trimesh.creation.box(extents=[size, size * 0.6, self.config.thickness * 0.4])
            trap.apply_translation(pt + np.array([0, 0, self.config.thickness * 0.3]))
            with contextlib.suppress(Exception):
                result = result.union(trap)

        return result, selected

    def _add_diamond(
        self, plate: trimesh.Trimesh, n_features: int, size: float,
    ) -> tuple[trimesh.Trimesh, np.ndarray]:
        """Add diamond pattern texture"""
        points = self._sample_surface_points(plate, n_features * 2)
        selected = self._farthest_point_sampling(points, min(n_features, len(points)))

        result = plate
        for pt in selected:
            diamond = trimesh.creation.box(
                extents=[size * 0.5, size * 0.5, self.config.thickness * 0.3],
            )
            rot = trimesh.transformations.rotation_matrix(np.pi / 4, [0, 0, 1])
            diamond.apply_transform(rot)
            diamond.apply_translation(pt)
            with contextlib.suppress(Exception):
                result = result.union(diamond)

        return result, selected

    def _farthest_point_sampling(
        self, points: np.ndarray, n_select: int,
    ) -> np.ndarray:
        if len(points) <= n_select:
            return points

        selected_idx = [0]
        dists = np.full(len(points), np.inf)

        for _ in range(n_select - 1):
            last = points[selected_idx[-1]]
            d = np.linalg.norm(points - last, axis=1)
            dists = np.minimum(dists, d)
            next_idx = int(np.argmax(dists))
            selected_idx.append(next_idx)

        return points[selected_idx]
