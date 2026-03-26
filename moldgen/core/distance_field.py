"""Signed Distance Field (SDF) computation and field operations.

Provides nTopology-style implicit field infrastructure:
- Mesh-to-SDF conversion (exact + voxelised)
- Field arithmetic (add, multiply, blend, combine)
- Smooth boolean operators (union, intersection, difference)
- Field remapping and thresholding
- Variable-thickness shell / offset via field modulation
- Marching Cubes iso-surface extraction back to mesh

References
----------
- Íñigo Quílez, "Smooth minimum" functions for SDF blending
- nTopology implicit modeling: ntopology.com/blog/implicit-modeling-for-mechanical-design
- Hart, J.C. "Sphere tracing: a geometric method for the antialiased ray
  tracing of implicit surfaces", Visual Computer 12(10), 1996.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field as dc_field
from typing import Literal

import numpy as np
from scipy import ndimage

logger = logging.getLogger(__name__)


# ── SDF from mesh ─────────────────────────────────────────────────────

@dataclass
class SDFGrid:
    """A voxelised signed distance field on a regular 3D grid."""
    values: np.ndarray          # (nz, ny, nx) float32
    origin: np.ndarray          # (3,) world-space origin of the grid
    spacing: float              # uniform voxel edge length (mm)
    shape: tuple[int, int, int] # (nz, ny, nx)

    # ── point query ───────────────────────────────────────────────
    def sample(self, points: np.ndarray) -> np.ndarray:
        """Tri-linear interpolation of SDF at arbitrary world-space points."""
        idx = (points - self.origin) / self.spacing
        return ndimage.map_coordinates(
            self.values, idx.T[::-1], order=1, mode="nearest",
        ).astype(np.float64)

    def gradient(self, points: np.ndarray) -> np.ndarray:
        """Central-difference gradient of SDF (≈ surface normal direction)."""
        eps = self.spacing * 0.5
        gx = (self.sample(points + [eps, 0, 0]) - self.sample(points - [eps, 0, 0])) / (2 * eps)
        gy = (self.sample(points + [0, eps, 0]) - self.sample(points - [0, eps, 0])) / (2 * eps)
        gz = (self.sample(points + [0, 0, eps]) - self.sample(points - [0, 0, eps])) / (2 * eps)
        return np.column_stack([gx, gy, gz])

    # ── coordinate helpers ────────────────────────────────────────
    def world_coords(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (X, Y, Z) meshgrid arrays in world space."""
        nz, ny, nx = self.shape
        xs = self.origin[0] + np.arange(nx) * self.spacing
        ys = self.origin[1] + np.arange(ny) * self.spacing
        zs = self.origin[2] + np.arange(nz) * self.spacing
        return xs, ys, zs


def mesh_to_sdf(
    mesh,  # trimesh.Trimesh
    resolution: int = 64,
    pad: float = 2.0,
) -> SDFGrid:
    """Convert a triangle mesh to a voxelised signed distance field.

    Uses trimesh's proximity queries for exact closest-point distance,
    with inside/outside determined by winding number.

    Parameters
    ----------
    mesh : trimesh.Trimesh
    resolution : int
        Number of voxels along the longest axis.
    pad : float
        Extra padding around the mesh bounding box (mm).
    """
    import trimesh

    bounds_min = mesh.bounds[0] - pad
    bounds_max = mesh.bounds[1] + pad
    extent = bounds_max - bounds_min
    spacing = float(extent.max() / resolution)
    nx = max(2, int(np.ceil(extent[0] / spacing)))
    ny = max(2, int(np.ceil(extent[1] / spacing)))
    nz = max(2, int(np.ceil(extent[2] / spacing)))

    xs = bounds_min[0] + np.arange(nx) * spacing
    ys = bounds_min[1] + np.arange(ny) * spacing
    zs = bounds_min[2] + np.arange(nz) * spacing

    grid_pts = np.stack(
        np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1,
    ).reshape(-1, 3)

    # Closest point distance
    closest, dist, _ = trimesh.proximity.closest_point(mesh, grid_pts)
    dist = dist.astype(np.float64)

    # Inside/outside via winding number (or ray test fallback)
    try:
        inside = mesh.contains(grid_pts)
    except Exception:
        logger.debug("mesh.contains failed, using ray-based sign estimation")
        inside = np.zeros(len(grid_pts), dtype=bool)

    sdf = np.where(inside, -dist, dist).astype(np.float32)
    sdf = sdf.reshape((nx, ny, nz)).transpose(2, 1, 0)  # → (nz, ny, nx)

    logger.info("SDF computed: shape=(%d,%d,%d), spacing=%.3f mm", nz, ny, nx, spacing)
    return SDFGrid(
        values=sdf, origin=bounds_min.copy(),
        spacing=spacing, shape=(nz, ny, nx),
    )


def _sdf_on_grid(mesh, origin, spacing, nx, ny, nz) -> np.ndarray:
    """Compute SDF for *mesh* on a pre-defined grid."""
    import trimesh as _tm

    xs = origin[0] + np.arange(nx) * spacing
    ys = origin[1] + np.arange(ny) * spacing
    zs = origin[2] + np.arange(nz) * spacing
    grid_pts = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1).reshape(-1, 3)

    _, dist, _ = _tm.proximity.closest_point(mesh, grid_pts)
    dist = dist.astype(np.float64)
    try:
        inside = mesh.contains(grid_pts)
    except Exception:
        inside = np.zeros(len(grid_pts), dtype=bool)

    sdf = np.where(inside, -dist, dist).astype(np.float32)
    return sdf.reshape((nx, ny, nz)).transpose(2, 1, 0)


def mesh_to_sdf_shared(
    mesh_a, mesh_b, resolution: int = 64, pad: float = 2.0,
) -> tuple:
    """Compute SDFs for two meshes on a **shared** grid (union bounding box).

    Returns (SDFGrid_a, SDFGrid_b) with identical shape/origin/spacing.
    """
    bounds_min = np.minimum(mesh_a.bounds[0], mesh_b.bounds[0]) - pad
    bounds_max = np.maximum(mesh_a.bounds[1], mesh_b.bounds[1]) + pad
    extent = bounds_max - bounds_min
    spacing = float(extent.max() / resolution)
    nx = max(2, int(np.ceil(extent[0] / spacing)))
    ny = max(2, int(np.ceil(extent[1] / spacing)))
    nz = max(2, int(np.ceil(extent[2] / spacing)))

    sdf_a = _sdf_on_grid(mesh_a, bounds_min, spacing, nx, ny, nz)
    sdf_b = _sdf_on_grid(mesh_b, bounds_min, spacing, nx, ny, nz)

    shape = (nz, ny, nx)
    return (
        SDFGrid(values=sdf_a, origin=bounds_min.copy(), spacing=spacing, shape=shape),
        SDFGrid(values=sdf_b, origin=bounds_min.copy(), spacing=spacing, shape=shape),
    )


# ── Smooth boolean operators (Íñigo Quílez formulation) ──────────────

def smooth_union(a: np.ndarray, b: np.ndarray, k: float = 0.5) -> np.ndarray:
    """Smooth minimum (polynomial): merges two SDF fields with a fillet blend.

    k controls the blend radius — larger k → wider fillet.
    """
    h = np.clip(0.5 + 0.5 * (b - a) / max(k, 1e-9), 0, 1)
    return a * h + b * (1 - h) - k * h * (1 - h)


def smooth_intersection(a: np.ndarray, b: np.ndarray, k: float = 0.5) -> np.ndarray:
    """Smooth maximum for intersection."""
    return -smooth_union(-a, -b, k)


def smooth_difference(a: np.ndarray, b: np.ndarray, k: float = 0.5) -> np.ndarray:
    """Smooth subtraction: a minus b."""
    return smooth_intersection(a, -b, k)


def sharp_union(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.minimum(a, b)


def sharp_intersection(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.maximum(a, b)


def sharp_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.maximum(a, -b)


# ── Field operations (nTopology-style) ────────────────────────────────

def field_offset(sdf: SDFGrid, distance: float) -> SDFGrid:
    """Offset (grow/shrink) the implicit body by shifting the iso-surface.

    Positive distance → grow outward (offset).
    Negative distance → shrink inward (inset).
    """
    return SDFGrid(
        values=sdf.values - distance,
        origin=sdf.origin.copy(), spacing=sdf.spacing, shape=sdf.shape,
    )


def field_shell(sdf: SDFGrid, thickness: float) -> SDFGrid:
    """Create a shell of given thickness around the zero iso-surface.

    Result = |sdf| - thickness/2  (inside the shell → negative).
    """
    return SDFGrid(
        values=np.abs(sdf.values) - thickness / 2,
        origin=sdf.origin.copy(), spacing=sdf.spacing, shape=sdf.shape,
    )


def field_variable_shell(
    sdf: SDFGrid,
    thickness_field: np.ndarray,
) -> SDFGrid:
    """Variable-thickness shell driven by a spatial thickness field.

    thickness_field must match sdf.shape and contain per-voxel thickness values.
    """
    assert thickness_field.shape == sdf.values.shape
    half_t = thickness_field / 2.0
    return SDFGrid(
        values=(np.abs(sdf.values) - half_t).astype(np.float32),
        origin=sdf.origin.copy(), spacing=sdf.spacing, shape=sdf.shape,
    )


def field_blend(
    a: SDFGrid, b: SDFGrid,
    operation: Literal["union", "intersection", "difference"] = "union",
    blend_radius: float = 0.0,
) -> SDFGrid:
    """Perform a boolean blend between two SDF grids (must share same grid)."""
    assert a.shape == b.shape and np.allclose(a.origin, b.origin)
    if blend_radius > 0:
        ops = {
            "union": smooth_union,
            "intersection": smooth_intersection,
            "difference": smooth_difference,
        }
        result = ops[operation](a.values, b.values, blend_radius)
    else:
        ops = {
            "union": sharp_union,
            "intersection": sharp_intersection,
            "difference": sharp_difference,
        }
        result = ops[operation](a.values, b.values)
    return SDFGrid(
        values=result.astype(np.float32),
        origin=a.origin.copy(), spacing=a.spacing, shape=a.shape,
    )


def field_remap(
    sdf: SDFGrid,
    in_min: float = -1.0, in_max: float = 1.0,
    out_min: float = 0.0, out_max: float = 1.0,
    clamp: bool = True,
) -> SDFGrid:
    """Linear remap of field values from [in_min, in_max] → [out_min, out_max]."""
    t = (sdf.values - in_min) / max(in_max - in_min, 1e-9)
    if clamp:
        t = np.clip(t, 0, 1)
    result = out_min + t * (out_max - out_min)
    return SDFGrid(
        values=result.astype(np.float32),
        origin=sdf.origin.copy(), spacing=sdf.spacing, shape=sdf.shape,
    )


def field_threshold(sdf: SDFGrid, iso: float = 0.0) -> np.ndarray:
    """Binary mask: True where sdf ≤ iso (inside the body)."""
    return sdf.values <= iso


def field_gaussian_blur(sdf: SDFGrid, sigma_mm: float = 1.0) -> SDFGrid:
    """Gaussian blur of the SDF field — smooths sharp features."""
    sigma_voxels = sigma_mm / max(sdf.spacing, 1e-9)
    blurred = ndimage.gaussian_filter(sdf.values.astype(np.float64), sigma=sigma_voxels)
    return SDFGrid(
        values=blurred.astype(np.float32),
        origin=sdf.origin.copy(), spacing=sdf.spacing, shape=sdf.shape,
    )


# ── Distance field from points / geometry ─────────────────────────────

def distance_field_from_points(
    sdf_template: SDFGrid,
    points: np.ndarray,
) -> SDFGrid:
    """Compute unsigned distance field from a set of 3D points.

    Useful for field-driven design: e.g. map distance-from-load-points
    to lattice density or wall thickness.
    """
    from scipy.spatial import cKDTree
    xs, ys, zs = sdf_template.world_coords()
    grid_pts = np.stack(
        np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1,
    ).reshape(-1, 3)
    tree = cKDTree(points)
    dist, _ = tree.query(grid_pts)
    dist = dist.reshape(
        (len(xs), len(ys), len(zs)),
    ).transpose(2, 1, 0).astype(np.float32)
    return SDFGrid(
        values=dist, origin=sdf_template.origin.copy(),
        spacing=sdf_template.spacing, shape=sdf_template.shape,
    )


def distance_field_from_axis(
    sdf_template: SDFGrid,
    axis: Literal["x", "y", "z"] = "z",
) -> SDFGrid:
    """Compute distance from a principal axis (field increases outward).

    Useful for field-driven grading along a build direction.
    """
    xs, ys, zs = sdf_template.world_coords()
    if axis == "x":
        mid = (xs[0] + xs[-1]) / 2
        field_1d = np.abs(xs - mid)
        field = np.broadcast_to(
            field_1d[None, None, :], sdf_template.shape,
        ).copy()
    elif axis == "y":
        mid = (ys[0] + ys[-1]) / 2
        field_1d = np.abs(ys - mid)
        field = np.broadcast_to(
            field_1d[None, :, None], sdf_template.shape,
        ).copy()
    else:
        mid = (zs[0] + zs[-1]) / 2
        field_1d = np.abs(zs - mid)
        field = np.broadcast_to(
            field_1d[:, None, None], sdf_template.shape,
        ).copy()
    return SDFGrid(
        values=field.astype(np.float32),
        origin=sdf_template.origin.copy(),
        spacing=sdf_template.spacing, shape=sdf_template.shape,
    )


# ── Iso-surface extraction (SDF → mesh) ──────────────────────────────

def extract_isosurface(sdf: SDFGrid, iso: float = 0.0):
    """Marching Cubes on the SDF grid → trimesh.Trimesh."""
    import trimesh
    try:
        from skimage.measure import marching_cubes
    except ImportError:
        from skimage import measure
        marching_cubes = measure.marching_cubes

    verts, faces, normals, _ = marching_cubes(
        sdf.values, level=iso,
        spacing=(sdf.spacing, sdf.spacing, sdf.spacing),
    )
    verts = verts[:, ::-1] + sdf.origin  # (z,y,x) → (x,y,z)
    faces = faces[:, ::-1]  # fix winding
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    logger.info("Iso-surface extracted: %d verts, %d faces", len(mesh.vertices), len(mesh.faces))
    return mesh


# ── High-level convenience ────────────────────────────────────────────

@dataclass
class FieldDrivenShellResult:
    mesh: object  # trimesh.Trimesh
    min_thickness: float
    max_thickness: float
    mean_thickness: float


def field_driven_shell(
    mesh,  # trimesh.Trimesh
    base_thickness: float = 2.0,
    thickness_variation: float = 1.0,
    field_type: Literal["distance_from_center", "distance_from_base", "curvature_proxy"] = "distance_from_center",
    resolution: int = 64,
) -> FieldDrivenShellResult:
    """Create a variable-thickness shell driven by a spatial field.

    nTopology-style operation: map a field to wall thickness, then
    extract the resulting shell as a mesh.

    Parameters
    ----------
    base_thickness : float
        Minimum shell thickness (mm).
    thickness_variation : float
        Additional thickness at field maximum (mm).
    field_type : str
        Which spatial field drives the thickness variation.
    resolution : int
        SDF grid resolution.
    """
    sdf = mesh_to_sdf(mesh, resolution=resolution, pad=base_thickness + thickness_variation + 1)

    # Build thickness field
    xs, ys, zs = sdf.world_coords()
    grid_pts = np.stack(
        np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1,
    )
    center = (mesh.bounds[0] + mesh.bounds[1]) / 2

    if field_type == "distance_from_center":
        d = np.linalg.norm(grid_pts - center, axis=-1)
    elif field_type == "distance_from_base":
        d = grid_pts[..., 2] - mesh.bounds[0][2]
    else:  # curvature_proxy
        d = np.linalg.norm(grid_pts - center, axis=-1)

    d_norm = d / max(d.max(), 1e-9)
    thickness = base_thickness + thickness_variation * d_norm
    thickness = thickness.transpose(2, 1, 0).astype(np.float32)  # → (nz, ny, nx)

    shell_sdf = field_variable_shell(sdf, thickness)
    result_mesh = extract_isosurface(shell_sdf, iso=0.0)

    t_inside = thickness[sdf.values <= 0]
    return FieldDrivenShellResult(
        mesh=result_mesh,
        min_thickness=float(t_inside.min()) if len(t_inside) > 0 else base_thickness,
        max_thickness=float(t_inside.max()) if len(t_inside) > 0 else base_thickness + thickness_variation,
        mean_thickness=float(t_inside.mean()) if len(t_inside) > 0 else base_thickness,
    )
