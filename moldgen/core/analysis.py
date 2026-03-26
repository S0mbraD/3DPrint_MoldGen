"""nTopology-inspired mesh analysis: thickness, curvature, draft, symmetry.

Provides per-vertex or per-face scalar fields that can be visualized as
color overlays in the 3D viewport, driving downstream decisions like
lattice density grading or support placement.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


# ── Thickness Analysis ────────────────────────────────────────────────

@dataclass
class ThicknessResult:
    per_vertex: np.ndarray          # (N,) wall thickness per vertex in mm
    min_thickness: float
    max_thickness: float
    mean_thickness: float
    std_thickness: float
    thin_count: int                 # vertices below threshold
    histogram_bins: list[float] = field(default_factory=list)
    histogram_counts: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "min": round(float(self.min_thickness), 4),
            "max": round(float(self.max_thickness), 4),
            "mean": round(float(self.mean_thickness), 4),
            "std": round(float(self.std_thickness), 4),
            "thin_count": int(self.thin_count),
            "n_vertices": len(self.per_vertex),
            "histogram_bins": [round(b, 3) for b in self.histogram_bins],
            "histogram_counts": [int(c) for c in self.histogram_counts],
            "values": [round(float(v), 4) for v in self.per_vertex.tolist()],
        }


def compute_thickness(
    mesh: MeshData,
    n_rays: int = 6,
    max_distance: float = 50.0,
    thin_threshold: float = 1.0,
) -> ThicknessResult:
    """Multi-ray inward thickness estimation per vertex.

    For each vertex, cast *n_rays* inward rays (along negated normal and
    jittered directions) and take the median hit distance as the local
    wall thickness.
    """
    tm = mesh.to_trimesh()
    verts = np.asarray(tm.vertices, dtype=np.float64)
    normals = np.asarray(tm.vertex_normals, dtype=np.float64)
    n = len(verts)

    thickness = np.full(n, max_distance, dtype=np.float64)

    rng = np.random.default_rng(42)

    for ray_i in range(n_rays):
        if ray_i == 0:
            dirs = -normals
        else:
            jitter = rng.normal(0, 0.3, size=normals.shape)
            dirs = -normals + jitter
            norms = np.linalg.norm(dirs, axis=1, keepdims=True)
            norms = np.clip(norms, 1e-8, None)
            dirs = dirs / norms

        origins = verts + dirs * 0.01

        try:
            locs, ray_idx, _ = tm.ray.intersects_location(
                origins, dirs, multiple_hits=False,
            )
            if len(locs) > 0:
                dists = np.linalg.norm(locs - origins[ray_idx], axis=1)
                valid = dists < max_distance
                hit_idx = ray_idx[valid]
                hit_dist = dists[valid]
                thickness[hit_idx] = np.minimum(thickness[hit_idx], hit_dist)
        except Exception as exc:
            logger.debug("Ray batch %d failed: %s", ray_i, exc)

    thickness = np.clip(thickness, 0.0, max_distance)
    finite = thickness[thickness < max_distance]

    if len(finite) == 0:
        finite = thickness

    hist_counts, hist_edges = np.histogram(finite, bins=20)

    return ThicknessResult(
        per_vertex=thickness,
        min_thickness=float(np.min(finite)),
        max_thickness=float(np.max(finite)),
        mean_thickness=float(np.mean(finite)),
        std_thickness=float(np.std(finite)),
        thin_count=int(np.sum(finite < thin_threshold)),
        histogram_bins=hist_edges.tolist(),
        histogram_counts=hist_counts.tolist(),
    )


# ── Curvature Analysis ────────────────────────────────────────────────

@dataclass
class CurvatureResult:
    gaussian: np.ndarray      # (N,) per-vertex Gaussian curvature
    mean_curvature: np.ndarray  # (N,) per-vertex mean curvature
    max_curvature: np.ndarray   # (N,) max of abs(k1, k2)
    min_val: float
    max_val: float
    mean_val: float

    def to_dict(self) -> dict:
        return {
            "n_vertices": len(self.gaussian),
            "gaussian_min": round(float(np.min(self.gaussian)), 6),
            "gaussian_max": round(float(np.max(self.gaussian)), 6),
            "mean_curvature_min": round(float(np.min(self.mean_curvature)), 6),
            "mean_curvature_max": round(float(np.max(self.mean_curvature)), 6),
            "max_curvature_mean": round(float(self.mean_val), 6),
            "gaussian": [round(float(v), 6) for v in self.gaussian.tolist()],
            "mean": [round(float(v), 6) for v in self.mean_curvature.tolist()],
            "max_abs": [round(float(v), 6) for v in self.max_curvature.tolist()],
        }


def compute_curvature(mesh: MeshData) -> CurvatureResult:
    """Discrete curvature via angle-defect (Gaussian) and cotangent (mean)."""
    tm = mesh.to_trimesh()
    verts = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.asarray(tm.faces, dtype=np.int64)
    n_v = len(verts)

    gaussian = np.full(n_v, 2 * math.pi, dtype=np.float64)
    mean_curv = np.zeros(n_v, dtype=np.float64)
    area_sum = np.zeros(n_v, dtype=np.float64)

    for face in faces:
        i, j, k = face
        vi, vj, vk = verts[i], verts[j], verts[k]

        eij = vj - vi
        eik = vk - vi
        ejk = vk - vj
        eji = vi - vj
        eki = vi - vk
        ekj = vj - vk

        def _angle(a: np.ndarray, b: np.ndarray) -> float:
            cos_a = np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12)
            return float(np.arccos(np.clip(cos_a, -1, 1)))

        ai = _angle(eij, eik)
        aj = _angle(eji, ejk)
        ak = _angle(eki, ekj)

        gaussian[i] -= ai
        gaussian[j] -= aj
        gaussian[k] -= ak

        face_area = 0.5 * np.linalg.norm(np.cross(eij, eik))
        a3 = face_area / 3.0
        area_sum[i] += a3
        area_sum[j] += a3
        area_sum[k] += a3

    area_sum = np.clip(area_sum, 1e-12, None)
    gaussian /= area_sum

    try:
        import trimesh.curvature
        mean_curv = trimesh.curvature.discrete_mean_curvature_measure(tm, verts, radius=0)
    except Exception as exc:
        logger.debug("trimesh.curvature unavailable, using Gaussian fallback: %s", exc)
        mean_curv = gaussian * 0.5

    max_curv = np.maximum(np.abs(gaussian), np.abs(mean_curv))

    return CurvatureResult(
        gaussian=gaussian,
        mean_curvature=mean_curv,
        max_curvature=max_curv,
        min_val=float(np.min(max_curv)),
        max_val=float(np.max(max_curv)),
        mean_val=float(np.mean(max_curv)),
    )


# ── Per-Face Draft Analysis ───────────────────────────────────────────

@dataclass
class DraftAnalysisResult:
    per_face_angle: np.ndarray   # (F,) draft angle in degrees per face
    min_draft: float
    max_draft: float
    mean_draft: float
    undercut_fraction: float     # fraction of faces with draft < 0
    critical_fraction: float     # fraction with 0 < draft < threshold
    histogram_bins: list[float] = field(default_factory=list)
    histogram_counts: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_faces": len(self.per_face_angle),
            "min_draft": round(float(self.min_draft), 2),
            "max_draft": round(float(self.max_draft), 2),
            "mean_draft": round(float(self.mean_draft), 2),
            "undercut_fraction": round(float(self.undercut_fraction), 4),
            "critical_fraction": round(float(self.critical_fraction), 4),
            "histogram_bins": [round(b, 2) for b in self.histogram_bins],
            "histogram_counts": [int(c) for c in self.histogram_counts],
            "per_face": [round(float(v), 2) for v in self.per_face_angle.tolist()],
        }


def compute_draft_analysis(
    mesh: MeshData,
    pull_direction: list[float] | np.ndarray | None = None,
    critical_angle: float = 3.0,
) -> DraftAnalysisResult:
    """Per-face draft angle relative to *pull_direction* (default +Z)."""
    tm = mesh.to_trimesh()
    normals = np.asarray(tm.face_normals, dtype=np.float64)

    if pull_direction is None:
        pull = np.array([0.0, 0.0, 1.0])
    else:
        pull = np.asarray(pull_direction, dtype=np.float64)
        pull = pull / max(np.linalg.norm(pull), 1e-12)

    cos_angles = np.dot(normals, pull)
    cos_angles = np.clip(cos_angles, -1, 1)
    draft_angles = 90.0 - np.degrees(np.arccos(np.abs(cos_angles)))

    undercut_mask = cos_angles < 0
    draft_angles[undercut_mask] = -draft_angles[undercut_mask]

    hist_c, hist_e = np.histogram(draft_angles, bins=36, range=(-90, 90))

    return DraftAnalysisResult(
        per_face_angle=draft_angles,
        min_draft=float(np.min(draft_angles)),
        max_draft=float(np.max(draft_angles)),
        mean_draft=float(np.mean(draft_angles)),
        undercut_fraction=float(np.mean(draft_angles < 0)),
        critical_fraction=float(np.mean((draft_angles >= 0) & (draft_angles < critical_angle))),
        histogram_bins=hist_e.tolist(),
        histogram_counts=hist_c.tolist(),
    )


# ── Symmetry Analysis ─────────────────────────────────────────────────

@dataclass
class SymmetryResult:
    x_symmetry: float    # 0..1 — how symmetric about YZ plane
    y_symmetry: float
    z_symmetry: float
    best_plane: str       # "x", "y", or "z"
    best_score: float
    principal_axes: list[list[float]]   # 3×3 PCA axes

    def to_dict(self) -> dict:
        return {
            "x_symmetry": round(self.x_symmetry, 4),
            "y_symmetry": round(self.y_symmetry, 4),
            "z_symmetry": round(self.z_symmetry, 4),
            "best_plane": self.best_plane,
            "best_score": round(self.best_score, 4),
            "principal_axes": [[round(v, 6) for v in ax] for ax in self.principal_axes],
        }


def compute_symmetry(mesh: MeshData) -> SymmetryResult:
    """Estimate symmetry about each axis plane using Hausdorff-like metric."""
    tm = mesh.to_trimesh()
    verts = np.asarray(tm.vertices, dtype=np.float64)
    center = verts.mean(axis=0)
    verts_c = verts - center

    from scipy.spatial import cKDTree

    tree = cKDTree(verts_c)

    scores = {}
    for ax_i, ax_name in enumerate(["x", "y", "z"]):
        reflected = verts_c.copy()
        reflected[:, ax_i] = -reflected[:, ax_i]
        dists, _ = tree.query(reflected)
        extent = np.ptp(verts_c[:, ax_i])
        if extent < 1e-6:
            scores[ax_name] = 1.0
        else:
            norm_dist = dists / extent
            scores[ax_name] = float(max(0.0, 1.0 - np.mean(norm_dist) * 4))

    best = max(scores, key=scores.get)  # type: ignore[arg-type]

    try:
        _, _, vh = np.linalg.svd(verts_c, full_matrices=False)
        pca = vh[:3].tolist()
    except Exception as exc:
        logger.debug("SVD failed for PCA, using identity axes: %s", exc)
        pca = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

    return SymmetryResult(
        x_symmetry=scores["x"],
        y_symmetry=scores["y"],
        z_symmetry=scores["z"],
        best_plane=best,
        best_score=scores[best],
        principal_axes=pca,
    )


# ── Overhang Analysis ─────────────────────────────────────────────────

@dataclass
class OverhangResult:
    per_face_overhang: np.ndarray    # (F,) boolean — True if overhang
    overhang_fraction: float
    overhang_area: float              # mm² of overhang
    total_area: float
    critical_angle: float

    def to_dict(self) -> dict:
        return {
            "n_faces": len(self.per_face_overhang),
            "overhang_fraction": round(float(self.overhang_fraction), 4),
            "overhang_area_mm2": round(float(self.overhang_area), 2),
            "total_area_mm2": round(float(self.total_area), 2),
            "critical_angle_deg": round(float(self.critical_angle), 1),
            "per_face": self.per_face_overhang.astype(int).tolist(),
        }


def compute_overhang(
    mesh: MeshData,
    build_direction: list[float] | None = None,
    critical_angle: float = 45.0,
) -> OverhangResult:
    """Per-face overhang detection for 3D printing."""
    tm = mesh.to_trimesh()
    normals = np.asarray(tm.face_normals, dtype=np.float64)
    areas = np.asarray(tm.area_faces, dtype=np.float64)

    if build_direction is None:
        build = np.array([0.0, 0.0, 1.0])
    else:
        build = np.asarray(build_direction, dtype=np.float64)
        build = build / max(np.linalg.norm(build), 1e-12)

    cos_angles = np.dot(normals, build)
    face_angles = np.degrees(np.arccos(np.clip(np.abs(cos_angles), 0, 1)))

    is_downward = cos_angles < 0
    is_overhang = is_downward & (face_angles > (90 - critical_angle))

    return OverhangResult(
        per_face_overhang=is_overhang,
        overhang_fraction=float(np.mean(is_overhang)),
        overhang_area=float(np.sum(areas[is_overhang])),
        total_area=float(np.sum(areas)),
        critical_angle=critical_angle,
    )


# ── Part Volume / BOM Estimation ──────────────────────────────────────

@dataclass
class BOMEntry:
    component: str
    volume_mm3: float
    surface_area_mm2: float
    face_count: int
    estimated_weight_g: float
    estimated_print_time_min: float

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "volume_mm3": round(self.volume_mm3, 1),
            "surface_area_mm2": round(self.surface_area_mm2, 1),
            "face_count": self.face_count,
            "estimated_weight_g": round(self.estimated_weight_g, 2),
            "estimated_print_time_min": round(self.estimated_print_time_min, 1),
        }


def compute_bom(
    components: dict[str, MeshData],
    density_g_per_cm3: float = 1.24,
    print_speed_mm3_per_min: float = 50.0,
) -> list[BOMEntry]:
    """Bill of Materials for all mesh components."""
    entries = []
    for name, mesh in components.items():
        tm = mesh.to_trimesh()
        vol = abs(float(tm.volume)) if tm.is_watertight else float(tm.area) * 0.5
        sa = float(tm.area)
        weight = vol * density_g_per_cm3 / 1000.0
        time_min = vol / max(print_speed_mm3_per_min, 0.01)
        entries.append(BOMEntry(
            component=name,
            volume_mm3=vol,
            surface_area_mm2=sa,
            face_count=len(tm.faces),
            estimated_weight_g=weight,
            estimated_print_time_min=time_min,
        ))
    return entries


# ── Mesh Quality Analysis ─────────────────────────────────────────────

@dataclass
class MeshQualityResult:
    """Comprehensive mesh quality metrics — nTopology DfAM-style."""
    # Per-face metrics
    face_aspect_ratios: np.ndarray       # (F,) longest_edge / shortest_edge
    face_areas: np.ndarray               # (F,) triangle area in mm²
    face_angles_min: np.ndarray          # (F,) minimum interior angle (degrees)
    face_angles_max: np.ndarray          # (F,) maximum interior angle (degrees)
    # Per-edge metrics
    edge_lengths: np.ndarray             # (E,) all unique edge lengths
    # Aggregate statistics
    n_vertices: int
    n_faces: int
    n_edges: int
    aspect_ratio_mean: float
    aspect_ratio_max: float
    skinny_triangle_count: int           # faces with min_angle < 15°
    skinny_fraction: float
    degenerate_face_count: int           # faces with area < 1e-10
    edge_length_min: float
    edge_length_max: float
    edge_length_mean: float
    edge_length_std: float
    area_min: float
    area_max: float
    area_mean: float
    is_watertight: bool
    is_manifold: bool
    euler_characteristic: int
    genus: int
    # Volume and surface
    volume: float
    surface_area: float
    compactness: float                   # 36π V² / A³ (1.0 for sphere)
    # Histograms
    aspect_ratio_histogram: list[dict]
    edge_length_histogram: list[dict]
    angle_histogram: list[dict]


def compute_mesh_quality(mesh: MeshData) -> MeshQualityResult:
    """Compute comprehensive mesh quality metrics.

    Analyses triangle shape quality, edge length uniformity, manifold
    properties, and topological invariants.
    """
    tm = mesh.to_trimesh() if hasattr(mesh, "to_trimesh") else mesh

    verts = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.asarray(tm.faces, dtype=np.int64)
    nf = len(faces)

    # ── Triangle metrics ──────────────────────────────────────────
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    e01 = v1 - v0
    e12 = v2 - v1
    e20 = v0 - v2

    len01 = np.linalg.norm(e01, axis=1)
    len12 = np.linalg.norm(e12, axis=1)
    len20 = np.linalg.norm(e20, axis=1)

    edge_lens = np.column_stack([len01, len12, len20])
    longest = edge_lens.max(axis=1)
    shortest = np.maximum(edge_lens.min(axis=1), 1e-12)
    aspect_ratios = longest / shortest

    # Interior angles via dot product
    def _angle(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        cos_val = np.sum(a * b, axis=1) / (
            np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-12)
        )
        return np.degrees(np.arccos(np.clip(cos_val, -1, 1)))

    ang0 = _angle(e01, -e20)   # angle at v0
    ang1 = _angle(-e01, e12)   # angle at v1
    ang2 = _angle(-e12, e20)   # angle at v2

    all_angles = np.column_stack([ang0, ang1, ang2])
    min_angles = all_angles.min(axis=1)
    max_angles = all_angles.max(axis=1)

    # Face areas
    cross = np.cross(e01, -e20)
    face_areas = 0.5 * np.linalg.norm(cross, axis=1)
    degenerate_count = int(np.sum(face_areas < 1e-10))

    # ── Edge metrics ──────────────────────────────────────────────
    all_edges = np.vstack([
        np.sort(faces[:, [0, 1]], axis=1),
        np.sort(faces[:, [1, 2]], axis=1),
        np.sort(faces[:, [0, 2]], axis=1),
    ])
    unique_edges = np.unique(all_edges, axis=0)
    edge_vecs = verts[unique_edges[:, 1]] - verts[unique_edges[:, 0]]
    edge_lengths = np.linalg.norm(edge_vecs, axis=1)

    # ── Topology ──────────────────────────────────────────────────
    n_v = len(verts)
    n_e = len(unique_edges)
    n_f = nf
    euler = n_v - n_e + n_f
    genus = max(0, (2 - euler) // 2)

    is_watertight = bool(getattr(tm, "is_watertight", False))
    is_manifold = True
    try:
        from collections import Counter
        edge_counts = Counter(map(tuple, all_edges.tolist()))
        non_manifold = sum(1 for c in edge_counts.values() if c > 2)
        is_manifold = non_manifold == 0
    except Exception:
        pass

    volume = float(tm.volume) if is_watertight else 0.0
    surface_area = float(tm.area)
    compactness = (36 * math.pi * volume**2) / max(surface_area**3, 1e-12) if volume > 0 else 0.0

    skinny_count = int(np.sum(min_angles < 15.0))

    # ── Histograms ────────────────────────────────────────────────
    def _make_hist(arr: np.ndarray, n_bins: int = 15) -> list[dict]:
        if len(arr) == 0:
            return []
        bins = np.linspace(float(arr.min()), float(arr.max()), n_bins + 1)
        counts, edges = np.histogram(arr, bins=bins)
        return [
            {"bin_start": float(edges[i]), "bin_end": float(edges[i+1]), "count": int(counts[i])}
            for i in range(len(counts))
        ]

    return MeshQualityResult(
        face_aspect_ratios=aspect_ratios,
        face_areas=face_areas,
        face_angles_min=min_angles,
        face_angles_max=max_angles,
        edge_lengths=edge_lengths,
        n_vertices=n_v,
        n_faces=n_f,
        n_edges=n_e,
        aspect_ratio_mean=float(aspect_ratios.mean()),
        aspect_ratio_max=float(aspect_ratios.max()),
        skinny_triangle_count=skinny_count,
        skinny_fraction=skinny_count / max(n_f, 1),
        degenerate_face_count=degenerate_count,
        edge_length_min=float(edge_lengths.min()) if len(edge_lengths) > 0 else 0.0,
        edge_length_max=float(edge_lengths.max()) if len(edge_lengths) > 0 else 0.0,
        edge_length_mean=float(edge_lengths.mean()) if len(edge_lengths) > 0 else 0.0,
        edge_length_std=float(edge_lengths.std()) if len(edge_lengths) > 0 else 0.0,
        area_min=float(face_areas.min()),
        area_max=float(face_areas.max()),
        area_mean=float(face_areas.mean()),
        is_watertight=is_watertight,
        is_manifold=is_manifold,
        euler_characteristic=euler,
        genus=genus,
        volume=volume,
        surface_area=surface_area,
        compactness=compactness,
        aspect_ratio_histogram=_make_hist(aspect_ratios),
        edge_length_histogram=_make_hist(edge_lengths),
        angle_histogram=_make_hist(min_angles),
    )
