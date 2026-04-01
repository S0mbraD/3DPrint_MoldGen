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


# ═══════════════════════ Data Classes ═══════════════════════════════════

@dataclass
class MoldConfig:
    wall_thickness: float = 4.0
    clearance: float = 0.3
    shell_type: str = "box"       # "box" | "conformal"
    margin: float = 10.0
    fillet_radius: float = 1.0
    # Parting style: "flat" | "dovetail" | "zigzag" | "step" | "tongue_groove"
    parting_style: str = "flat"
    parting_depth: float = 3.0       # depth of interlock features (mm)
    parting_pitch: float = 10.0      # spacing between interlock features (mm)
    # Flanges with screw holes
    add_flanges: bool = False
    flange_width: float = 12.0       # flange extension width (mm)
    flange_thickness: float = 4.0    # flange plate thickness (mm)
    screw_hole_diameter: float = 4.0 # M4 screws
    n_flanges: int = 4               # number of flange tabs
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
    # Mold input mesh: subdivide model before shell / voxel ops for smoother cavities
    min_input_faces: int = 12000


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
class MoldResult:
    shells: list[MoldShell]
    cavity_volume: float = 0.0
    alignment_features: list[AlignmentFeature] = field(default_factory=list)
    pour_hole_position: np.ndarray | None = None
    pour_hole: HoleFeature | None = None
    vent_positions: list[np.ndarray] = field(default_factory=list)
    vent_holes: list[HoleFeature] = field(default_factory=list)
    flanges: list[FlangeFeature] = field(default_factory=list)
    parting_style: str = "flat"

    def to_dict(self) -> dict:
        return {
            "n_shells": len(self.shells),
            "shells": [s.to_dict() for s in self.shells],
            "cavity_volume": round(self.cavity_volume, 2),
            "parting_style": self.parting_style,
            "alignment_features": [
                f.to_dict() for f in self.alignment_features
            ],
            "flanges": [f.to_dict() for f in self.flanges],
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
    tm: trimesh.Trimesh, min_faces: int = 4000,
) -> trimesh.Trimesh:
    """Subdivide a mesh until it has at least *min_faces* faces.

    Low-poly models produce low-resolution mold shells. Subdivision
    increases surface resolution so that mold walls, cavities, and
    parting features have enough geometry for clean boolean operations.
    """
    iters = 0
    while len(tm.faces) < min_faces and iters < 4:
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
) -> trimesh.Trimesh | None:
    # Prefer capped trimesh slice when shapely is available (clean parting cap).
    for cap in (True, False):
        try:
            r = mesh.slice_plane(origin, normal, cap=cap)
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
        tm_model = _repair_mesh(tm_model)

        # Subdivide low-poly models so mold shells have enough resolution
        tm_model = _ensure_min_faces(tm_model, min_faces=self.config.min_input_faces)

        logger.info(
            "Repaired: %d faces, watertight=%s",
            len(tm_model.faces), tm_model.is_watertight,
        )

        center = np.asarray(tm_model.centroid, dtype=np.float64)

        # ── Strategy 1: Boolean subtraction (outer box - cavity) ──
        shells = None
        cavity = self._create_cavity(tm_model)
        outer = self._create_outer_shell(cavity)
        solid = self._robust_boolean_subtract(outer, cavity)
        # Inverted cavity / bad CSG can yield only the inner skin (~n_cav faces) with no box.
        if (
            solid is not None
            and len(solid.faces) > 10
            and not _shell_is_conformal(self.config.shell_type)
            and len(solid.faces) < len(cavity.faces) + 6
        ):
            logger.warning(
                "Boolean result suspicious (faces=%d, cavity=%d); using fallbacks",
                len(solid.faces), len(cavity.faces),
            )
            solid = None
        if solid is not None and len(solid.faces) > 10:
            shells = self._split_solid_to_shells(solid, center, direction)
            if shells and len(shells) >= 2:
                logger.info("Boolean mold: %d shells", len(shells))
            else:
                shells = None

        # ── Strategy 2: Voxel-based construction ──
        if not shells:
            logger.info("Boolean failed, trying voxel construction")
            shells = self._build_shells_voxel(tm_model, center, direction)
            if shells and len(shells) >= 2:
                logger.info("Voxel mold: %d shells", len(shells))

        # ── Strategy 3: Direct concatenation (last resort) ──
        if not shells or len(shells) < 2:
            logger.warning("Voxel failed, using direct concatenation fallback")
            shells = self._build_direct_shells(cavity, center, direction)
            logger.info("Direct construction: %d shells", len(shells))

        # ── Repair all shells ──
        for sh in shells:
            tm_sh = sh.mesh.to_trimesh()
            tm_sh = _repair_mesh(tm_sh)
            dn = np.asarray(sh.direction, dtype=np.float64)
            dn = dn / (np.linalg.norm(dn) + 1e-12)
            tm_sh = _seal_parting_plane_gaps(tm_sh, center, dn)
            tm_sh = _repair_mesh(tm_sh)
            sh.mesh = MeshData.from_trimesh(tm_sh)

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

        # ── Flanges with screw holes ──
        flanges: list[FlangeFeature] = []
        if self.config.add_flanges:
            shells, flanges = self._generate_flanges(
                shells, tm_model, direction, center,
            )
            logger.info("Added %d flanges", len(flanges))

        elapsed = time.perf_counter() - t0
        logger.info(
            "Mold complete: %d shells, cavity=%.0f mm3, "
            "pour=%s, vents=%d, pins=%d, flanges=%d, style=%s, %.2fs",
            len(shells), cavity_vol,
            "yes" if pour_hole else "no",
            len(vent_holes),
            len([a for a in alignment if a.feature_type == "pin"]),
            len(flanges),
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
            flanges=flanges,
            parting_style=self.config.parting_style,
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
        tm_model = _repair_mesh(tm_model)
        tm_model = _ensure_min_faces(tm_model, min_faces=self.config.min_input_faces)
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

    def _try_boolean_mold(
        self, cavity: trimesh.Trimesh,
        center: np.ndarray, direction: np.ndarray,
    ) -> list[MoldShell] | None:
        try:
            import manifold3d
        except ImportError:
            return None

        outer = self._create_outer_shell(cavity)
        try:
            def _m(tm):
                return manifold3d.Manifold(manifold3d.Mesh(
                    vert_properties=np.asarray(tm.vertices, dtype=np.float32),
                    tri_verts=np.asarray(tm.faces, dtype=np.uint32),
                ))
            diff = _m(outer) - _m(cavity)
            out = diff.to_mesh()
            solid = trimesh.Trimesh(
                vertices=np.asarray(out.vert_properties[:, :3]),
                faces=np.asarray(out.tri_verts), process=True,
            )
        except Exception as exc:
            logger.warning("Manifold3D failed: %s", exc)
            return None

        if len(solid.faces) < 10:
            return None

        upper = _safe_slice(solid, center, direction)
        lower = _safe_slice(solid, center, -direction)
        shells = []
        for i, (half, d) in enumerate([
            (upper, direction.copy()), (lower, -direction),
        ]):
            if half is None or len(half.faces) == 0:
                continue
            shells.append(MoldShell(
                shell_id=i, mesh=MeshData.from_trimesh(half),
                direction=d,
                volume=(
                    float(half.volume) if half.is_watertight else 0.0
                ),
                surface_area=float(half.area),
            ))
        return shells if len(shells) >= 2 else None

    def _build_direct_shells(
        self, cavity: trimesh.Trimesh,
        center: np.ndarray, direction: np.ndarray,
    ) -> list[MoldShell]:
        outer = self._create_outer_shell(cavity)
        upper_box = _safe_slice(outer, center, direction)
        lower_box = _safe_slice(outer, center, -direction)

        if upper_box is None or lower_box is None:
            dots = (outer.triangles_center - center) @ direction
            upper_box = _extract_submesh(outer, dots >= 0)
            lower_box = _extract_submesh(outer, dots < 0)

        cavity_inv = cavity.copy()
        cavity_inv.invert()
        upper_cav = _safe_slice(cavity_inv, center, direction)
        lower_cav = _safe_slice(cavity_inv, center, -direction)
        if upper_cav is None or len(upper_cav.faces) < 4:
            cav_dots = (cavity_inv.triangles_center - center) @ direction
            upper_cav = _extract_submesh(cavity_inv, cav_dots >= 0)
        if lower_cav is None or len(lower_cav.faces) < 4:
            cav_dots = (cavity_inv.triangles_center - center) @ direction
            lower_cav = _extract_submesh(cavity_inv, cav_dots < 0)

        shells: list[MoldShell] = []
        for i, (box_h, cav_h, d) in enumerate([
            (upper_box, upper_cav, direction.copy()),
            (lower_box, lower_cav, -direction),
        ]):
            parts = [box_h]
            if len(cav_h.faces) > 0:
                parts.append(cav_h)
            try:
                combined = trimesh.util.concatenate(parts)
            except Exception:
                combined = box_h
            sn = np.asarray(d, dtype=np.float64)
            sn = sn / (np.linalg.norm(sn) + 1e-12)
            combined = _seal_parting_plane_gaps(combined, center, sn)
            shells.append(MoldShell(
                shell_id=i, mesh=MeshData.from_trimesh(combined),
                direction=np.asarray(d, dtype=np.float64),
                volume=(
                    float(combined.volume) if combined.is_watertight else 0.0
                ),
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
        """Split a mold solid into upper/lower halves, with optional interlock profile."""
        if self.config.parting_style != "flat":
            upper, lower = self._apply_parting_interlock(solid, center, direction)
            shells: list[MoldShell] = []
            for i, (half, d) in enumerate([
                (upper, direction.copy()), (lower, -direction.copy()),
            ]):
                if half is not None and len(half.faces) >= 4:
                    sn = np.asarray(d, dtype=np.float64)
                    sn = sn / (np.linalg.norm(sn) + 1e-12)
                    half = _seal_parting_plane_gaps(half, center, sn)
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
            sn = np.asarray(normal, dtype=np.float64)
            sn = sn / (np.linalg.norm(sn) + 1e-12)
            half = _safe_slice(solid, center, normal)
            if half is not None and len(half.faces) >= 4:
                half = _seal_parting_plane_gaps(half, center, sn)
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
        """Voxel-based mold construction: voxelize model, dilate, subtract."""
        c = self.config
        extents = tm_model.extents
        max_ext = float(np.max(extents))
        if max_ext < 1e-6:
            return None

        # Uniform pitch from longest extent only; use finer cells than max_ext/80 so
        # marching-cubes cavity surfaces are less visibly stair-stepped in the viewport.
        target_pitch = min(
            0.55,
            max_ext / 160.0,
            max(0.18, float(c.wall_thickness) / 4.0),
        )
        resolution = int(np.ceil(max_ext / max(target_pitch, max_ext / 320.0)))
        resolution = int(np.clip(resolution, 96, 320))
        pitch = max_ext / resolution
        logger.info("Voxel mold: pitch=%.3f mm, res=%d", pitch, resolution)

        # Step 1: Voxelize model
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

        # Step 2: Dilate to create clearance
        clearance_px = max(1, int(np.ceil(c.clearance / pitch)))
        cavity_matrix = ndimage.binary_dilation(
            model_matrix, iterations=clearance_px,
        )

        # Step 3: Build outer shell
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

        # Step 4: Marching cubes to extract surface
        try:
            from skimage.measure import marching_cubes
            verts_vox, faces_mc, normals_mc, _ = marching_cubes(
                mold_matrix.astype(np.float32), level=0.5,
            )
        except ImportError:
            logger.warning("scikit-image unavailable for marching cubes")
            return None
        except Exception as e:
            logger.warning("Marching cubes failed: %s", e)
            return None

        world_origin = vox_origin - wall_px * pitch
        verts_world = verts_vox * pitch + world_origin
        mold_mesh = trimesh.Trimesh(
            vertices=verts_world, faces=faces_mc,
            vertex_normals=normals_mc, process=True,
        )
        trimesh.repair.fix_normals(mold_mesh)
        logger.info("Voxel mold mesh: %d faces", len(mold_mesh.faces))

        # Step 5: Simplify if too many faces
        target = min(100_000, MOLD_MAX_FACES)
        if len(mold_mesh.faces) > target:
            try:
                mold_mesh = mold_mesh.simplify_quadric_decimation(target)
            except Exception:
                pass

        # Step 6: Split into halves
        return self._split_solid_to_shells(mold_mesh, center, direction)

    # ═══════════════ Cavity / Outer Shell ═══════════════════════

    def _create_cavity(self, tm_model: trimesh.Trimesh) -> trimesh.Trimesh:
        """Vertex-normal offset with Laplacian pre-smooth to reduce
        self-intersections on concave geometry."""
        clearance = self.config.clearance
        if clearance <= 0:
            return tm_model.copy()
        try:
            smooth_n = _laplacian_smooth_vertex_normals(tm_model)
            new_verts = tm_model.vertices + smooth_n * clearance
            return trimesh.Trimesh(
                vertices=new_verts, faces=tm_model.faces.copy(),
                process=True,
            )
        except Exception:
            logger.warning("Vertex offset failed, using original")
            return tm_model.copy()

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
        """Boolean-subtract pour/vent hole cylinders from shell meshes."""
        c = self.config
        hole_cyls: list[trimesh.Trimesh] = []

        if pour_hole:
            cyl = _make_cylinder(
                pour_hole.position, direction,
                radius=pour_hole.diameter / 2.0,
                height=(c.wall_thickness + c.margin) * 4,
            )
            hole_cyls.append(cyl)

        for vh in vent_holes:
            cyl = _make_cylinder(
                vh.position, direction,
                radius=vh.diameter / 2.0,
                height=(c.wall_thickness + c.margin) * 4,
            )
            hole_cyls.append(cyl)

        if not hole_cyls:
            return shells

        updated: list[MoldShell] = []
        for sh in shells:
            tm_shell = sh.mesh.to_trimesh()
            cut_ok = False

            for hole_cyl in hole_cyls:
                result = self._robust_boolean_subtract(tm_shell, hole_cyl)
                if result is not None and len(result.faces) > 4:
                    tm_shell = result
                    cut_ok = True

            if cut_ok:
                logger.info("Cut holes in shell %d", sh.shell_id)
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
