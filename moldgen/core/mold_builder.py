"""模具壳体生成 — 布尔运算 + 体素回退 + 智能浇注/排气系统
=================================================

v4 核心变更:
  1. 布尔运算: manifold3d → trimesh → 体素回退三级策略
  2. 体素回退: scipy marching_cubes 保证始终生成有效空腔
  3. 浇筑口/排气口: 布尔差集切割到壳体网格上
  4. 网格修复: 每壳体生成后自动修复流形错误
  5. 分割封帽: 分型面始终封帽，确保水密壳体
"""

from __future__ import annotations

import heapq
import logging
import time
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy import ndimage

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)

MOLD_MAX_FACES = 300_000
MOLD_MIN_FACES = 12_000


# ═══════════════════════ Data Classes ═══════════════════════════════════

M_SCREW_TABLE: dict[str, dict[str, float]] = {
    "M1":   {"through": 1.2, "tap": 0.85, "head": 2.0,  "nut": 2.5,  "nut_h": 0.8},
    "M1.6": {"through": 1.8, "tap": 1.35, "head": 3.0,  "nut": 3.2,  "nut_h": 1.3},
    "M2":   {"through": 2.4, "tap": 1.7,  "head": 3.8,  "nut": 4.0,  "nut_h": 1.6},
    "M2.5": {"through": 2.9, "tap": 2.15, "head": 4.5,  "nut": 5.0,  "nut_h": 2.0},
    "M3":   {"through": 3.4, "tap": 2.55, "head": 5.5,  "nut": 5.5,  "nut_h": 2.4},
    "M4":   {"through": 4.5, "tap": 3.4,  "head": 7.0,  "nut": 7.0,  "nut_h": 3.2},
    "M5":   {"through": 5.5, "tap": 4.25, "head": 8.5,  "nut": 8.0,  "nut_h": 4.0},
    "M6":   {"through": 6.6, "tap": 5.1,  "head": 10.0, "nut": 10.0, "nut_h": 5.0},
    "M8":   {"through": 9.0, "tap": 6.85, "head": 13.0, "nut": 13.0, "nut_h": 6.5},
}


@dataclass
class MoldConfig:
    wall_thickness: float = 4.0
    clearance: float = 0.3
    shell_type: str = "box"       # "box" | "conformal"
    margin: float = 10.0
    fillet_radius: float = 1.0
    # Parting style: "flat" | "dovetail" | "zigzag" | "step" | "tongue_groove"
    parting_style: str = "flat"
    # Adaptive parting surface type (used when splitting the mold)
    parting_surface_type: str = "flat"  # "flat" | "heightfield" | "projected" | "auto"
    parting_depth: float = 3.0       # depth of interlock features (mm)
    parting_pitch: float = 10.0      # spacing between interlock features (mm)
    # Screw fastening system (pocket + through-bolt at corners)
    add_screw_holes: bool = False
    screw_size: str = "M4"           # M1 / M1.6 / M2 / M2.5 / M3 / M4 / M5 / M6 / M8
    n_screws: int = 4                # number of screw positions
    screw_counterbore: bool = True   # add counterbore recess for bolt head
    screw_tab_thickness: float = 5.0 # tab thickness remaining near parting plane (mm)
    # Clamp bracket generation
    add_clamp_bracket: bool = False
    clamp_width: float = 15.0        # bracket width (mm)
    clamp_thickness: float = 3.0     # bracket wall thickness (mm)
    clamp_screw_size: str = "M3"     # screw size for clamp bolts
    n_clamp_screws: int = 4
    # Alignment
    add_alignment_pins: bool = True
    pin_diameter: float = 4.0
    pin_height: float = 8.0
    pin_tolerance: float = 0.2
    n_pins: int = 4
    # FDM constraints
    min_wall_thickness: float = 1.2
    max_overhang_angle: float = 45.0
    # Pour
    add_pour_hole: bool = True
    pour_hole_diameter: float = 15.0
    pour_funnel_angle: float = 30.0   # funnel taper degrees
    # Vent
    add_vent_holes: bool = True
    vent_hole_diameter: float = 3.0
    n_vent_holes: int = 4
    # Draft
    draft_angle_check: bool = True
    min_draft_angle: float = 1.0      # degrees


@dataclass
class MoldShell:
    shell_id: int
    mesh: MeshData
    direction: np.ndarray
    volume: float = 0.0
    surface_area: float = 0.0
    is_printable: bool = True
    min_draft_angle: float = 0.0

    def to_dict(self) -> dict:
        return {
            "shell_id": self.shell_id,
            "direction": self.direction.tolist(),
            "volume": round(self.volume, 2),
            "surface_area": round(self.surface_area, 2),
            "face_count": self.mesh.face_count,
            "is_printable": self.is_printable,
            "min_draft_angle": round(self.min_draft_angle, 1),
        }


@dataclass
class AlignmentFeature:
    position: np.ndarray
    feature_type: str       # "pin" | "hole"
    diameter: float
    height: float
    mesh: MeshData | None = None

    def to_dict(self) -> dict:
        return {
            "position": self.position.tolist(),
            "type": self.feature_type,
            "diameter": round(self.diameter, 2),
            "height": round(self.height, 2),
        }


@dataclass
class HoleFeature:
    """Describes a pour-hole or vent-hole with position + geometry."""
    position: np.ndarray
    diameter: float
    hole_type: str           # "pour" | "vent"
    score: float = 0.0
    mesh: MeshData | None = None

    def to_dict(self) -> dict:
        return {
            "position": self.position.tolist(),
            "diameter": round(self.diameter, 2),
            "type": self.hole_type,
            "score": round(self.score, 4),
        }


@dataclass
class FlangeFeature:
    """Describes a mounting flange tab with screw hole."""
    position: np.ndarray
    normal: np.ndarray
    width: float
    thickness: float
    screw_diameter: float
    mesh: MeshData | None = None

    def to_dict(self) -> dict:
        return {
            "position": self.position.tolist(),
            "normal": self.normal.tolist(),
            "width": round(self.width, 2),
            "thickness": round(self.thickness, 2),
            "screw_diameter": round(self.screw_diameter, 2),
        }


@dataclass
class ScrewHoleFeature:
    """Through-bolt hole for mold clamping."""
    position: np.ndarray
    screw_size: str          # M1..M8
    through_diameter: float
    counterbore_diameter: float
    counterbore_depth: float

    def to_dict(self) -> dict:
        return {
            "position": self.position.tolist(),
            "screw_size": self.screw_size,
            "through_diameter": round(self.through_diameter, 2),
            "counterbore_diameter": round(self.counterbore_diameter, 2),
            "counterbore_depth": round(self.counterbore_depth, 2),
        }


@dataclass
class ClampBracket:
    """External clamp bracket that wraps around the parting line."""
    mesh: MeshData
    screw_positions: list[np.ndarray] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "face_count": self.mesh.face_count,
            "screw_positions": [p.tolist() for p in self.screw_positions],
        }


@dataclass
class MoldResult:
    shells: list[MoldShell]
    cavity_volume: float = 0.0
    alignment_features: list[AlignmentFeature] = field(default_factory=list)
    pour_hole_position: np.ndarray | None = None
    pour_hole: HoleFeature | None = None
    vent_positions: list[np.ndarray] = field(default_factory=list)
    vent_holes: list[HoleFeature] = field(default_factory=list)
    screw_holes: list[ScrewHoleFeature] = field(default_factory=list)
    clamp_brackets: list[ClampBracket] = field(default_factory=list)
    parting_style: str = "flat"
    parting_surface_type: str = "flat"
    undercut_severity: str = "none"

    def to_dict(self) -> dict:
        return {
            "n_shells": len(self.shells),
            "shells": [s.to_dict() for s in self.shells],
            "cavity_volume": round(self.cavity_volume, 2),
            "parting_style": self.parting_style,
            "parting_surface_type": self.parting_surface_type,
            "undercut_severity": self.undercut_severity,
            "alignment_features": [
                f.to_dict() for f in self.alignment_features
            ],
            "screw_holes": [s.to_dict() for s in self.screw_holes],
            "clamp_brackets": [c.to_dict() for c in self.clamp_brackets],
            "pour_hole": (
                self.pour_hole.to_dict()
                if self.pour_hole is not None
                else (
                    self.pour_hole_position.tolist()
                    if self.pour_hole_position is not None
                    else None
                )
            ),
            "vent_holes": (
                [v.to_dict() for v in self.vent_holes]
                if self.vent_holes
                else [v.tolist() for v in self.vent_positions]
            ),
        }


# ═══════════════════════ Helpers ════════════════════════════════════════

def _ensure_min_faces(
    tm: trimesh.Trimesh, min_faces: int = 12_000,
) -> trimesh.Trimesh:
    """Subdivide a mesh until it has at least *min_faces* faces.

    Low-poly models produce low-resolution mold shells. Subdivision
    increases surface resolution so that mold walls, cavities, and
    parting features have enough geometry for clean boolean operations.
    """
    iters = 0
    while len(tm.faces) < min_faces and iters < 5:
        try:
            new_v, new_f = trimesh.remesh.subdivide(tm.vertices, tm.faces)
            tm = trimesh.Trimesh(vertices=new_v, faces=new_f, process=True)
            iters += 1
        except Exception:
            break
    if iters > 0:
        logger.info(
            "Subdivided model %dx -> %d faces (target >= %d)",
            iters, len(tm.faces), min_faces,
        )
    return tm


def _auto_rescale_to_mm(
    tm: trimesh.Trimesh, unit_hint: str = "mm",
) -> tuple[trimesh.Trimesh, float]:
    """Detect if a mesh is in metres/cm and rescale to millimetres.

    Many 3D-scanned models use metres (extents < 2 on a face model)
    or centimetres (extents < 20). Mold parameters assume mm, so we
    must auto-scale.  Returns *(rescaled_mesh, scale_factor)*.
    A factor of 1.0 means no scaling was applied.
    """
    max_ext = float(np.max(tm.extents))
    if max_ext < 1e-12:
        return tm, 1.0

    hint = unit_hint.lower().strip()
    if hint in ("m", "meter", "meters"):
        scale = 1000.0
    elif hint in ("cm", "centimeter", "centimeters"):
        scale = 10.0
    elif hint in ("in", "inch", "inches"):
        scale = 25.4
    elif max_ext < 2.0:
        scale = 1000.0
        logger.info(
            "Model max extent %.4f << typical mm range; assuming metres → mm (×1000)",
            max_ext,
        )
    elif max_ext < 25.0:
        scale = 10.0
        logger.info(
            "Model max extent %.2f < 25; assuming cm → mm (×10)", max_ext,
        )
    else:
        return tm, 1.0

    scaled = tm.copy()
    scaled.vertices = tm.vertices * scale
    logger.info(
        "Rescaled model ×%.0f: extents %s → %s",
        scale,
        np.array2string(tm.extents, precision=2),
        np.array2string(scaled.extents, precision=1),
    )
    return scaled, scale


def _laplacian_smooth_vertex_normals(tm: trimesh.Trimesh) -> np.ndarray:
    """Blend each vertex normal with its neighbors (one iteration).

    Reduces divergent normals at high-curvature tips so normal-offset
    shells (cavity clearance, conformal outer wall) stay closed.
    """
    normals = np.asarray(tm.vertex_normals, dtype=np.float64)
    smooth_n = normals.copy()
    try:
        adj_list = tm.vertex_neighbors
        for vi in range(len(smooth_n)):
            nbrs = adj_list[vi]
            if nbrs:
                avg = np.mean(normals[nbrs], axis=0)
                smooth_n[vi] = 0.5 * normals[vi] + 0.5 * avg
        row_n = np.linalg.norm(smooth_n, axis=1, keepdims=True)
        safe_n = np.where(row_n > 1e-8, row_n, 1.0)
        smooth_n = np.where(row_n > 1e-8, smooth_n / safe_n, normals)
    except Exception:
        smooth_n = normals
    return smooth_n


def _edges_to_closed_loops(edges: np.ndarray) -> list[np.ndarray]:
    """Extract closed vertex loops from an undirected 2-manifold boundary edge list."""
    if edges.size == 0:
        return []
    e = np.asarray(edges, dtype=np.int64)
    from collections import defaultdict

    adj: dict[int, set[int]] = defaultdict(set)
    undirected: set[tuple[int, int]] = set()
    for a, b in e:
        a, b = int(a), int(b)
        if a == b:
            continue
        adj[a].add(b)
        adj[b].add(a)
        undirected.add((a, b) if a < b else (b, a))

    loops: list[np.ndarray] = []
    while undirected:
        v0, v1 = undirected.pop()
        loop: list[int] = [v0, v1]
        prev, curr = v0, v1
        while True:
            nbrs = sorted(x for x in adj[curr] if x != prev)
            if not nbrs:
                break
            others = [x for x in nbrs if x != v0]
            nxt = others[0] if others else v0
            ek = (curr, nxt) if curr < nxt else (nxt, curr)
            if nxt == v0:
                if ek in undirected:
                    undirected.discard(ek)
                break
            if ek in undirected:
                undirected.discard(ek)
            loop.append(int(nxt))
            prev, curr = curr, int(nxt)
            if len(loop) > e.shape[0] + 20:
                break
        if len(loop) >= 3:
            loops.append(np.array(loop, dtype=np.int64))
    return loops


def _signed_shoelace_2d(poly_xy: np.ndarray) -> float:
    """Signed area; positive ⇒ CCW in an (x,y) right-handed frame."""
    if poly_xy.ndim != 2 or len(poly_xy) < 3:
        return 0.0
    x = poly_xy[:, 0].astype(np.float64, copy=False)
    y = poly_xy[:, 1].astype(np.float64, copy=False)
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _point_in_polygon_2d(pt: np.ndarray, poly_xy: np.ndarray) -> bool:
    """Ray cast; *poly_xy* is an open ring (first vertex not repeated at end)."""
    if poly_xy.ndim != 2 or len(poly_xy) < 3:
        return False
    x, y = float(pt[0]), float(pt[1])
    inside = False
    n = len(poly_xy)
    j = n - 1
    for i in range(n):
        yi = float(poly_xy[i, 1])
        yj = float(poly_xy[j, 1])
        xi = float(poly_xy[i, 0])
        xj = float(poly_xy[j, 0])
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi:
            inside = not inside
        j = i
    return inside


def _orthonormal_basis_perpendicular(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(d, dtype=np.float64).reshape(3)
    d = d / (np.linalg.norm(d) + 1e-12)
    a = (
        np.array([1.0, 0.0, 0.0])
        if abs(float(d[0])) < 0.9
        else np.array([0.0, 1.0, 0.0])
    )
    u = np.cross(d, a)
    u = u / (np.linalg.norm(u) + 1e-12)
    v = np.cross(d, u)
    return u, v


def _project_to_plane_2d(
    pts: np.ndarray,
    origin: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
) -> np.ndarray:
    q = pts - origin.reshape(1, 3)
    return np.column_stack([q @ u, q @ v])


def _nest_planar_loops_for_triangulation(
    prepared: list[tuple[np.ndarray, np.ndarray]],
    *,
    area_eps: float,
) -> list[tuple[np.ndarray, list[np.ndarray]]]:
    """Pick outer boundary + hole loops per connected nesting (single hole level).

    Each item is ``(vertex_indices, xy_projected)`` for one closed loop.
    Returns ``[(outer_idx, [hole_idx, ...]), ...]`` (one component per root loop).
    """
    if not prepared:
        return []
    n = len(prepared)
    centroids = np.array([xy.mean(axis=0) for _, xy in prepared], dtype=np.float64)
    abs_areas = np.array(
        [abs(_signed_shoelace_2d(xy)) for _, xy in prepared], dtype=np.float64,
    )
    parent = np.full(n, -1, dtype=np.int32)
    for i in range(n):
        ci = centroids[i]
        best_j = -1
        best_area = np.inf
        for j in range(n):
            if j == i:
                continue
            if abs_areas[j] <= abs_areas[i] + area_eps:
                continue
            if not _point_in_polygon_2d(ci, prepared[j][1]):
                continue
            if abs_areas[j] < best_area:
                best_area = abs_areas[j]
                best_j = j
        parent[i] = int(best_j)

    roots = [i for i in range(n) if parent[i] == -1]
    out: list[tuple[np.ndarray, list[np.ndarray]]] = []
    for r in roots:
        holes = [prepared[i][0] for i in range(n) if parent[i] == r]
        out.append((prepared[r][0], holes))
    return out


def _rings_xy_for_manifold(
    outer_xy: np.ndarray, holes_xy: list[np.ndarray],
) -> list[np.ndarray]:
    """Exterior CCW, holes CW (manifold3d ``triangulate`` convention)."""
    rings: list[np.ndarray] = []
    o = np.asarray(outer_xy, dtype=np.float64, copy=True)
    if _signed_shoelace_2d(o) < 0:
        o = o[::-1].copy()
    rings.append(o)
    for h in holes_xy:
        hh = np.asarray(h, dtype=np.float64, copy=True)
        if _signed_shoelace_2d(hh) > 0:
            hh = hh[::-1].copy()
        rings.append(hh)
    return rings


def _triangulate_nested_planar_rings(
    outer_idx: np.ndarray,
    hole_indices: list[np.ndarray],
    verts: np.ndarray,
    origin_plane: np.ndarray,
    u_ax: np.ndarray,
    v_ax: np.ndarray,
) -> np.ndarray | None:
    """Return (m,3) int face indices into *verts* using stacked loop vertices."""
    import manifold3d

    outer_xy = _project_to_plane_2d(verts[outer_idx], origin_plane, u_ax, v_ax)
    holes_xy = [
        _project_to_plane_2d(verts[hi], origin_plane, u_ax, v_ax)
        for hi in hole_indices
    ]
    rings_xy = _rings_xy_for_manifold(outer_xy, holes_xy)
    try:
        loc = manifold3d.triangulate(rings_xy).astype(np.int64)
    except Exception:
        return None
    if loc.size == 0:
        return None
    idx_parts = [outer_idx] + [hi for hi in hole_indices]
    idx_map = np.concatenate(idx_parts)
    return idx_map[loc]


def _seal_parting_plane_gaps(
    tm: trimesh.Trimesh,
    plane_origin: np.ndarray,
    slice_plane_normal: np.ndarray,
    *,
    z_tol: float | None = None,
) -> trimesh.Trimesh:
    """Close open boundary edges with planar caps (parting face, top rim, etc.).

    Previous logic only considered edges whose endpoints lay near a single
    parting plane in a fixed frame. Real mold halves still have **other** open
    rims (e.g. the annular “lid” between the outer box and the cavity). Worse,
    merging **all** coplanar boundary edges into one walk can zig-zag between
    two different heights, producing a non-planar bogus loop. Slicers then
    show a dark ring between the outer rim and the inner disc.

    Fix:
      1. Take **all** one-sided boundary edges.
      2. Cluster them by average height along **slice_plane_normal** (the shell
         opening / parting axis stored in ``MoldShell.direction``).
      3. Within each cluster, extract closed loops, drop degenerate (near-zero
         area) rings, **nest** outer vs holes, and triangulate with
         ``manifold3d.triangulate([outer, *holes])`` — one annulus per component.
    """
    _ = z_tol  # retained for API compatibility; height bins replace plane z filter

    if tm is None or len(tm.faces) < 4:
        return tm

    normal = np.asarray(slice_plane_normal, dtype=np.float64)
    nrm = float(np.linalg.norm(normal))
    if nrm < 1e-12:
        return tm
    d = normal / nrm
    origin = np.asarray(plane_origin, dtype=np.float64).reshape(3)

    verts = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.reshape(np.asarray(tm.faces, dtype=np.int64), (-1, 3))
    if faces.size and int(faces.max()) >= len(verts):
        logger.warning("Seal: face indices out of range; skipping seal")
        return tm

    ext_float = float(np.max(np.ptp(verts, axis=0))) if len(verts) else 1.0
    area_eps = max(1e-9, 1e-12 * ext_float * ext_float)
    min_loop_area = max(0.08, 1e-10 * ext_float * ext_float)
    # Wide height bins so every edge of one planar opening groups together
    # (narrow bins split a single loop across buckets → incomplete caps).
    bin_w = max(1.25, 0.02 * ext_float)

    fe = trimesh.geometry.faces_to_edges(faces)
    fe = np.sort(np.asarray(fe, dtype=np.int64), axis=1)
    edge_count = Counter(map(tuple, fe))
    bedges = np.array([list(k) for k, v in edge_count.items() if v == 1], dtype=np.int64)
    if len(bedges) == 0:
        return tm
    h_v = (verts - origin) @ d
    h_e = (h_v[bedges[:, 0]] + h_v[bedges[:, 1]]) * 0.5
    bins = np.round(h_e / bin_w).astype(np.int64)

    u_ax, v_ax = _orthonormal_basis_perpendicular(d)

    new_faces: list[np.ndarray] = [faces]
    max_holes = 48

    for b in np.unique(bins):
        sub = bedges[bins == b]
        if len(sub) < 3:
            continue
        h0 = float(np.mean(h_e[bins == b]))
        origin_plane = origin + d * h0

        loops_v = _edges_to_closed_loops(sub)
        prepared: list[tuple[np.ndarray, np.ndarray]] = []
        for loop in loops_v:
            if len(loop) < 3:
                continue
            xy = _project_to_plane_2d(verts[loop], origin_plane, u_ax, v_ax)
            if abs(_signed_shoelace_2d(xy)) < min_loop_area:
                continue
            prepared.append((loop, xy))

        if not prepared:
            continue

        for outer_idx, hole_list in _nest_planar_loops_for_triangulation(
            prepared, area_eps=area_eps,
        ):
            if len(hole_list) > max_holes:
                logger.warning(
                    "Skipping planar seal with %d holes (max %d)",
                    len(hole_list), max_holes,
                )
                continue
            holes_idx = [np.asarray(h, dtype=np.int64) for h in hole_list]
            nf = _triangulate_nested_planar_rings(
                outer_idx, holes_idx, verts, origin_plane, u_ax, v_ax,
            )
            if nf is None:
                continue
            nf_ok = (nf[:, 1:] != nf[:, :1]).all(axis=1) & (nf[:, 1] != nf[:, 2])
            new_faces.append(nf.astype(np.int64)[nf_ok])

    if len(new_faces) <= 1:
        return tm

    all_f = np.vstack(new_faces)
    out = trimesh.Trimesh(vertices=verts, faces=all_f, process=False)
    try:
        out.remove_duplicate_faces()
    except Exception:
        pass
    try:
        _compact_mesh_vertex_indices(out)
    except Exception:
        pass
    return out


def _compact_mesh_vertex_indices(tm: trimesh.Trimesh) -> None:
    """Remap ``faces`` to a dense 0…N-1 range and drop unreferenced vertices.

    Some repair steps leave a compact *set* of vertex IDs in ``faces`` while
    ``vertices`` still spans 0…K-1 (K>N). ``trimesh.remove_unreferenced_vertices``
    may fail to rewrite ``faces`` in isolated cases, leaving stale indices.
    """
    if tm is None or len(tm.faces) == 0:
        return
    faces = np.asarray(tm.faces, dtype=np.int64)
    verts = np.asarray(tm.vertices, dtype=np.float64)
    ok = (faces >= 0).all(axis=1) & (faces < len(verts)).all(axis=1)
    if not np.all(ok):
        faces = faces[ok]
        tm.faces = faces
        if len(faces) == 0:
            return
    used = np.unique(faces.ravel())
    if used.size == 0:
        return
    if len(used) == len(verts) and int(used[0]) == 0 and int(used[-1]) == len(verts) - 1:
        return
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    tm.vertices = verts[used]
    tm.faces = remap[faces]
    try:
        tm._cache.clear()
    except Exception:
        pass


def _boundary_undirected_edge_count(tm: trimesh.Trimesh) -> int:
    if tm is None or len(tm.faces) == 0:
        return 0
    fe = trimesh.geometry.faces_to_edges(np.asarray(tm.faces, dtype=np.int64))
    fe = np.sort(fe, axis=1)
    return sum(1 for _, v in Counter(map(tuple, fe)).items() if v == 1)


def _dedupe_opposite_or_duplicate_tris(tm: trimesh.Trimesh) -> None:
    """Remove duplicate triangles sharing the same 3 vertices (any winding).

    Slice caps plus our planar seal can introduce back-to-back copies that
    confuse slicers.  If removing extras would *increase* open boundary length,
    the edit is skipped (some coincident triangles are structurally required).
    """
    if tm is None or len(tm.faces) < 2:
        return
    from collections import defaultdict

    f = np.asarray(tm.faces, dtype=np.int64)
    b0 = _boundary_undirected_edge_count(tm)
    groups: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for i in range(len(f)):
        tri = f[i]
        if len(set(int(x) for x in tri)) < 3:
            continue
        key = tuple(sorted(int(x) for x in tri))
        groups[key].append(i)
    drop: set[int] = set()
    for idxs in groups.values():
        if len(idxs) <= 1:
            continue
        drop.update(idxs[1:])
    if not drop:
        return
    keep = np.array([i for i in range(len(f)) if i not in drop], dtype=np.int64)
    trial = f[keep]
    tm.faces = trial
    try:
        tm._cache.clear()
    except Exception:
        pass
    if _boundary_undirected_edge_count(tm) > b0:
        tm.faces = f
        try:
            tm._cache.clear()
        except Exception:
            pass


def _repair_mesh(tm: trimesh.Trimesh) -> trimesh.Trimesh:
    """Aggressive mesh repair: remove degenerates, fix normals, fill holes."""
    try:
        tm.update_faces(tm.nondegenerate_faces())
    except (AttributeError, Exception):
        pass
    try:
        tm.remove_duplicate_faces()
    except Exception:
        pass
    for fn in (trimesh.repair.fill_holes,
               trimesh.repair.fix_normals,
               trimesh.repair.fix_winding):
        try:
            fn(tm)
        except Exception:
            pass
    try:
        trimesh.repair.fix_inversion(tm)
    except Exception:
        pass
    try:
        _dedupe_opposite_or_duplicate_tris(tm)
    except Exception:
        pass
    try:
        _compact_mesh_vertex_indices(tm)
    except Exception:
        pass
    return tm


def _extract_submesh(
    mesh: trimesh.Trimesh, face_mask: np.ndarray,
) -> trimesh.Trimesh:
    idx = np.where(face_mask)[0]
    if len(idx) == 0:
        return trimesh.Trimesh()
    sub_f = mesh.faces[idx]
    uv = np.unique(sub_f.ravel())
    remap = np.full(len(mesh.vertices), -1, dtype=int)
    remap[uv] = np.arange(len(uv))
    return trimesh.Trimesh(
        vertices=mesh.vertices[uv], faces=remap[sub_f], process=True,
    )


def _shoelace_area_2d(poly_xy: np.ndarray) -> float:
    """Signed absolute area of a simple polygon in 2D (shoelace)."""
    if poly_xy.ndim != 2 or len(poly_xy) < 3:
        return 0.0
    x = poly_xy[:, 0].astype(np.float64, copy=False)
    y = poly_xy[:, 1].astype(np.float64, copy=False)
    if float(np.linalg.norm(poly_xy[0] - poly_xy[-1])) > 1e-12:
        x = np.concatenate([x, x[:1]])
        y = np.concatenate([y, y[:1]])
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _path_perimeter_2d(arr: np.ndarray) -> float:
    if arr.ndim != 2 or len(arr) < 2:
        return 0.0
    loop = np.vstack([arr, arr[:1]])
    return float(np.linalg.norm(np.diff(loop, axis=0), axis=1).sum())


def _shell_is_conformal(shell_type: str | None) -> bool:
    return (shell_type or "box").strip().lower() == "conformal"


def _slice_keep_positive_halfspace(
    mesh: trimesh.Trimesh,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
) -> trimesh.Trimesh | None:
    """Keep the portion on the positive side of a plane (same contract as trimesh.slice_plane).

    ``Trimesh.slice_plane`` imports ``path.polygons`` which **requires shapely**.  Without it,
    every call raises and MoldGen fell back to ``_extract_submesh`` (triangle centers),
    which drops faces that straddle the cut — **square shells lose side walls** and slicers
    only see a flat cap plus cavity.

    ``trimesh.intersections.slice_faces_plane`` is numpy-only for the cut; combine with
    ``_seal_parting_plane_gaps`` for caps.
    """
    if mesh is None or len(mesh.faces) < 1:
        return None
    try:
        from trimesh.intersections import slice_faces_plane

        po = np.asarray(plane_origin, dtype=np.float64).reshape(3)
        pn = np.asarray(plane_normal, dtype=np.float64).reshape(3)
        nrm = float(np.linalg.norm(pn))
        if nrm < 1e-12:
            return None
        pn = pn / nrm
        v, f, _ = slice_faces_plane(
            np.asarray(mesh.vertices, dtype=np.float64),
            np.asarray(mesh.faces, dtype=np.int64),
            pn,
            po,
        )
        if f is None or len(f) < 4:
            return None
        return trimesh.Trimesh(vertices=v, faces=f, process=False)
    except Exception:
        return None


def _safe_slice(
    mesh: trimesh.Trimesh, origin: np.ndarray, normal: np.ndarray,
    *, cap: bool = True,
) -> trimesh.Trimesh | None:
    """Slice mesh at plane, keeping the positive half-space.

    Args:
        cap: If True, cap the cut face. Set False for mold wall-volume
             slicing where the cavity cross-section must stay open.
    """
    cap_order = (True, False) if cap else (False, True)
    for c in cap_order:
        try:
            r = mesh.slice_plane(origin, normal, cap=c)
            if r is not None and len(r.faces) >= 4:
                return r
        except Exception:
            continue
    half = _slice_keep_positive_halfspace(mesh, origin, normal)
    if half is not None and len(half.faces) >= 4:
        return half
    dots = (mesh.triangles_center - origin) @ normal
    sub = _extract_submesh(mesh, dots >= 0)
    return sub if len(sub.faces) > 0 else None


def _build_face_adjacency_dict(tm: trimesh.Trimesh) -> dict[int, list[int]]:
    """Build {face_id: [neighbor_ids]} from trimesh face_adjacency."""
    n = len(tm.faces)
    adj: dict[int, list[int]] = {i: [] for i in range(n)}
    try:
        pairs = tm.face_adjacency
        for f0, f1 in pairs:
            adj[f0].append(f1)
            adj[f1].append(f0)
    except Exception:
        pass
    return adj


def _make_oriented_box(
    center: np.ndarray,
    u_ax: np.ndarray, v_ax: np.ndarray, w_ax: np.ndarray,
    size_u: float, size_v: float, size_w: float,
) -> trimesh.Trimesh:
    """Build a watertight box mesh directly in world coordinates.

    Avoids ``trimesh.creation.box() + apply_transform()`` which can
    produce geometry that boolean engines (manifold3d) reject silently.
    The 8 vertices are computed explicitly and faces use verified CCW
    winding for outward normals.
    """
    hu, hv, hw = size_u / 2.0, size_v / 2.0, size_w / 2.0
    verts = np.array([
        center - hu * u_ax - hv * v_ax - hw * w_ax,   # 0: ---
        center + hu * u_ax - hv * v_ax - hw * w_ax,   # 1: +--
        center + hu * u_ax + hv * v_ax - hw * w_ax,   # 2: ++-
        center - hu * u_ax + hv * v_ax - hw * w_ax,   # 3: -+-
        center - hu * u_ax - hv * v_ax + hw * w_ax,   # 4: --+
        center + hu * u_ax - hv * v_ax + hw * w_ax,   # 5: +-+
        center + hu * u_ax + hv * v_ax + hw * w_ax,   # 6: +++
        center - hu * u_ax + hv * v_ax + hw * w_ax,   # 7: -++
    ], dtype=np.float64)
    faces = np.array([
        [0, 3, 2], [0, 2, 1],   # −w face
        [4, 5, 6], [4, 6, 7],   # +w face
        [0, 1, 5], [0, 5, 4],   # −v face
        [2, 3, 7], [2, 7, 6],   # +v face
        [0, 4, 7], [0, 7, 3],   # −u face
        [1, 2, 6], [1, 6, 5],   # +u face
    ], dtype=np.int64)
    box = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    trimesh.repair.fix_normals(box)
    return box


def _make_cylinder(
    position: np.ndarray, direction: np.ndarray,
    radius: float, height: float, sections: int = 24,
) -> trimesh.Trimesh:
    """Create a cylinder mesh at *position*, oriented along *direction*."""
    cyl = trimesh.creation.cylinder(
        radius=radius, height=height, sections=sections,
    )
    # Align cylinder Z axis with direction
    z = np.array([0, 0, 1.0])
    d = direction / (np.linalg.norm(direction) + 1e-12)
    v = np.cross(z, d)
    s = np.linalg.norm(v)
    c = float(np.dot(z, d))
    if s > 1e-8:
        vx = np.array([
            [0, -v[2], v[1]],
            [v[2], 0, -v[0]],
            [-v[1], v[0], 0],
        ])
        R = np.eye(3) + vx + vx @ vx * (1 - c) / (s * s)
    else:
        R = np.eye(3) if c > 0 else np.diag([1, -1, -1.0])

    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = position
    cyl.apply_transform(T)
    return cyl


# ═══════════════════════ Main Builder ══════════════════════════════════

class MoldBuilder:
    """模具壳体生成器 v3"""

    def __init__(self, config: MoldConfig | None = None):
        self.config = config or MoldConfig()

    # ───────────── public: 2-part mold ─────────────────────────

    def build_two_part_mold(
        self, model: MeshData, direction: np.ndarray,
    ) -> MoldResult:
        t0 = time.perf_counter()
        direction = np.asarray(direction, dtype=np.float64)
        direction = direction / np.linalg.norm(direction)
        logger.info(
            "Building 2-part mold [%.2f,%.2f,%.2f] (%d faces)",
            *direction, model.face_count,
        )

        from moldgen.core.orientation import _auto_decimate
        build_mesh, decimated = _auto_decimate(model, MOLD_MAX_FACES)
        if decimated:
            logger.info(
                "Decimated %d -> %d faces",
                model.face_count, build_mesh.face_count,
            )

        tm_model = build_mesh.to_trimesh()

        tm_model, self._scale_factor = _auto_rescale_to_mm(
            tm_model, model.unit,
        )

        tm_model = _repair_mesh(tm_model)
        tm_model = _ensure_min_faces(tm_model, min_faces=MOLD_MIN_FACES)

        logger.info(
            "Repaired: %d faces, watertight=%s",
            len(tm_model.faces), tm_model.is_watertight,
        )

        center = np.asarray(tm_model.centroid, dtype=np.float64)

        # ── Undercut analysis (lightweight, runs during mold generation) ──
        from moldgen.core.parting import UndercutAnalyzer
        uc_info = UndercutAnalyzer().analyze(tm_model, direction, threshold=1.0)
        logger.info(
            "Mold undercut: %d/%d faces (%.1f%%), severity=%s",
            uc_info.n_undercut_faces, uc_info.total_faces,
            uc_info.undercut_ratio * 100, uc_info.severity,
        )
        if uc_info.severity == "severe":
            logger.warning(
                "Severe undercuts detected (%.1f%%, max_depth=%.1fmm). "
                "Consider using multi-piece mold or side-pulls.",
                uc_info.undercut_ratio * 100, uc_info.max_depth,
            )

        cavity = self._create_cavity(tm_model)
        outer = self._create_outer_shell(cavity)

        # ── Try non-planar split if adaptive surface type requested ──
        shells = None
        if self.config.parting_surface_type in ("heightfield", "projected", "auto"):
            shells = self._build_shells_adaptive_surface(
                tm_model, outer, cavity, center, direction,
            )

        # ── Strategy 1: Slice-Then-Subtract (primary / flat fallback) ─
        if not shells or len(shells) < 2:
            shells = self._build_shells_slice_then_subtract(
                outer, cavity, center, direction,
            )

        # ── Strategy 2: Voxel construction ─────────────────────────
        if not shells or len(shells) < 2:
            logger.info("Slice-then-subtract failed, trying voxel")
            shells = self._build_shells_voxel(tm_model, center, direction)

        # ── Strategy 3: Direct half-box fallback ───────────────────
        if not shells or len(shells) < 2:
            logger.warning("Voxel failed, using direct half-box fallback")
            shells = self._build_direct_shells(cavity, center, direction)

        # ── Repair shells (do NOT seal parting face — cavity must stay open) ──
        for sh in shells:
            tm_sh = sh.mesh.to_trimesh()
            tm_sh = _repair_mesh(tm_sh)
            sh.mesh = MeshData.from_trimesh(tm_sh)

        # ── Apply parting interlock profile if non-flat ──
        if self.config.parting_style != "flat" and len(shells) >= 2:
            shells = self._apply_parting_interlock_to_shells(
                shells, center, direction,
            )

        # ── Draft angle check per shell ──
        if self.config.draft_angle_check:
            for sh in shells:
                sh.min_draft_angle = self._check_draft_angle(
                    sh.mesh, sh.direction,
                )
                sh.is_printable = (
                    sh.min_draft_angle >= self.config.min_draft_angle
                )

        # ── Assembly features ──
        cavity_vol = float(cavity.volume) if cavity.is_watertight else 0.0
        alignment = (
            self._generate_alignment_features(tm_model, direction, center)
            if self.config.add_alignment_pins else []
        )

        pour_hole = None
        if self.config.add_pour_hole:
            pour_hole = self._compute_pour_gate(tm_model, cavity, direction)

        vent_holes: list[HoleFeature] = []
        if self.config.add_vent_holes:
            pour_pos = pour_hole.position if pour_hole else None
            vent_holes = self._compute_vent_holes(
                tm_model, direction, pour_pos,
            )

        # ── Cut holes into shells ──
        shells = self._cut_holes_in_shells(
            shells, pour_hole, vent_holes, direction,
        )

        # ── Through-bolt screw holes (pocket + tab design) ──
        screw_holes: list[ScrewHoleFeature] = []
        if self.config.add_screw_holes:
            shells, screw_holes = self._generate_screw_holes(
                shells, tm_model, direction, center,
            )
            logger.info("Added %d screw holes", len(screw_holes))

        # ── Clamp brackets ──
        clamp_brackets: list[ClampBracket] = []
        if self.config.add_clamp_bracket:
            clamp_brackets = self._generate_clamp_brackets(
                shells, tm_model, direction, center,
            )
            logger.info("Generated %d clamp brackets", len(clamp_brackets))

        elapsed = time.perf_counter() - t0
        logger.info(
            "Mold complete: %d shells, cavity=%.0f mm3, "
            "pour=%s, vents=%d, pins=%d, screws=%d, clamps=%d, "
            "style=%s, %.2fs",
            len(shells), cavity_vol,
            "yes" if pour_hole else "no",
            len(vent_holes),
            len([a for a in alignment if a.feature_type == "pin"]),
            len(screw_holes), len(clamp_brackets),
            self.config.parting_style,
            elapsed,
        )

        return MoldResult(
            shells=shells,
            cavity_volume=cavity_vol,
            alignment_features=alignment,
            pour_hole_position=(
                pour_hole.position if pour_hole else None
            ),
            pour_hole=pour_hole,
            vent_positions=[v.position for v in vent_holes],
            vent_holes=vent_holes,
            screw_holes=screw_holes,
            clamp_brackets=clamp_brackets,
            parting_style=self.config.parting_style,
            parting_surface_type=self.config.parting_surface_type,
            undercut_severity=uc_info.severity,
        )

    # ───────────── public: multi-part mold ─────────────────────

    def build_multi_part_mold(
        self, model: MeshData, directions: list[np.ndarray],
    ) -> MoldResult:
        if len(directions) < 2:
            raise ValueError("Multi-part mold requires at least 2 directions")

        logger.info(
            "Building multi-part mold with %d directions", len(directions),
        )
        t0 = time.perf_counter()

        from moldgen.core.orientation import _auto_decimate
        build_mesh, _ = _auto_decimate(model, MOLD_MAX_FACES)
        tm_model = build_mesh.to_trimesh()
        tm_model, self._scale_factor = _auto_rescale_to_mm(tm_model, model.unit)
        tm_model = _repair_mesh(tm_model)
        tm_model = _ensure_min_faces(tm_model, min_faces=MOLD_MIN_FACES)
        cavity = self._create_cavity(tm_model)
        center = np.asarray(tm_model.centroid, dtype=np.float64)

        outer = self._create_outer_shell(cavity)
        cavity_inv = cavity.copy()
        cavity_inv.invert()

        box_parts = [outer]
        for d_idx, d in enumerate(directions):
            d = np.asarray(d, dtype=np.float64)
            d = d / np.linalg.norm(d)
            new_parts = []
            for part in box_parts:
                for sign in (1, -1):
                    h = _safe_slice(part, center, sign * d)
                    if h is not None and len(h.faces) > 0:
                        new_parts.append(h)
            if new_parts:
                box_parts = new_parts
            logger.info("Split %d: %d parts", d_idx + 1, len(box_parts))

        box_centers = np.array([bp.centroid for bp in box_parts])
        cav_centers = cavity_inv.triangles_center
        dists = np.linalg.norm(
            cav_centers[:, None, :] - box_centers[None, :, :], axis=-1,
        )
        assignments = np.argmin(dists, axis=1)

        shells: list[MoldShell] = []
        for i, box_part in enumerate(box_parts):
            cav_sub = _extract_submesh(cavity_inv, assignments == i)
            try:
                combined = trimesh.util.concatenate([box_part, cav_sub])
            except Exception:
                combined = box_part
            d = directions[min(i, len(directions) - 1)]
            d = np.asarray(d, dtype=np.float64)
            d = d / (np.linalg.norm(d) + 1e-12)
            shells.append(MoldShell(
                shell_id=i,
                mesh=MeshData.from_trimesh(combined),
                direction=d,
                volume=(
                    float(combined.volume) if combined.is_watertight else 0.0
                ),
                surface_area=float(combined.area),
            ))

        cavity_vol = float(cavity.volume) if cavity.is_watertight else 0.0
        alignment = (
            self._generate_alignment_features(
                tm_model, directions[0], center,
            )
            if self.config.add_alignment_pins else []
        )

        logger.info(
            "Multi-part: %d shells in %.1fs",
            len(shells), time.perf_counter() - t0,
        )
        return MoldResult(
            shells=shells,
            cavity_volume=cavity_vol,
            alignment_features=alignment,
        )

    # ═══════════════ Shell Construction Strategies ══════════════

    def _build_shells_adaptive_surface(
        self, tm_model: trimesh.Trimesh, outer: trimesh.Trimesh,
        cavity: trimesh.Trimesh, center: np.ndarray, direction: np.ndarray,
    ) -> list[MoldShell] | None:
        """Split mold using an adaptive (non-planar) parting surface.

        Generates a heightfield or projected parting surface via
        PartingGenerator, then creates a thin cutting slab from the surface
        mesh to perform the split via boolean operations.
        """
        from moldgen.core.parting import PartingConfig, PartingGenerator
        from moldgen.core.mesh_data import MeshData

        surf_type = self.config.parting_surface_type
        config = PartingConfig(
            surface_type=surf_type,
            heightfield_resolution=30,
            heightfield_smooth=3,
            extend_margin=self.config.margin + 5.0,
        )
        gen = PartingGenerator(config)

        mesh_data = MeshData.from_trimesh(tm_model)
        try:
            result = gen.generate(mesh_data, direction)
        except Exception:
            logger.warning("Adaptive parting generation failed, fallback to flat")
            return None

        if result.parting_surface is None:
            return None

        actual_type = result.surface_type_used
        if actual_type == "flat":
            return None

        surf_tm = result.parting_surface.mesh.to_trimesh()
        if len(surf_tm.faces) < 3:
            return None

        logger.info(
            "Adaptive split: surface_type=%s, %d faces",
            actual_type, len(surf_tm.faces),
        )

        # Create a thick slab from the surface by extruding vertices
        # in ±direction by a small offset.  Then use:
        #   upper_half = outer ∩ above_slab  (i.e. outer - below_slab)
        #   lower_half = outer ∩ below_slab  (i.e. outer - above_slab)
        slab_offset = 0.01  # very thin
        verts = np.asarray(surf_tm.vertices, dtype=np.float64)
        faces = np.asarray(surf_tm.faces, dtype=np.int64)
        n_v = len(verts)
        n_f = len(faces)

        # Top and bottom shifted surfaces
        verts_top = verts + direction * slab_offset
        verts_bot = verts - direction * slab_offset

        # For each original shell (upper/lower):
        # Build a "half-space" volume by combining the surface with a large
        # bounding box above/below, then intersect with outer.
        bounds = outer.bounds
        extent = np.linalg.norm(bounds[1] - bounds[0]) + 20.0
        half_extent = extent / 2.0

        shells: list[MoldShell] = []
        for i, (side_dir, side_name) in enumerate(
            [(direction, "upper"), (-direction, "lower")]
        ):
            # Slice outer at each surface vertex position along direction:
            # Use a simpler approach — for each half, project the surface
            # vertices to determine which vertices of outer are above/below
            outer_verts = np.asarray(outer.vertices, dtype=np.float64)

            # For each outer vertex, find the height of the nearest
            # surface point and check if the vertex is above or below
            from scipy.spatial import cKDTree

            # Project everything onto the UV plane perpendicular to direction
            arb = np.array([1, 0, 0]) if abs(direction[0]) < 0.9 else np.array([0, 1, 0])
            u_ax = np.cross(direction, arb)
            u_ax /= np.linalg.norm(u_ax)
            v_ax = np.cross(direction, u_ax)
            v_ax /= np.linalg.norm(v_ax)

            surf_uv = np.column_stack([verts @ u_ax, verts @ v_ax])
            surf_h = verts @ direction

            tree = cKDTree(surf_uv)

            outer_uv = np.column_stack([outer_verts @ u_ax, outer_verts @ v_ax])
            outer_h = outer_verts @ direction

            _, idx = tree.query(outer_uv, k=1)
            local_h = surf_h[idx]

            # Vertices on the correct side for this shell half
            if side_name == "upper":
                keep_mask = outer_h >= local_h - 0.05
            else:
                keep_mask = outer_h <= local_h + 0.05

            outer_half = _extract_submesh(outer, keep_mask[outer.faces].all(axis=1))

            if outer_half is None or len(outer_half.faces) < 4:
                logger.warning("Adaptive split: no geometry for %s half", side_name)
                continue

            # Boolean subtract cavity
            shell_mesh = self._robust_boolean_subtract(outer_half, cavity)
            if shell_mesh is None or len(shell_mesh.faces) < 10:
                logger.warning("Adaptive split: boolean failed for %s", side_name)
                continue

            shell_mesh = _repair_mesh(shell_mesh)
            d = np.asarray(side_dir, dtype=np.float64)
            d = d / (np.linalg.norm(d) + 1e-12)
            shells.append(MoldShell(
                shell_id=i,
                mesh=MeshData.from_trimesh(shell_mesh),
                direction=d,
                volume=float(shell_mesh.volume) if shell_mesh.is_watertight else 0.0,
                surface_area=float(shell_mesh.area),
            ))

        if len(shells) >= 2:
            logger.info("Adaptive surface split: %d shells", len(shells))
            return shells

        logger.warning("Adaptive split produced %d shells, falling back", len(shells))
        return None

    def _build_shells_slice_then_subtract(
        self, outer: trimesh.Trimesh, cavity: trimesh.Trimesh,
        center: np.ndarray, direction: np.ndarray,
    ) -> list[MoldShell] | None:
        """Primary strategy: slice outer shell first, then subtract cavity.

        For box mode this ensures:
        - Each half-box is a simple convex shape (slice_plane cap works correctly)
        - Boolean(half_box - cavity) naturally produces the cavity impression
        - The parting face has the cavity opening (no sealing needed)
        """
        shells: list[MoldShell] = []

        for i, normal in enumerate([direction, -direction]):
            d = np.asarray(normal, dtype=np.float64)
            d = d / (np.linalg.norm(d) + 1e-12)

            # Slice outer shell at parting plane — convex cut, cap is a
            # simple rectangle (no annular issues)
            outer_half = _safe_slice(outer, center, d)
            if outer_half is None or len(outer_half.faces) < 4:
                logger.warning("Cannot slice outer for shell %d", i)
                continue

            # Boolean subtract the FULL cavity from this outer half.
            # The boolean clips the cavity to the half-box volume and
            # naturally leaves the cavity impression open at the parting face.
            shell_mesh = self._robust_boolean_subtract(outer_half, cavity)

            if shell_mesh is None or len(shell_mesh.faces) < 10:
                logger.warning("Boolean (outer_half - cavity) failed for shell %d", i)
                continue

            shell_mesh = _repair_mesh(shell_mesh)
            logger.info(
                "Slice-then-subtract shell %d: %d faces, watertight=%s",
                i, len(shell_mesh.faces), shell_mesh.is_watertight,
            )

            shells.append(MoldShell(
                shell_id=i,
                mesh=MeshData.from_trimesh(shell_mesh),
                direction=np.asarray(d, dtype=np.float64),
                volume=float(shell_mesh.volume) if shell_mesh.is_watertight else 0.0,
                surface_area=float(shell_mesh.area),
            ))

        if len(shells) >= 2:
            logger.info("Slice-then-subtract mold: %d shells", len(shells))
            return shells
        return None

    def _build_direct_shells(
        self, cavity: trimesh.Trimesh,
        center: np.ndarray, direction: np.ndarray,
    ) -> list[MoldShell]:
        """Last-resort fallback: concatenate half-box + inverted cavity half.

        No boolean needed — just geometric concatenation.
        Outer surfaces come from a sliced box, inner from inverted cavity.
        """
        outer = self._create_outer_shell(cavity)
        up = direction / (np.linalg.norm(direction) + 1e-12)

        shells: list[MoldShell] = []
        for i, normal in enumerate([direction, -direction]):
            d = np.asarray(normal, dtype=np.float64)
            d = d / (np.linalg.norm(d) + 1e-12)

            # Outer half-box: slice outer at parting plane (cap=True for
            # the box boundary, but we'll trim the cap where cavity is)
            outer_half = _safe_slice(outer, center, d)
            if outer_half is None or len(outer_half.faces) < 4:
                dots = (outer.triangles_center - center) @ d
                outer_half = _extract_submesh(outer, dots >= 0)

            # Inner cavity surface (inverted normals for the mold impression)
            cavity_inv = cavity.copy()
            cavity_inv.invert()
            cav_half = _safe_slice(cavity_inv, center, d)
            if cav_half is None or len(cav_half.faces) < 4:
                cav_dots = (cavity_inv.triangles_center - center) @ d
                cav_half = _extract_submesh(cavity_inv, cav_dots >= 0)

            parts = [outer_half]
            if cav_half is not None and len(cav_half.faces) > 0:
                parts.append(cav_half)

            try:
                combined = trimesh.util.concatenate(parts)
            except Exception:
                combined = outer_half

            combined = _repair_mesh(combined)

            shells.append(MoldShell(
                shell_id=i, mesh=MeshData.from_trimesh(combined),
                direction=np.asarray(d, dtype=np.float64),
                volume=float(combined.volume) if combined.is_watertight else 0.0,
                surface_area=float(combined.area),
            ))
        return shells

    # ═══════════════ Robust Boolean + Voxel Fallback ═══════════

    def _robust_boolean_subtract(
        self, outer: trimesh.Trimesh, cavity: trimesh.Trimesh,
    ) -> trimesh.Trimesh | None:
        """Try boolean outer-cavity with multiple engines."""
        # Engine 1: manifold3d
        try:
            import manifold3d
            m_outer = manifold3d.Manifold(manifold3d.Mesh(
                vert_properties=np.asarray(outer.vertices, dtype=np.float32),
                tri_verts=np.asarray(outer.faces, dtype=np.uint32),
            ))
            m_cavity = manifold3d.Manifold(manifold3d.Mesh(
                vert_properties=np.asarray(cavity.vertices, dtype=np.float32),
                tri_verts=np.asarray(cavity.faces, dtype=np.uint32),
            ))
            diff = m_outer - m_cavity
            out = diff.to_mesh()
            result = trimesh.Trimesh(
                vertices=np.asarray(out.vert_properties[:, :3]),
                faces=np.asarray(out.tri_verts), process=True,
            )
            if len(result.faces) > 10:
                logger.info("manifold3d boolean OK: %d faces", len(result.faces))
                return result
        except Exception as e:
            logger.warning("manifold3d boolean failed: %s", e)

        # Engine 2: trimesh.boolean (tries available engines)
        for engine in ("manifold", "blender", None):
            try:
                kw = {"engine": engine} if engine else {}
                result = outer.difference(cavity, **kw)
                if result is not None and len(result.faces) > 10:
                    logger.info(
                        "trimesh boolean (%s) OK: %d faces",
                        engine or "default", len(result.faces),
                    )
                    return result
            except Exception as e:
                logger.debug("trimesh boolean (%s) failed: %s", engine, e)

        return None

    # ═══════════════ Parting Surface Geometry ══════════════════════

    def _robust_boolean_union(
        self, mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh,
    ) -> trimesh.Trimesh | None:
        """Try boolean union with multiple engines."""
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
            result_m = m_a + m_b
            out = result_m.to_mesh()
            result = trimesh.Trimesh(
                vertices=np.asarray(out.vert_properties[:, :3]),
                faces=np.asarray(out.tri_verts), process=True,
            )
            if len(result.faces) > 4:
                return result
        except Exception as e:
            logger.debug("manifold3d union failed: %s", e)

        for engine in ("manifold", "blender", None):
            try:
                kw = {"engine": engine} if engine else {}
                result = mesh_a.union(mesh_b, **kw)
                if result is not None and len(result.faces) > 4:
                    return result
            except Exception:
                pass

        return None

    def _robust_boolean_intersect(
        self, mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh,
    ) -> trimesh.Trimesh | None:
        """Try boolean intersection with multiple engines."""
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
            result_m = m_a ^ m_b
            out = result_m.to_mesh()
            result = trimesh.Trimesh(
                vertices=np.asarray(out.vert_properties[:, :3]),
                faces=np.asarray(out.tri_verts), process=True,
            )
            if len(result.faces) > 4:
                return result
        except Exception as e:
            logger.debug("manifold3d intersect failed: %s", e)

        for engine in ("manifold", "blender", None):
            try:
                kw = {"engine": engine} if engine else {}
                result = mesh_a.intersection(mesh_b, **kw)
                if result is not None and len(result.faces) > 4:
                    return result
            except Exception:
                pass

        return None

    def _create_parting_interlock(
        self,
        solid: trimesh.Trimesh,
        center: np.ndarray,
        direction: np.ndarray,
    ) -> trimesh.Trimesh | None:
        """Create interlock geometry at the parting plane.

        Uses the mold cross-section outline at the parting plane to place
        features precisely along the wall boundary. This ensures features
        only exist in the mold wall region and never protrude through the cavity.
        """
        c = self.config
        style = c.parting_style
        if style == "flat":
            return None

        up = direction / (np.linalg.norm(direction) + 1e-12)
        depth = c.parting_depth
        pitch = c.parting_pitch

        outline_pts = self._get_parting_outline(solid, center, up)
        if outline_pts is None or len(outline_pts) < 6:
            logger.warning("Cannot extract parting outline; skipping interlock")
            return None

        feature_pts, tangents = self._sample_outline_at_pitch(outline_pts, pitch)
        if len(feature_pts) < 2:
            logger.warning("Too few outline points for interlock features")
            return None

        parts: list[trimesh.Trimesh] = []
        for i, (pt, tan) in enumerate(zip(feature_pts, tangents)):
            normal_in_plane = np.cross(up, tan)
            nrm = np.linalg.norm(normal_in_plane)
            if nrm < 1e-10:
                continue
            normal_in_plane /= nrm

            feat = self._make_interlock_unit(
                style, i, pt, up, tan, normal_in_plane, depth, pitch,
            )
            if feat is not None:
                parts.append(feat)

        if not parts:
            return None

        try:
            combined = trimesh.util.concatenate(parts)
            _repair_mesh(combined)
            logger.info("Parting interlock: %d features, %d faces", len(parts), len(combined.faces))
            return combined
        except Exception as e:
            logger.warning("Parting interlock creation failed: %s", e)
            return None

    def _get_parting_outline(
        self, solid: trimesh.Trimesh, center: np.ndarray, up: np.ndarray,
    ) -> np.ndarray | None:
        """Get **ordered** 3D polyline on the **outer mold wall** section at the parting plane.

        ``trimesh`` section of a hollow mold yields multiple 2D loops: the
        outer box silhouette and one or more inner loops from the cavity
        (often much longer in perimeter on high-res organ meshes).  Choosing
        the **longest perimeter** wrongly locks dovetail/zigzag to the cavity
        contour.  We pick the loop with the **largest absolute 2D area**
        (outer shell boundary) and fall back to longest perimeter only if
        areas are degenerate.
        """
        try:
            up = np.asarray(up, dtype=np.float64)
            up = up / (np.linalg.norm(up) + 1e-12)
            section = solid.section(plane_origin=center, plane_normal=up)
            if section is None:
                logger.debug("Parting outline: solid.section returned None")
                return None
            section_2d, to_3D = section.to_planar()
            if section_2d is None:
                return None

            candidates: list[tuple[float, float, np.ndarray]] = []
            for path_pts in section_2d.discrete:
                arr = np.asarray(path_pts, dtype=np.float64)
                if arr.ndim != 2 or len(arr) < 3:
                    continue
                area = _shoelace_area_2d(arr)
                perim = _path_perimeter_2d(arr)
                candidates.append((area, perim, arr))

            if not candidates:
                return None

            max_area = max(c[0] for c in candidates)
            area_tol = max(1e-6, 0.001 * max_area)
            if max_area > area_tol:
                best_2d = max(candidates, key=lambda c: c[0])[2]
                logger.debug(
                    "Parting outline: chose loop by max area=%.2f (n_cands=%d)",
                    max_area, len(candidates),
                )
            else:
                best_2d = max(candidates, key=lambda c: c[1])[2]
                logger.debug(
                    "Parting outline: areas degenerate — fallback max perimeter=%.2f",
                    max(candidates, key=lambda c: c[1])[1],
                )

            if len(best_2d) < 4:
                return None

            pts_list: list[np.ndarray] = []
            for pt_2d in best_2d:
                homog = np.array([pt_2d[0], pt_2d[1], 0.0, 1.0])
                pts_list.append((to_3D @ homog)[:3])
            pts = np.array(pts_list, dtype=np.float64)

            centroid = pts.mean(axis=0)
            inward_offset = min(self.config.parting_pitch * 0.3, 3.0)
            for i in range(len(pts)):
                to_center = centroid - pts[i]
                d = np.linalg.norm(to_center)
                if d > 1e-6:
                    pts[i] += to_center / d * min(inward_offset, d * 0.2)
            return pts
        except Exception as e:
            logger.warning("Cross-section extraction failed: %s", e)
            return None

    def _sample_outline_at_pitch(
        self, outline_pts: np.ndarray, pitch: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Sample points on a **closed** polyline at ~pitch spacing with valid tangents."""
        if len(outline_pts) < 3:
            return np.zeros((0, 3)), np.zeros((0, 3))

        loop = np.vstack([outline_pts, outline_pts[:1]])
        diffs = np.diff(loop, axis=0)
        seg_lengths = np.linalg.norm(diffs, axis=1)
        total_length = float(seg_lengths.sum())
        if total_length < 1e-9:
            return outline_pts[:1], np.zeros_like(outline_pts[:1])

        pitch = max(float(pitch), 1e-3)
        n_features = max(4, int(total_length / pitch))
        sample_dists = np.linspace(0.0, total_length, n_features, endpoint=False)

        cum_length = np.concatenate([[0.0], np.cumsum(seg_lengths)])

        points: list[np.ndarray] = []
        tangents: list[np.ndarray] = []
        for d in sample_dists:
            d = d % total_length
            idx = int(np.searchsorted(cum_length, d, side="right")) - 1
            idx = max(0, min(idx, len(diffs) - 1))
            frac = (d - cum_length[idx]) / (seg_lengths[idx] + 1e-12)
            pt = loop[idx] + frac * diffs[idx]
            tan = diffs[idx] / (seg_lengths[idx] + 1e-12)
            tn = np.linalg.norm(tan)
            if tn < 1e-12:
                nv = len(outline_pts)
                tan = outline_pts[(idx + 1) % nv] - outline_pts[idx % nv]
                tn = np.linalg.norm(tan)
                tan = tan / tn if tn > 1e-12 else np.array([1.0, 0.0, 0.0])
            else:
                tan = tan / tn
            points.append(pt)
            tangents.append(tan)

        return np.array(points), np.array(tangents)

    def _make_interlock_unit(
        self,
        style: str,
        index: int,
        position: np.ndarray,
        up: np.ndarray,
        tangent: np.ndarray,
        normal: np.ndarray,
        depth: float,
        pitch: float,
    ) -> trimesh.Trimesh | None:
        """Create a single interlock feature that straddles the parting plane.

        Features are centered AT the parting plane (extending ±depth/2),
        so both the upper and lower shells receive matching geometry
        (protrusion in one, groove in the other).
        """
        fw = pitch * 0.55   # extent along tangent
        fd = pitch * 0.45   # extent along in-plane normal (wall direction)

        if style == "step":
            if index % 2 != 0:
                return None
            box = trimesh.primitives.Box(extents=[fw, fd, depth]).to_mesh()
            T = np.eye(4)
            T[:3, 0] = tangent
            T[:3, 1] = normal
            T[:3, 2] = up
            T[:3, 3] = position          # centered AT the plane, not above it
            box.apply_transform(T)
            return box

        elif style == "dovetail":
            top_w, bot_w, h, d = fw * 0.8, fw * 0.4, depth, fd
            half_h = h / 2
            verts = np.array([
                [-top_w / 2, -d / 2, -half_h], [top_w / 2, -d / 2, -half_h],
                [bot_w / 2, -d / 2, half_h],    [-bot_w / 2, -d / 2, half_h],
                [-top_w / 2, d / 2, -half_h],   [top_w / 2, d / 2, -half_h],
                [bot_w / 2, d / 2, half_h],      [-bot_w / 2, d / 2, half_h],
            ])
            faces = np.array([
                [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
                [0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7],
            ])
            T = np.eye(4)
            T[:3, 0] = tangent; T[:3, 1] = normal; T[:3, 2] = up
            T[:3, 3] = position
            mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
            mesh.apply_transform(T)
            return mesh

        elif style == "zigzag":
            w, d, h = fw, fd, depth
            half_h = h / 2
            verts = np.array([
                [-w / 2, -d / 2, -half_h], [w / 2, -d / 2, -half_h],
                [0, -d / 2, half_h],
                [-w / 2, d / 2, -half_h],  [w / 2, d / 2, -half_h],
                [0, d / 2, half_h],
            ])
            faces = np.array([
                [0, 1, 2], [3, 5, 4],
                [0, 3, 4], [0, 4, 1],
                [1, 4, 5], [1, 5, 2],
                [2, 5, 3], [2, 3, 0],
            ])
            T = np.eye(4)
            T[:3, 0] = tangent; T[:3, 1] = normal; T[:3, 2] = up
            T[:3, 3] = position
            mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
            mesh.apply_transform(T)
            return mesh

        elif style == "tongue_groove":
            box = trimesh.primitives.Box(extents=[fw * 0.5, fd, depth]).to_mesh()
            T = np.eye(4)
            T[:3, 0] = tangent; T[:3, 1] = normal; T[:3, 2] = up
            T[:3, 3] = position          # centered AT the plane
            box.apply_transform(T)
            return box

        return None

    def _apply_parting_interlock(
        self,
        solid: trimesh.Trimesh,
        center: np.ndarray,
        direction: np.ndarray,
    ) -> tuple[trimesh.Trimesh | None, trimesh.Trimesh | None]:
        """Split solid with interlock profile.

        Strategy 1: Boolean union/subtract with interlock geometry.
        Strategy 2: Direct vertex displacement on parting face vertices.
        """
        upper = _safe_slice(solid, center, direction)
        lower = _safe_slice(solid, center, -direction)

        if upper is None or lower is None:
            return upper, lower

        interlock = self._create_parting_interlock(solid, center, direction)
        if interlock is None:
            # Fallback to vertex displacement
            return self._displace_parting_verts(upper, lower, center, direction)

        union_result = self._robust_boolean_union(upper, interlock)
        if union_result is not None and len(union_result.faces) > len(upper.faces) // 2:
            upper_new = _repair_mesh(union_result)
            sub_result = self._robust_boolean_subtract(lower, interlock)
            if sub_result is not None and len(sub_result.faces) > 4:
                lower_new = _repair_mesh(sub_result)
                logger.info("Parting interlock: boolean OK (upper=%d, lower=%d faces)",
                            len(upper_new.faces), len(lower_new.faces))
                return upper_new, lower_new

        logger.info("Parting interlock: boolean failed, using vertex displacement")
        return self._displace_parting_verts(upper, lower, center, direction)

    def _displace_parting_verts(
        self,
        upper: trimesh.Trimesh,
        lower: trimesh.Trimesh,
        center: np.ndarray,
        direction: np.ndarray,
    ) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
        """Displace vertices near the parting plane to create interlocking geometry."""
        c = self.config
        style = c.parting_style
        depth = c.parting_depth
        pitch = c.parting_pitch
        up = direction / (np.linalg.norm(direction) + 1e-12)

        for half, sign in [(upper, 1.0), (lower, -1.0)]:
            verts = np.asarray(half.vertices, dtype=np.float64)
            heights = (verts - center) @ up
            near_mask = np.abs(heights) < depth * 1.5

            if not np.any(near_mask):
                continue

            near_idx = np.where(near_mask)[0]
            near_verts = verts[near_idx]

            arb = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1.0, 0])
            u_ax = np.cross(up, arb)
            u_ax /= np.linalg.norm(u_ax) + 1e-12

            coords_u = (near_verts - center) @ u_ax

            if style == "zigzag":
                phase = (coords_u % pitch) / pitch
                displacement = np.where(phase < 0.5, depth * (2 * phase), depth * (2 - 2 * phase))
            elif style == "step":
                phase = (coords_u % pitch) / pitch
                displacement = np.where(phase < 0.5, depth, 0.0)
            elif style == "dovetail":
                phase = (coords_u % pitch) / pitch * 2.0 * np.pi
                displacement = depth * 0.5 * (1.0 + np.sin(phase))
            elif style == "tongue_groove":
                phase = (coords_u % pitch) / pitch
                displacement = np.where(
                    (phase > 0.25) & (phase < 0.75), depth, 0.0,
                )
            else:
                displacement = np.zeros(len(near_idx))

            verts[near_idx] += (sign * displacement)[:, None] * up[None, :]
            half.vertices = verts

        logger.info("Parting interlock: vertex displacement applied (style=%s)", style)
        return upper, lower

    def _apply_parting_interlock_to_shells(
        self, shells: list[MoldShell],
        center: np.ndarray, direction: np.ndarray,
    ) -> list[MoldShell]:
        """Apply parting interlock profile to pre-built shell meshes.

        Works on shells generated by slice-then-subtract: extracts the
        trimesh objects, applies interlock (boolean or vertex displacement),
        and returns updated MoldShell list.
        """
        if len(shells) < 2:
            return shells

        upper_tm = shells[0].mesh.to_trimesh()
        lower_tm = shells[1].mesh.to_trimesh()

        interlock = self._create_parting_interlock(
            trimesh.util.concatenate([upper_tm, lower_tm]),
            center, direction,
        )

        applied = False
        if interlock is not None:
            union_r = self._robust_boolean_union(upper_tm, interlock)
            if union_r is not None and len(union_r.faces) > len(upper_tm.faces) // 2:
                sub_r = self._robust_boolean_subtract(lower_tm, interlock)
                if sub_r is not None and len(sub_r.faces) > 4:
                    upper_tm = _repair_mesh(union_r)
                    lower_tm = _repair_mesh(sub_r)
                    applied = True
                    logger.info(
                        "Parting interlock (boolean): upper=%d, lower=%d faces",
                        len(upper_tm.faces), len(lower_tm.faces),
                    )

        if not applied:
            upper_tm, lower_tm = self._displace_parting_verts(
                upper_tm, lower_tm, center, direction,
            )
            logger.info("Parting interlock (vertex displacement): style=%s",
                        self.config.parting_style)

        result: list[MoldShell] = []
        for i, (tm, sh_orig) in enumerate([(upper_tm, shells[0]), (lower_tm, shells[1])]):
            tm = _repair_mesh(tm)
            result.append(MoldShell(
                shell_id=sh_orig.shell_id,
                mesh=MeshData.from_trimesh(tm),
                direction=sh_orig.direction,
                volume=float(tm.volume) if tm.is_watertight else sh_orig.volume,
                surface_area=float(tm.area),
                is_printable=sh_orig.is_printable,
                min_draft_angle=sh_orig.min_draft_angle,
            ))
        result.extend(shells[2:])
        return result

    # ═══════════════ Screw Hole Generation ═══════════════════════

    def _generate_screw_holes(
        self, shells: list[MoldShell], tm_model: trimesh.Trimesh,
        direction: np.ndarray, center: np.ndarray,
    ) -> tuple[list[MoldShell], list[ScrewHoleFeature]]:
        """Create pocket-and-tab screw fastening at mold wall corners.

        At each screw position a rectangular pocket is cut from the
        outer face of each shell half down to ``screw_tab_thickness``
        above/below the parting plane.  The remaining thin *tab* near
        the parting plane receives a through-bolt hole and optional
        counterbore.  This allows short standard screws instead of
        full-height bolts.

        Cross-section at one corner::

              shell outer face
            ┌────────────────┐
            │    pocket      │ ← box subtraction removes material
            │                │
            ├────┐      ┌────┤
            │    │ tab  │    │ ← screw_tab_thickness
            ├────┤      ├────┤ ← parting plane
            │    │ tab  │    │
            ├────┘      └────┤
            │                │
            │    pocket      │
            └────────────────┘

        Uses ``_make_oriented_box`` for robust boolean-friendly geometry
        with a ``_make_cylinder`` fallback if box subtraction fails.
        """
        c = self.config
        spec = M_SCREW_TABLE.get(c.screw_size, M_SCREW_TABLE["M4"])
        up = direction / (np.linalg.norm(direction) + 1e-12)

        arb = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0.0, 1, 0])
        u_ax = np.cross(up, arb); u_ax /= (np.linalg.norm(u_ax) + 1e-12)
        v_ax = np.cross(up, u_ax); v_ax /= (np.linalg.norm(v_ax) + 1e-12)

        bounds = tm_model.bounds
        model_extent = bounds[1] - bounds[0]
        half_u = abs(float(model_extent @ u_ax)) / 2
        half_v = abs(float(model_extent @ v_ax)) / 2

        wall_mid = (c.clearance + c.margin + c.wall_thickness) / 2
        avail_wall = c.margin + c.wall_thickness - c.clearance
        if avail_wall < spec["through"] + 2.0:
            logger.warning(
                "Screw %s requires %.1fmm but wall only %.1fmm wide — skipping",
                c.screw_size, spec["through"] + 2.0, avail_wall,
            )
            return shells, []

        tab = c.screw_tab_thickness

        # Pocket must extend BEYOND outer wall surface to prevent thin shells.
        # avail_wall+4 guarantees 2mm overshoot on each side; boolean ignores
        # the part outside the shell, only cuts what overlaps.
        pocket_xy = max(
            max(spec["head"], spec["nut"]) * 2.5,
            avail_wall + 4.0,
        )

        # ── Build positions: corners first, then edge midpoints ──
        positions: list[np.ndarray] = []
        corners = [(+1, +1), (+1, -1), (-1, +1), (-1, -1)]
        for su, sv in corners[:min(c.n_screws, 4)]:
            pos = (center
                   + su * (half_u + wall_mid) * u_ax
                   + sv * (half_v + wall_mid) * v_ax)
            pos -= up * float(np.dot(pos - center, up))
            positions.append(pos)

        if c.n_screws > 4:
            edges = [(+1, 0), (-1, 0), (0, +1), (0, -1)]
            for su, sv in edges[:c.n_screws - 4]:
                pos = (center
                       + (su * (half_u + wall_mid) if su else 0) * u_ax
                       + (sv * (half_v + wall_mid) if sv else 0) * v_ax)
                pos -= up * float(np.dot(pos - center, up))
                positions.append(pos)

        # ── Proximity safety check ──
        safe_dist = spec["through"] / 2 + c.clearance + 0.5
        try:
            _, dists, _ = tm_model.nearest.on_surface(np.array(positions))
            keep = [i for i, d in enumerate(dists) if d >= safe_dist]
            if len(keep) < len(positions):
                logger.warning(
                    "Dropped %d/%d screw positions too close to cavity",
                    len(positions) - len(keep), len(positions),
                )
                positions = [positions[i] for i in keep]
        except Exception:
            pass

        if not positions:
            return shells, []

        through_r = spec["through"] / 2.0
        cb_r = spec["head"] / 2.0
        cb_depth = min(spec["nut_h"] + 1.0, tab * 0.35)
        center_h = float(np.dot(center, up))

        features: list[ScrewHoleFeature] = []
        updated_shells: list[MoldShell] = []

        for sh in shells:
            tm_shell = sh.mesh.to_trimesh()
            verts_h = tm_shell.vertices @ up
            sh_h_min = float(verts_h.min())
            sh_h_max = float(verts_h.max())
            is_upper = ((sh_h_min + sh_h_max) / 2) > center_h

            for pos in positions:
                # ── Step 1: Rectangular pocket from outer face to tab ──
                if is_upper:
                    pocket_lo = center_h + tab
                    pocket_hi = sh_h_max + 2.0
                else:
                    pocket_lo = sh_h_min - 2.0
                    pocket_hi = center_h - tab

                pocket_h = abs(pocket_hi - pocket_lo)
                if pocket_h < 2.0:
                    continue

                pocket_mid_h = (pocket_hi + pocket_lo) / 2
                pocket_center = pos + up * (pocket_mid_h - center_h)

                pocket_ok = False

                # Primary: oriented box built from world-space vertices
                pocket_box = _make_oriented_box(
                    pocket_center, u_ax, v_ax, up,
                    pocket_xy, pocket_xy, pocket_h,
                )
                result = self._robust_boolean_subtract(tm_shell, pocket_box)
                if result is not None and len(result.faces) > 10:
                    tm_shell = result
                    pocket_ok = True
                    logger.info(
                        "Pocket box OK at [%.1f,%.1f,%.1f]  %d faces",
                        *pocket_center, len(tm_shell.faces),
                    )

                # Fallback: cylindrical pocket (always works with boolean)
                if not pocket_ok:
                    logger.warning(
                        "Box pocket failed — falling back to cylinder at "
                        "[%.1f,%.1f,%.1f]",
                        *pocket_center,
                    )
                    pocket_cyl = _make_cylinder(
                        pocket_center, up,
                        radius=pocket_xy / 2.0,
                        height=pocket_h + 1.0,
                    )
                    result = self._robust_boolean_subtract(tm_shell, pocket_cyl)
                    if result is not None and len(result.faces) > 10:
                        tm_shell = result
                        pocket_ok = True

                if not pocket_ok:
                    logger.error(
                        "Both box and cylinder pocket failed — skipping "
                        "position [%.1f,%.1f,%.1f]",
                        *pos,
                    )
                    continue

                # ── Step 2: Through-hole in remaining tab ──
                hole_h = tab * 2 + 4.0
                cyl = _make_cylinder(pos, up, radius=through_r, height=hole_h)
                result = self._robust_boolean_subtract(tm_shell, cyl)
                if result is not None and len(result.faces) > 10:
                    tm_shell = result

                # ── Step 3: Counterbore on pocket face ──
                if c.screw_counterbore and cb_depth > 0.5:
                    if is_upper:
                        cb_h = center_h + tab - cb_depth / 2
                    else:
                        cb_h = center_h - tab + cb_depth / 2
                    cb_pos = pos + up * (cb_h - center_h)
                    cb_cyl = _make_cylinder(
                        cb_pos, up, radius=cb_r, height=cb_depth + 0.5,
                    )
                    result = self._robust_boolean_subtract(tm_shell, cb_cyl)
                    if result is not None and len(result.faces) > 10:
                        tm_shell = result

            # Light repair only — DO NOT fill_holes here because the pocket
            # openings are intentional (fill_holes would seal them shut).
            try:
                tm_shell.update_faces(tm_shell.nondegenerate_faces())
            except Exception:
                pass
            try:
                tm_shell.remove_duplicate_faces()
            except Exception:
                pass
            for _rfn in (trimesh.repair.fix_normals, trimesh.repair.fix_winding):
                try:
                    _rfn(tm_shell)
                except Exception:
                    pass

            updated_shells.append(MoldShell(
                shell_id=sh.shell_id,
                mesh=MeshData.from_trimesh(tm_shell),
                direction=sh.direction,
                volume=float(abs(tm_shell.volume)) if tm_shell.is_volume else sh.volume,
                surface_area=float(tm_shell.area),
                is_printable=sh.is_printable,
                min_draft_angle=sh.min_draft_angle,
            ))

        for pos in positions:
            features.append(ScrewHoleFeature(
                position=pos,
                screw_size=c.screw_size,
                through_diameter=spec["through"],
                counterbore_diameter=cb_r * 2 if c.screw_counterbore else 0.0,
                counterbore_depth=cb_depth if c.screw_counterbore else 0.0,
            ))

        logger.info(
            "Screw holes: %d × %s pocket+tab (tab=%.1fmm, pocket=%.1fmm sq)",
            len(features), c.screw_size, tab, pocket_xy,
        )
        return updated_shells, features

    # ═══════════════ Clamp Bracket Generation ══════════════════════

    def _generate_clamp_brackets(
        self, shells: list[MoldShell], tm_model: trimesh.Trimesh,
        direction: np.ndarray, center: np.ndarray,
    ) -> list[ClampBracket]:
        """Generate C-shaped clamp brackets that wrap around the parting plane.

        Each bracket is a U-channel that straddles the parting line with
        through-bolt holes for tightening.
        """
        c = self.config
        clamp_spec = M_SCREW_TABLE.get(c.clamp_screw_size, M_SCREW_TABLE["M3"])
        up = direction / (np.linalg.norm(direction) + 1e-12)

        arb = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0.0, 1, 0])
        u_ax = np.cross(up, arb); u_ax /= (np.linalg.norm(u_ax) + 1e-12)
        v_ax = np.cross(up, u_ax); v_ax /= (np.linalg.norm(v_ax) + 1e-12)

        bounds = tm_model.bounds
        max_ext = float(np.max(bounds[1] - bounds[0]))
        bracket_dist = max_ext / 2 + c.margin + c.wall_thickness + c.clamp_width / 2

        all_bounds = np.vstack([sh.mesh.bounds for sh in shells])
        shell_height = float(np.ptp(all_bounds @ up))
        grip_height = min(shell_height * 0.3, c.clamp_width)

        brackets: list[ClampBracket] = []

        for bi in range(c.n_clamp_screws):
            angle = 2 * np.pi * bi / c.n_clamp_screws + np.pi / c.n_clamp_screws
            outward = np.cos(angle) * u_ax + np.sin(angle) * v_ax
            bracket_center = center + outward * bracket_dist

            outer_w = c.clamp_width
            inner_w = outer_w - 2 * c.clamp_thickness
            outer_h = grip_height * 2 + c.clamp_thickness

            outer_box = trimesh.primitives.Box(extents=[outer_w, outer_h, outer_w * 0.6])
            inner_box = trimesh.primitives.Box(extents=[inner_w, grip_height * 2, inner_w * 0.8])

            T = np.eye(4)
            T[:3, 0] = outward
            T[:3, 1] = up
            T[:3, 2] = np.cross(outward, up)
            T[:3, 3] = bracket_center

            outer_mesh = outer_box.to_mesh()
            outer_mesh.apply_transform(T)
            inner_mesh = inner_box.to_mesh()
            inner_mesh.apply_transform(T)

            bracket_mesh = self._robust_boolean_subtract(outer_mesh, inner_mesh)
            if bracket_mesh is None or len(bracket_mesh.faces) < 10:
                bracket_mesh = outer_mesh

            screw_r = clamp_spec["through"] / 2.0
            screw_pos_top = bracket_center + up * (grip_height * 0.6)
            screw_pos_bot = bracket_center - up * (grip_height * 0.6)
            screw_positions = [screw_pos_top, screw_pos_bot]

            for sp in screw_positions:
                cyl = _make_cylinder(sp, outward, radius=screw_r, height=outer_w * 2)
                result = self._robust_boolean_subtract(bracket_mesh, cyl)
                if result is not None and len(result.faces) > 4:
                    bracket_mesh = result

            bracket_mesh = _repair_mesh(bracket_mesh)
            brackets.append(ClampBracket(
                mesh=MeshData.from_trimesh(bracket_mesh),
                screw_positions=screw_positions,
            ))

        logger.info("Clamp brackets: %d × %s screws", len(brackets), c.clamp_screw_size)
        return brackets

    # ═══════════════ Flange Generation ════════════════════════════

    def _generate_flanges(
        self,
        shells: list[MoldShell],
        tm_model: trimesh.Trimesh,
        direction: np.ndarray,
        center: np.ndarray,
    ) -> tuple[list[MoldShell], list[FlangeFeature]]:
        """Add mounting flange tabs with screw holes to each shell at the parting plane."""
        c = self.config
        if not c.add_flanges:
            return shells, []

        up = direction / (np.linalg.norm(direction) + 1e-12)
        arb = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0.0, 1, 0])
        u_ax = np.cross(up, arb); u_ax /= (np.linalg.norm(u_ax) + 1e-12)
        v_ax = np.cross(up, u_ax); v_ax /= (np.linalg.norm(v_ax) + 1e-12)

        bounds = tm_model.bounds
        max_ext = float(np.max(bounds[1] - bounds[0]))
        flange_dist = max_ext / 2 + c.margin + c.wall_thickness + c.flange_width / 2

        features: list[FlangeFeature] = []
        updated_shells: list[MoldShell] = []

        for sh in shells:
            tm_shell = sh.mesh.to_trimesh()

            for fi in range(c.n_flanges):
                angle = 2 * np.pi * fi / c.n_flanges + np.pi / c.n_flanges
                outward = np.cos(angle) * u_ax + np.sin(angle) * v_ax
                flange_center = center + outward * flange_dist

                T = np.eye(4)
                T[:3, 0] = outward
                T[:3, 1] = up
                T[:3, 2] = np.cross(outward, up)
                T[:3, 3] = flange_center

                flange_box = trimesh.primitives.Box(
                    extents=[c.flange_width, c.flange_thickness, c.flange_width * 0.8],
                ).to_mesh()
                flange_box.apply_transform(T)

                screw_cyl = _make_cylinder(
                    flange_center, up,
                    radius=c.screw_hole_diameter / 2,
                    height=c.flange_thickness * 3,
                )

                try:
                    combined = trimesh.util.concatenate([tm_shell, flange_box])
                    cut = self._robust_boolean_subtract(combined, screw_cyl)
                    if cut is not None and len(cut.faces) > len(tm_shell.faces):
                        tm_shell = _repair_mesh(cut)
                    else:
                        tm_shell = _repair_mesh(combined)
                except Exception:
                    try:
                        tm_shell = trimesh.util.concatenate([tm_shell, flange_box])
                    except Exception:
                        pass

                features.append(FlangeFeature(
                    position=flange_center.copy(),
                    normal=outward.copy(),
                    width=c.flange_width,
                    thickness=c.flange_thickness,
                    screw_diameter=c.screw_hole_diameter,
                ))

            updated_shells.append(MoldShell(
                shell_id=sh.shell_id,
                mesh=MeshData.from_trimesh(tm_shell),
                direction=sh.direction,
                volume=float(tm_shell.volume) if tm_shell.is_watertight else sh.volume,
                surface_area=float(tm_shell.area),
                is_printable=sh.is_printable,
                min_draft_angle=sh.min_draft_angle,
            ))

        return updated_shells, features

    # ═══════════════ Shell Splitting ═════════════════════════════

    def _split_solid_to_shells(
        self, solid: trimesh.Trimesh,
        center: np.ndarray, direction: np.ndarray,
    ) -> list[MoldShell]:
        """Split a mold solid into upper/lower halves.

        NOTE: Does NOT seal the parting plane — the cavity impression
        must remain open for a functional mold.
        """
        if self.config.parting_style != "flat":
            upper, lower = self._apply_parting_interlock(solid, center, direction)
            shells: list[MoldShell] = []
            for i, (half, d) in enumerate([
                (upper, direction.copy()), (lower, -direction.copy()),
            ]):
                if half is not None and len(half.faces) >= 4:
                    shells.append(MoldShell(
                        shell_id=i,
                        mesh=MeshData.from_trimesh(half),
                        direction=np.asarray(d, dtype=np.float64),
                        volume=float(half.volume) if half.is_watertight else 0.0,
                        surface_area=float(half.area),
                    ))
            if len(shells) >= 2:
                return shells

        shells = []
        for i, (normal, d) in enumerate([
            (direction, direction.copy()),
            (-direction, -direction.copy()),
        ]):
            half = _safe_slice(solid, center, normal)
            if half is not None and len(half.faces) >= 4:
                shells.append(MoldShell(
                    shell_id=i,
                    mesh=MeshData.from_trimesh(half),
                    direction=np.asarray(d, dtype=np.float64),
                    volume=float(half.volume) if half.is_watertight else 0.0,
                    surface_area=float(half.area),
                ))
        return shells

    def _build_shells_voxel(
        self, tm_model: trimesh.Trimesh,
        center: np.ndarray, direction: np.ndarray,
    ) -> list[MoldShell] | None:
        """Voxel-based mold construction with per-half marching cubes.

        Splits the voxel grid at the parting plane BEFORE marching cubes,
        so each half naturally has the cavity impression open.
        """
        c = self.config
        extents = tm_model.extents
        max_ext = float(np.max(extents))
        if max_ext < 1e-6:
            return None

        target_pitch = min(
            0.55,
            max_ext / 160.0,
            max(0.18, float(c.wall_thickness) / 4.0),
        )
        resolution = int(np.ceil(max_ext / max(target_pitch, max_ext / 320.0)))
        resolution = int(np.clip(resolution, 96, 320))
        pitch = max_ext / resolution
        logger.info("Voxel mold: pitch=%.3f mm, res=%d", pitch, resolution)

        try:
            vox = tm_model.voxelized(pitch)
            if hasattr(vox, "fill"):
                vox = vox.fill()
            model_matrix = vox.matrix.copy()
            vox_origin = np.asarray(vox.transform[:3, 3], dtype=np.float64)
        except Exception as e:
            logger.warning("Voxelization failed: %s", e)
            return None

        if not np.any(model_matrix):
            logger.warning("Voxelization produced empty grid")
            return None

        clearance_px = max(1, int(np.ceil(c.clearance / pitch)))
        cavity_matrix = ndimage.binary_dilation(
            model_matrix, iterations=clearance_px,
        )

        wall_px = max(2, int(np.ceil((c.margin + c.wall_thickness) / pitch)))
        padded_cavity = np.pad(
            cavity_matrix, wall_px, mode="constant", constant_values=False,
        )

        if _shell_is_conformal(c.shell_type):
            outer_matrix = ndimage.binary_dilation(
                padded_cavity, iterations=wall_px,
            )
        else:
            outer_matrix = np.ones_like(padded_cavity, dtype=bool)

        mold_matrix = outer_matrix & ~padded_cavity
        world_origin = vox_origin - wall_px * pitch

        # Determine the split index along the dominant axis of `direction`
        up = direction / (np.linalg.norm(direction) + 1e-12)
        dominant_axis = int(np.argmax(np.abs(up)))
        parting_world = float(center[dominant_axis])
        split_idx = int(round((parting_world - world_origin[dominant_axis]) / pitch))
        split_idx = int(np.clip(split_idx, 1, mold_matrix.shape[dominant_axis] - 1))

        try:
            from skimage.measure import marching_cubes
        except ImportError:
            logger.warning("scikit-image unavailable for marching cubes")
            return None

        shells: list[MoldShell] = []
        target_faces = min(100_000, MOLD_MAX_FACES)

        for i, (lo, hi, d) in enumerate([
            (split_idx, mold_matrix.shape[dominant_axis], direction.copy()),
            (0, split_idx, -direction.copy()),
        ]):
            slices = [slice(None)] * 3
            slices[dominant_axis] = slice(lo, hi)
            half_matrix = mold_matrix[tuple(slices)]

            if not np.any(half_matrix):
                continue

            try:
                verts_vox, faces_mc, normals_mc, _ = marching_cubes(
                    half_matrix.astype(np.float32), level=0.5,
                )
            except Exception as e:
                logger.warning("Marching cubes failed for half %d: %s", i, e)
                continue

            offset = np.zeros(3, dtype=np.float64)
            offset[dominant_axis] = lo * pitch
            verts_world = verts_vox * pitch + world_origin + offset

            half_mesh = trimesh.Trimesh(
                vertices=verts_world, faces=faces_mc,
                vertex_normals=normals_mc, process=True,
            )
            trimesh.repair.fix_normals(half_mesh)

            if len(half_mesh.faces) > target_faces:
                try:
                    half_mesh = half_mesh.simplify_quadric_decimation(target_faces)
                except Exception:
                    pass

            half_mesh = _repair_mesh(half_mesh)
            logger.info("Voxel shell %d: %d faces", i, len(half_mesh.faces))

            shells.append(MoldShell(
                shell_id=i,
                mesh=MeshData.from_trimesh(half_mesh),
                direction=np.asarray(d, dtype=np.float64),
                volume=float(half_mesh.volume) if half_mesh.is_watertight else 0.0,
                surface_area=float(half_mesh.area),
            ))

        return shells if len(shells) >= 2 else None

    # ═══════════════ Cavity / Outer Shell ═══════════════════════

    def _create_cavity(self, tm_model: trimesh.Trimesh) -> trimesh.Trimesh:
        """Vertex-normal offset with Laplacian pre-smooth to reduce
        self-intersections on concave geometry."""
        clearance = self.config.clearance
        if clearance <= 0:
            return tm_model.copy()

        base = tm_model
        if not base.is_watertight:
            base = _repair_mesh(base)
            if not base.is_watertight:
                logger.warning(
                    "Model not watertight after repair (%d open edges); "
                    "cavity offset may be inaccurate",
                    len(base.faces) - base.referenced_vertices.sum()
                    if hasattr(base, "referenced_vertices") else -1,
                )

        try:
            smooth_n = _laplacian_smooth_vertex_normals(base)
            new_verts = base.vertices + smooth_n * clearance
            cav = trimesh.Trimesh(
                vertices=new_verts, faces=base.faces.copy(), process=True,
            )
            cav = _repair_mesh(cav)
            return cav
        except Exception:
            logger.warning("Vertex offset failed, using original")
            return base.copy()

    def _create_outer_shell(self, cavity: trimesh.Trimesh) -> trimesh.Trimesh:
        c = self.config
        bounds = cavity.bounds
        margin = c.margin + c.wall_thickness

        if _shell_is_conformal(c.shell_type):
            try:
                normals = _laplacian_smooth_vertex_normals(cavity)
                t = float(c.wall_thickness)
                new_v = cavity.vertices + normals * t
                disp = new_v - cavity.vertices
                dlen = np.linalg.norm(disp, axis=1)
                bad = (dlen < 0.35 * t) | (dlen > 2.5 * t) | ~np.isfinite(dlen)
                if np.any(bad):
                    nn = normals[bad]
                    nn /= np.linalg.norm(nn, axis=1, keepdims=True) + 1e-12
                    new_v = np.asarray(new_v, dtype=np.float64, order="C")
                    new_v[bad] = cavity.vertices[bad] + nn * t
                return trimesh.Trimesh(
                    vertices=new_v, faces=cavity.faces.copy(), process=True,
                )
            except Exception:
                logger.warning("Conformal shell failed, box fallback")

        box_min = bounds[0] - margin
        box_max = bounds[1] + margin
        box_size = box_max - box_min
        box_center = (box_min + box_max) / 2
        return trimesh.primitives.Box(
            extents=box_size,
            transform=trimesh.transformations.translation_matrix(box_center),
        ).to_mesh()

    # ═══════════════ Pour Gate (v3 Algorithm) ═══════════════════

    def _compute_pour_gate(
        self, tm_model: trimesh.Trimesh,
        cavity: trimesh.Trimesh,
        direction: np.ndarray,
    ) -> HoleFeature:
        """Multi-criteria pour gate placement.

        Score = 0.40 * height + 0.25 * centrality + 0.20 * access + 0.15 * thickness

        - height:     prefer top 20% of model (gravity fill)
        - centrality: prefer near centroid projection axis (even flow)
        - access:     prefer faces whose normal aligns with direction (easy drilling)
        - thickness:  prefer regions with larger local thickness (better flow)
        """
        verts = tm_model.vertices
        normals = tm_model.vertex_normals
        heights = verts @ direction
        h_min, h_max = float(np.min(heights)), float(np.max(heights))
        h_range = h_max - h_min
        c = self.config

        if h_range < 1e-6:
            pos = tm_model.centroid + direction * (c.margin + c.wall_thickness + 5)
            return HoleFeature(
                position=pos, diameter=c.pour_hole_diameter,
                hole_type="pour", score=0.0,
            )

        # 1. Height score (top 20%)
        h_norm = (heights - h_min) / h_range
        height_score = np.clip((h_norm - 0.80) / 0.20, 0, 1)

        # 2. Centrality (distance from centroid on parting plane)
        centroid = tm_model.centroid
        to_v = verts - centroid
        proj_h = np.outer(to_v @ direction, direction)
        proj_plane = to_v - proj_h
        dist_axis = np.linalg.norm(proj_plane, axis=1)
        max_dist = float(np.max(dist_axis)) + 1e-8
        centrality = 1.0 - dist_axis / max_dist

        # 3. Surface normal accessibility (face up = easy pour)
        n_dot = normals @ direction
        access = np.clip(n_dot, 0, 1)

        # 4. Local thickness estimate (Voronoi-based: distance to farthest
        #    vertex within a small neighbourhood along -direction)
        thickness_score = np.zeros(len(verts))
        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(verts)
            sample_idx = np.where(height_score > 0.01)[0]
            if len(sample_idx) == 0:
                sample_idx = np.argsort(h_norm)[-max(10, len(verts) // 100):]
            for vi in sample_idx:
                nbr_d, nbr_i = tree.query(verts[vi], k=min(30, len(verts)))
                if np.isscalar(nbr_d):
                    continue
                spread = float(np.max(nbr_d))
                if spread > 1e-8:
                    thickness_score[vi] = spread
            ts_max = float(np.max(thickness_score)) + 1e-8
            thickness_score = thickness_score / ts_max
        except Exception:
            thickness_score[:] = 0.5

        # Combined score
        score = (
            0.40 * height_score
            + 0.25 * centrality
            + 0.20 * access
            + 0.15 * thickness_score
        )
        # Mask: only top region
        valid = height_score > 0.01
        if not np.any(valid):
            valid = h_norm > 0.5
        score[~valid] = -1

        best_idx = int(np.argmax(score))
        best_score = float(score[best_idx])
        best_pos = verts[best_idx].copy()

        # Offset to mold exterior
        offset = direction * (c.margin + c.wall_thickness + 5.0)
        gate_pos = best_pos + offset

        logger.info(
            "Pour gate: score=%.3f at height=%.1f%% centrality=%.2f",
            best_score,
            float(h_norm[best_idx]) * 100,
            float(centrality[best_idx]),
        )

        # Build funnel geometry
        mesh_data = None
        try:
            funnel = self._make_pour_funnel(gate_pos, direction)
            mesh_data = MeshData.from_trimesh(funnel)
        except Exception:
            pass

        return HoleFeature(
            position=gate_pos,
            diameter=c.pour_hole_diameter,
            hole_type="pour",
            score=best_score,
            mesh=mesh_data,
        )

    def _make_pour_funnel(
        self, position: np.ndarray, direction: np.ndarray,
    ) -> trimesh.Trimesh:
        """Create a funnel (truncated cone + cylinder) for the pour hole."""
        c = self.config
        r = c.pour_hole_diameter / 2.0
        # Cylinder part
        cyl = _make_cylinder(
            position, direction,
            radius=r, height=c.wall_thickness + 2.0,
        )
        # Funnel cone on top
        cone_h = r * np.tan(np.radians(c.pour_funnel_angle))
        cone_pos = position + direction * (c.wall_thickness / 2 + cone_h / 2)
        try:
            cone = trimesh.creation.cone(
                radius=r * 1.5, height=cone_h, sections=24,
            )
            z = np.array([0, 0, 1.0])
            d = direction / (np.linalg.norm(direction) + 1e-12)
            v = np.cross(z, d)
            s = np.linalg.norm(v)
            cc = float(np.dot(z, d))
            if s > 1e-8:
                vx = np.array([
                    [0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0],
                ])
                R = np.eye(3) + vx + vx @ vx * (1 - cc) / (s * s)
            else:
                R = np.eye(3) if cc > 0 else np.diag([1, -1, -1.0])
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = cone_pos
            cone.apply_transform(T)
            return trimesh.util.concatenate([cyl, cone])
        except Exception:
            return cyl

    # ═══════════════ Vent Holes (v3 Algorithm) ══════════════════

    def _compute_vent_holes(
        self, tm_model: trimesh.Trimesh,
        direction: np.ndarray,
        pour_pos: np.ndarray | None = None,
    ) -> list[HoleFeature]:
        """Gravity-fill BFS simulation + air trap detection + farthest-point
        spacing for optimal vent placement.

        Algorithm:
          1. Build face adjacency graph
          2. Modified Dijkstra from pour-hole face: cost increases for
             upward flow (simulating gravity resistance)
          3. Faces with highest fill_time = last to fill = need vents
          4. Detect air traps: local height maxima in adjacency graph
          5. Combined score = fill_time + height + trap potential
          6. Select n_vents positions using farthest-point sampling
        """
        c = self.config
        n_vents = c.n_vent_holes
        face_centers = tm_model.triangles_center
        face_heights = face_centers @ direction
        n_faces = len(face_centers)

        if n_faces < 4:
            return self._fallback_vents(tm_model, direction, n_vents)

        adj = _build_face_adjacency_dict(tm_model)

        # Find start face (nearest to pour hole, or lowest face for gravity)
        if pour_pos is not None:
            dists_to_pour = np.linalg.norm(face_centers - pour_pos, axis=1)
            start = int(np.argmin(dists_to_pour))
        else:
            start = int(np.argmin(face_heights))

        # Modified Dijkstra — upward flow costs more
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
                # Gravity: upward flow is slower (cost = base + height penalty)
                if dh > 0:
                    cost = 1.0 + dh * 3.0
                else:
                    cost = max(0.3, 1.0 + dh * 0.3)
                new_t = t + cost
                if new_t < fill_time[nj]:
                    fill_time[nj] = new_t
                    heapq.heappush(heap, (new_t, nj))

        # Air trap detection: faces that are local height maxima
        air_trap = np.zeros(n_faces)
        for fi in range(n_faces):
            nbrs = adj.get(fi, [])
            if not nbrs:
                continue
            nbr_h = face_heights[np.array(nbrs)]
            if face_heights[fi] > np.max(nbr_h):
                air_trap[fi] = face_heights[fi] - float(np.mean(nbr_h))

        # Normalize scores
        ft_finite = fill_time[np.isfinite(fill_time)]
        if len(ft_finite) == 0:
            return self._fallback_vents(tm_model, direction, n_vents)
        ft_max = float(np.max(ft_finite)) + 1e-8
        fill_norm = np.where(
            np.isfinite(fill_time), fill_time / ft_max, 1.0,
        )

        h_min, h_max = float(np.min(face_heights)), float(np.max(face_heights))
        h_range = h_max - h_min + 1e-8
        height_norm = (face_heights - h_min) / h_range

        trap_max = float(np.max(air_trap)) + 1e-8
        trap_norm = air_trap / trap_max

        # Combined vent score
        vent_score = (
            0.40 * fill_norm
            + 0.35 * height_norm
            + 0.25 * trap_norm
        )

        # Select vents by farthest-point sampling on vent_score
        offset = direction * (c.margin + c.wall_thickness + 2.0)
        min_spacing = float(np.max(tm_model.extents)) * 0.15
        selected: list[HoleFeature] = []
        remaining = np.ones(n_faces, dtype=bool)

        for _ in range(n_vents):
            cands = np.where(remaining)[0]
            if len(cands) == 0:
                break
            best_local = cands[int(np.argmax(vent_score[cands]))]
            pos = face_centers[best_local] + offset
            sc = float(vent_score[best_local])

            # Build vent tube geometry
            mesh_data = None
            try:
                tube = _make_cylinder(
                    pos, direction,
                    radius=c.vent_hole_diameter / 2.0,
                    height=c.wall_thickness + 2.0,
                )
                mesh_data = MeshData.from_trimesh(tube)
            except Exception:
                pass

            selected.append(HoleFeature(
                position=pos,
                diameter=c.vent_hole_diameter,
                hole_type="vent",
                score=sc,
                mesh=mesh_data,
            ))

            # Exclude nearby faces for spacing
            d_sq = np.sum(
                (face_centers - face_centers[best_local]) ** 2, axis=1,
            )
            remaining &= (d_sq > min_spacing * min_spacing)

        logger.info(
            "Vent holes: %d placed (BFS fill sim, %d air traps detected)",
            len(selected), int(np.sum(air_trap > 0)),
        )
        return selected

    def _fallback_vents(
        self, tm_model: trimesh.Trimesh,
        direction: np.ndarray, n_vents: int,
    ) -> list[HoleFeature]:
        """Simple fallback: highest separated vertices."""
        c = self.config
        heights = tm_model.vertices @ direction
        offset = direction * (c.margin + c.wall_thickness + 2.0)
        top_idx = np.argsort(heights)[-max(n_vents * 5, 20):]
        top_verts = tm_model.vertices[top_idx]

        positions: list[HoleFeature] = []
        remaining = top_verts.copy()
        for _ in range(n_vents):
            if len(remaining) == 0:
                break
            if not positions:
                idx = int(np.argmax(remaining @ direction))
            else:
                dists = np.min(
                    [np.linalg.norm(remaining - p.position + offset, axis=1)
                     for p in positions],
                    axis=0,
                )
                idx = int(np.argmax(dists))
            positions.append(HoleFeature(
                position=remaining[idx] + offset,
                diameter=c.vent_hole_diameter,
                hole_type="vent",
            ))
            mask = np.linalg.norm(remaining - remaining[idx], axis=1) > 5.0
            remaining = remaining[mask]
        return positions

    # ═══════════════ Alignment Pins (with geometry) ═════════════

    def _generate_alignment_features(
        self, tm_model: trimesh.Trimesh,
        direction: np.ndarray, center: np.ndarray,
    ) -> list[AlignmentFeature]:
        c = self.config
        bounds = tm_model.bounds
        extents = bounds[1] - bounds[0]
        up = np.asarray(direction, dtype=np.float64)
        arb = (
            np.array([1.0, 0, 0])
            if abs(up[0]) < 0.9
            else np.array([0.0, 1, 0])
        )
        u = np.cross(up, arb).astype(np.float64)
        u /= np.linalg.norm(u)
        v = np.cross(up, u).astype(np.float64)
        v /= np.linalg.norm(v)

        max_ext = float(np.max(extents))
        offset = max_ext * 0.4 + c.margin * 0.5

        features: list[AlignmentFeature] = []
        for i in range(c.n_pins):
            angle = 2 * np.pi * i / c.n_pins
            pos = center + offset * (np.cos(angle) * u + np.sin(angle) * v)

            # Pin geometry
            pin_mesh = None
            hole_mesh = None
            try:
                pin_tm = _make_cylinder(
                    pos, direction,
                    radius=c.pin_diameter / 2.0,
                    height=c.pin_height,
                )
                pin_mesh = MeshData.from_trimesh(pin_tm)
                hole_tm = _make_cylinder(
                    pos, direction,
                    radius=(c.pin_diameter + c.pin_tolerance) / 2.0,
                    height=c.pin_height + 1.0,
                )
                hole_mesh = MeshData.from_trimesh(hole_tm)
            except Exception:
                pass

            features.append(AlignmentFeature(
                position=pos, feature_type="pin",
                diameter=c.pin_diameter, height=c.pin_height,
                mesh=pin_mesh,
            ))
            features.append(AlignmentFeature(
                position=pos, feature_type="hole",
                diameter=c.pin_diameter + c.pin_tolerance,
                height=c.pin_height + 1.0,
                mesh=hole_mesh,
            ))
        return features

    # ═══════════════ Boolean Hole Cutting ═══════════════════════

    def _cut_holes_in_shells(
        self,
        shells: list[MoldShell],
        pour_hole: HoleFeature | None,
        vent_holes: list[HoleFeature],
        direction: np.ndarray,
    ) -> list[MoldShell]:
        """Boolean-subtract pour/vent hole cylinders from shell meshes.

        Cylinder height is adaptive: spans only the individual shell's extent
        along the direction axis (wall_thickness + margin), NOT the full mold.
        This prevents holes from overshooting through to the other side.
        """
        c = self.config
        up = np.asarray(direction, dtype=np.float64)
        up = up / (np.linalg.norm(up) + 1e-12)

        hole_specs: list[tuple[np.ndarray, float, str]] = []
        if pour_hole:
            hole_specs.append((pour_hole.position, pour_hole.diameter / 2.0, "pour"))
        for vh in vent_holes:
            hole_specs.append((vh.position, vh.diameter / 2.0, "vent"))
        if not hole_specs:
            return shells

        updated: list[MoldShell] = []
        for sh in shells:
            tm_shell = sh.mesh.to_trimesh()
            sh_bounds = tm_shell.bounds
            sh_dir = np.asarray(sh.direction, dtype=np.float64)
            sh_dir = sh_dir / (np.linalg.norm(sh_dir) + 1e-12)

            # Per-shell height: only the extent of THIS shell along direction
            shell_heights = tm_shell.vertices @ up
            shell_h_range = float(np.ptp(shell_heights))
            cyl_height = min(
                shell_h_range + 2.0,
                (c.wall_thickness + c.margin) * 3.0,
            )
            cyl_height = max(cyl_height, c.wall_thickness * 2.0)

            n_cut = 0
            for pos, radius, htype in hole_specs:
                # Only cut into the shell that the hole is closest to
                hole_h = float(pos @ up)
                shell_center_h = float(tm_shell.centroid @ up)

                # Skip if the hole is on the opposite side of the parting plane
                if np.dot(sh_dir, up) > 0 and hole_h < shell_center_h - shell_h_range:
                    continue
                if np.dot(sh_dir, up) < 0 and hole_h > shell_center_h + shell_h_range:
                    continue

                # Center the cylinder at the hole position, oriented along direction
                cyl = _make_cylinder(pos, up, radius=radius, height=cyl_height)

                cyl_min = cyl.bounds[0]
                cyl_max = cyl.bounds[1]
                if np.any(cyl_max < sh_bounds[0] - 1) or np.any(cyl_min > sh_bounds[1] + 1):
                    continue

                result = self._robust_boolean_subtract(tm_shell, cyl)
                if result is not None and len(result.faces) > 4:
                    tm_shell = result
                    n_cut += 1
                else:
                    logger.warning(
                        "Boolean %s hole cut FAILED on shell %d (pos=%s r=%.1f)",
                        htype, sh.shell_id, pos.round(1).tolist(), radius,
                    )
            if n_cut > 0:
                logger.info("Cut %d holes in shell %d", n_cut, sh.shell_id)
                tm_shell = _repair_mesh(tm_shell)

            updated.append(MoldShell(
                shell_id=sh.shell_id,
                mesh=MeshData.from_trimesh(tm_shell),
                direction=sh.direction,
                volume=float(tm_shell.volume) if tm_shell.is_watertight else sh.volume,
                surface_area=float(tm_shell.area),
                is_printable=sh.is_printable,
                min_draft_angle=sh.min_draft_angle,
            ))

        return updated

    # ═══════════════ Draft Angle Check ══════════════════════════

    @staticmethod
    def _check_draft_angle(
        mesh_data: MeshData, direction: np.ndarray,
    ) -> float:
        """Compute min draft angle of mold-wall faces w.r.t. direction."""
        tm = mesh_data.to_trimesh()
        normals = np.asarray(tm.face_normals, dtype=np.float64)
        d = np.asarray(direction, dtype=np.float64)
        d = d / (np.linalg.norm(d) + 1e-12)

        # Side faces: nearly perpendicular to direction
        dot = normals @ d
        side_mask = np.abs(dot) < 0.3
        if not np.any(side_mask):
            return 90.0

        side_dot = np.abs(dot[side_mask])
        draft_angles = np.degrees(np.arcsin(np.clip(side_dot, 0, 1)))
        return float(np.min(draft_angles))

    # ═══════════════ Pour / Vent position (legacy compat) ══════

    def _compute_pour_hole_position(
        self, tm_model: trimesh.Trimesh, direction: np.ndarray,
    ) -> np.ndarray:
        """Legacy interface — delegates to _compute_pour_gate."""
        hole = self._compute_pour_gate(tm_model, tm_model, direction)
        return hole.position

    def _compute_vent_positions(
        self, tm_model: trimesh.Trimesh, direction: np.ndarray,
    ) -> list[np.ndarray]:
        """Legacy interface — delegates to _compute_vent_holes."""
        holes = self._compute_vent_holes(tm_model, direction)
        return [h.position for h in holes]

    # ═══════════════ Pillar Hole Cutting ══════════════════════════

    def cut_pillar_holes(
        self, shells: list["MoldShell"], pillar_positions: list[dict],
    ) -> list["MoldShell"]:
        """Boolean-subtract cylindrical holes through mold shells for support pillars.

        Each pillar_positions entry: { mold_hole_center, direction, diameter }
        """
        if not pillar_positions:
            return shells

        c = self.config
        hole_cyls: list[trimesh.Trimesh] = []

        for p in pillar_positions:
            center = np.asarray(p["mold_hole_center"], dtype=np.float64)
            direction = np.asarray(p["direction"], dtype=np.float64)
            direction /= np.linalg.norm(direction) + 1e-12
            diameter = float(p.get("diameter", 2.0))
            tolerance = 0.3

            cyl = _make_cylinder(
                center, direction,
                radius=(diameter / 2.0) + tolerance,
                height=(c.wall_thickness + c.margin) * 3,
            )
            hole_cyls.append(cyl)

        updated: list[MoldShell] = []
        for sh in shells:
            tm_shell = sh.mesh.to_trimesh()
            cut_count = 0
            for hole_cyl in hole_cyls:
                try:
                    result = self._robust_boolean_subtract(tm_shell, hole_cyl)
                    if result is not None and len(result.faces) > 4:
                        tm_shell = result
                        cut_count += 1
                except Exception:
                    pass
            if cut_count > 0:
                tm_shell = _repair_mesh(tm_shell)
                sh.mesh = MeshData.from_trimesh(tm_shell)
                logger.info("Cut %d pillar holes in shell %d", cut_count, sh.shell_id)
            updated.append(sh)

        return updated
