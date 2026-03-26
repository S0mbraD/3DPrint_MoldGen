"""Interference and Clearance Analysis between mesh pairs.

Provides nTopology-style part-to-part distance analysis:
- Minimum clearance computation
- Interference volume detection
- Clearance map (per-vertex)
- Assembly validation checks

References
----------
- nTopology implicit interference detection
- trimesh proximity module for closest-point queries
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ClearanceResult:
    """Result of clearance / interference analysis between two meshes."""
    min_clearance: float          # minimum distance (negative = interference)
    max_clearance: float
    mean_clearance: float
    interference_volume: float    # approx volume of overlapping region (mm³)
    interference_detected: bool
    # Per-vertex clearance on mesh_a
    per_vertex_clearance: np.ndarray  # (n_verts,) signed distance
    # Regions
    interference_faces_a: np.ndarray  # face indices on mesh_a that interfere
    interference_faces_b: np.ndarray  # face indices on mesh_b that interfere
    # Statistics
    clearance_histogram: list[dict]


def compute_clearance(
    mesh_a,  # trimesh.Trimesh
    mesh_b,  # trimesh.Trimesh
    sample_count: int = 5000,
) -> ClearanceResult:
    """Compute clearance / interference between two meshes.

    Positive clearance = gap between parts.
    Negative clearance = interference (overlap).

    Uses bidirectional closest-point queries for accuracy.
    """
    import trimesh

    # Sample points on mesh_a surface and query distance to mesh_b
    pts_a = mesh_a.vertices.copy()
    if len(pts_a) > sample_count:
        idx = np.random.default_rng(42).choice(len(pts_a), sample_count, replace=False)
        pts_a_sample = pts_a[idx]
    else:
        pts_a_sample = pts_a
        idx = np.arange(len(pts_a))

    # Closest point on mesh_b
    closest_b, dist_b, face_ids_b = trimesh.proximity.closest_point(mesh_b, pts_a_sample)

    # Determine sign: inside mesh_b → negative (interference)
    try:
        inside_b = mesh_b.contains(pts_a_sample)
    except Exception:
        # Fallback: use ray winding number or just assume outside
        inside_b = np.zeros(len(pts_a_sample), dtype=bool)

    signed_dist = np.where(inside_b, -dist_b, dist_b)

    # Bidirectional: also check mesh_b vertices inside mesh_a
    pts_b = mesh_b.vertices.copy()
    if len(pts_b) > sample_count:
        idx_b = np.random.default_rng(43).choice(len(pts_b), sample_count, replace=False)
        pts_b_sample = pts_b[idx_b]
    else:
        pts_b_sample = pts_b

    try:
        inside_a = mesh_a.contains(pts_b_sample)
    except Exception:
        inside_a = np.zeros(len(pts_b_sample), dtype=bool)

    closest_a, dist_a, face_ids_a = trimesh.proximity.closest_point(mesh_a, pts_b_sample)
    signed_dist_b = np.where(inside_a, -dist_a, dist_a)

    # Combine for overall statistics
    all_signed = np.concatenate([signed_dist, signed_dist_b])

    # Per-vertex clearance for full mesh_a
    _, full_dist, _ = trimesh.proximity.closest_point(mesh_b, pts_a)
    try:
        full_inside = mesh_b.contains(pts_a)
    except Exception:
        full_inside = np.zeros(len(pts_a), dtype=bool)
    per_vertex_clearance = np.where(full_inside, -full_dist, full_dist)

    # Interference detection
    interference_detected = bool(np.any(all_signed < 0))

    # Approximate interference volume using voxel counting
    interference_volume = 0.0
    if interference_detected:
        interference_volume = _estimate_interference_volume(mesh_a, mesh_b)

    # Identify interfering faces
    interfering_a = np.where(per_vertex_clearance < 0)[0]
    face_mask_a = np.any(np.isin(mesh_a.faces, interfering_a), axis=1)
    interference_faces_a = np.where(face_mask_a)[0]

    interfering_b_verts = np.where(inside_a)[0] if len(pts_b_sample) == len(pts_b) else np.array([], dtype=int)
    if len(interfering_b_verts) > 0:
        face_mask_b = np.any(np.isin(mesh_b.faces, interfering_b_verts), axis=1)
        interference_faces_b = np.where(face_mask_b)[0]
    else:
        interference_faces_b = np.array([], dtype=int)

    # Histogram
    bins = np.linspace(float(all_signed.min()), float(all_signed.max()), 20)
    counts, edges = np.histogram(all_signed, bins=bins)
    histogram = [
        {"bin_start": float(edges[i]), "bin_end": float(edges[i+1]), "count": int(counts[i])}
        for i in range(len(counts))
    ]

    return ClearanceResult(
        min_clearance=float(all_signed.min()),
        max_clearance=float(all_signed.max()),
        mean_clearance=float(all_signed.mean()),
        interference_volume=interference_volume,
        interference_detected=interference_detected,
        per_vertex_clearance=per_vertex_clearance,
        interference_faces_a=interference_faces_a,
        interference_faces_b=interference_faces_b,
        clearance_histogram=histogram,
    )


def _estimate_interference_volume(mesh_a, mesh_b, resolution: int = 32) -> float:
    """Estimate overlap volume using voxel counting."""
    try:
        import trimesh
        bounds_min = np.minimum(mesh_a.bounds[0], mesh_b.bounds[0])
        bounds_max = np.maximum(mesh_a.bounds[1], mesh_b.bounds[1])
        extent = bounds_max - bounds_min
        spacing = extent.max() / resolution
        n = np.maximum(1, np.ceil(extent / spacing)).astype(int)

        xs = bounds_min[0] + np.arange(n[0]) * spacing
        ys = bounds_min[1] + np.arange(n[1]) * spacing
        zs = bounds_min[2] + np.arange(n[2]) * spacing
        pts = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1).reshape(-1, 3)

        inside_a = mesh_a.contains(pts)
        inside_b = mesh_b.contains(pts)
        overlap = np.sum(inside_a & inside_b)
        return float(overlap * spacing**3)
    except Exception as exc:
        logger.debug("Interference volume estimation failed: %s", exc)
        return 0.0


# ── Assembly Validation ───────────────────────────────────────────────

@dataclass
class AssemblyCheckResult:
    """Result of assembly clearance validation."""
    all_clear: bool
    checks: list[dict]  # per-pair results
    total_interference_volume: float


def validate_assembly(
    parts: list[tuple[str, object]],  # [(name, trimesh.Trimesh), ...]
    min_clearance: float = 0.5,       # minimum required clearance (mm)
) -> AssemblyCheckResult:
    """Check all part pairs for interference or insufficient clearance.

    Parameters
    ----------
    parts : list of (name, mesh) tuples
    min_clearance : float
        Minimum acceptable clearance between any two parts.

    Returns
    -------
    AssemblyCheckResult with per-pair analysis.
    """
    checks: list[dict] = []
    all_clear = True
    total_interference = 0.0

    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            name_a, mesh_a = parts[i]
            name_b, mesh_b = parts[j]

            try:
                result = compute_clearance(mesh_a, mesh_b, sample_count=2000)
                status = "ok"
                if result.interference_detected:
                    status = "interference"
                    all_clear = False
                    total_interference += result.interference_volume
                elif result.min_clearance < min_clearance:
                    status = "tight"
                    all_clear = False

                checks.append({
                    "part_a": name_a,
                    "part_b": name_b,
                    "status": status,
                    "min_clearance": result.min_clearance,
                    "max_clearance": result.max_clearance,
                    "mean_clearance": result.mean_clearance,
                    "interference_volume": result.interference_volume,
                })
            except Exception as exc:
                logger.error("Assembly check %s vs %s failed: %s", name_a, name_b, exc)
                checks.append({
                    "part_a": name_a,
                    "part_b": name_b,
                    "status": "error",
                    "error": str(exc),
                })
                all_clear = False

    return AssemblyCheckResult(
        all_clear=all_clear,
        checks=checks,
        total_interference_volume=total_interference,
    )
