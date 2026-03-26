"""Triply Periodic Minimal Surface (TPMS) implicit field library.

Provides mathematically precise TPMS evaluation for lattice/hole pattern
generation on support plates.  All surface equations follow the canonical
forms from nTopology / differential geometry literature.

Each TPMS function maps (x, y, z) → ℝ where the zero iso-surface f=0
defines the minimal surface.  For 2-D plate patterns we evaluate at a
fixed z-slice and use the field topology (extrema, zero-crossings) to
place holes.

References
----------
- nTopology TPMS equations: support.ntop.com/hc/en-us/articles/360053267814
- Al-Ketan & Abu Al-Rub, "Multifunctional mechanical metamaterials based
  on TPMS architectured cellular solids", Adv. Eng. Mater. 21(10), 2019.
- Schoen, A.H. "Infinite periodic minimal surfaces without
  self-intersections", NASA Technical Note D-5541, 1970.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy import ndimage

logger = logging.getLogger(__name__)

# ── TPMS implicit functions ──────────────────────────────────────────
# All take (x, y, z) as *scaled* coordinates (already multiplied by
# 2π / cell_size outside), so the period is 2π in each axis.


def _gyroid(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Schoen Gyroid:  sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x)"""
    return np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x)


def _schwarz_p(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Schwarz Primitive:  cos(x) + cos(y) + cos(z)"""
    return np.cos(x) + np.cos(y) + np.cos(z)


def _schwarz_d(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Schwarz Diamond:
    sin(x)sin(y)sin(z) + sin(x)cos(y)cos(z)
    + cos(x)sin(y)cos(z) + cos(x)cos(y)sin(z)
    """
    sx, sy, sz = np.sin(x), np.sin(y), np.sin(z)
    cx, cy, cz = np.cos(x), np.cos(y), np.cos(z)
    return sx * sy * sz + sx * cy * cz + cx * sy * cz + cx * cy * sz


def _neovius(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Neovius:  3(cos(x) + cos(y) + cos(z)) + 4·cos(x)cos(y)cos(z)"""
    cx, cy, cz = np.cos(x), np.cos(y), np.cos(z)
    return 3.0 * (cx + cy + cz) + 4.0 * cx * cy * cz


def _lidinoid(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Lidinoid:
    sin(2x)cos(y)sin(z) + sin(2y)cos(z)sin(x) + sin(2z)cos(x)sin(y)
    - cos(2x)cos(2y) - cos(2y)cos(2z) - cos(2z)cos(2x) + 0.3
    """
    return (
        np.sin(2 * x) * np.cos(y) * np.sin(z)
        + np.sin(2 * y) * np.cos(z) * np.sin(x)
        + np.sin(2 * z) * np.cos(x) * np.sin(y)
        - np.cos(2 * x) * np.cos(2 * y)
        - np.cos(2 * y) * np.cos(2 * z)
        - np.cos(2 * z) * np.cos(2 * x)
        + 0.3
    )


def _iwp(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Schoen IWP (I-WP):
    2(cos(x)cos(y) + cos(y)cos(z) + cos(z)cos(x))
    - (cos(2x) + cos(2y) + cos(2z))
    """
    cx, cy, cz = np.cos(x), np.cos(y), np.cos(z)
    return 2.0 * (cx * cy + cy * cz + cz * cx) - (np.cos(2 * x) + np.cos(2 * y) + np.cos(2 * z))


def _frd(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Fischer-Koch S / FRD:
    4·cos(x)cos(y)cos(z) - (cos(2x)cos(2y) + cos(2y)cos(2z) + cos(2z)cos(2x))
    """
    return (
        4.0 * np.cos(x) * np.cos(y) * np.cos(z)
        - (np.cos(2 * x) * np.cos(2 * y) + np.cos(2 * y) * np.cos(2 * z) + np.cos(2 * z) * np.cos(2 * x))
    )


# ── Registry ─────────────────────────────────────────────────────────

TPMSFunction = Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]

TPMS_REGISTRY: dict[str, TPMSFunction] = {
    "gyroid": _gyroid,
    "schwarz_p": _schwarz_p,
    "schwarz_d": _schwarz_d,
    "neovius": _neovius,
    "lidinoid": _lidinoid,
    "iwp": _iwp,
    "frd": _frd,
}


# ── 2D field evaluation ──────────────────────────────────────────────

@dataclass
class TPMSFieldResult:
    """Result of evaluating a TPMS on a 2D grid at a fixed z-slice."""
    field: np.ndarray          # (ny, nx) raw field values
    us: np.ndarray             # (nx,) u-coordinates
    vs: np.ndarray             # (ny,) v-coordinates
    cell_size: float
    z_slice: float
    name: str


def evaluate_field_2d(
    name: str,
    half_span: float,
    cell_size: float,
    z_slice: float = 0.0,
    resolution: int = 200,
    margin: float = 0.0,
) -> TPMSFieldResult:
    """Evaluate a TPMS implicit field on a 2D (u, v) grid at fixed z.

    Parameters
    ----------
    name : str
        TPMS name (key in TPMS_REGISTRY).
    half_span : float
        The grid spans [-half_span+margin, half_span-margin].
    cell_size : float
        The spatial period of one TPMS unit cell (mm).
    z_slice : float
        Fixed z-coordinate for the 2D slice.
    resolution : int
        Number of grid points along each axis.
    margin : float
        Inset from the half_span boundary.

    Returns
    -------
    TPMSFieldResult with the evaluated field grid.
    """
    fn = TPMS_REGISTRY.get(name, _gyroid)
    lo = -half_span + margin
    hi = half_span - margin
    us = np.linspace(lo, hi, resolution)
    vs = np.linspace(lo, hi, resolution)
    uu, vv = np.meshgrid(us, vs, indexing="xy")

    omega = 2.0 * np.pi / cell_size
    xx = omega * uu
    yy = omega * vv
    zz = omega * z_slice * np.ones_like(uu)

    field = fn(xx, yy, zz)
    return TPMSFieldResult(field=field, us=us, vs=vs,
                           cell_size=cell_size, z_slice=z_slice, name=name)


# ── Hole centre extraction ───────────────────────────────────────────

@dataclass
class HoleCentre:
    """A single hole described in the plate's (u, v) coordinate system."""
    u: float
    v: float
    radius: float
    field_value: float    # raw TPMS value at this point (for diagnostics)


def extract_hole_centres(
    result: TPMSFieldResult,
    base_radius: float,
    min_spacing: float | None = None,
    max_holes: int = 300,
    adaptive_radius: bool = True,
) -> list[HoleCentre]:
    """Extract hole centres from local extrema of a TPMS field.

    The TPMS zero iso-surface f=0 defines the "walls".  Regions of large
    |f| are far from walls and make ideal hole locations.  We detect
    local maxima of |f| (both positive peaks and negative valleys) and
    place holes at those positions.

    Parameters
    ----------
    result : TPMSFieldResult
        The 2D field to analyse.
    base_radius : float
        The nominal hole radius (mm).
    min_spacing : float | None
        Minimum centre-to-centre distance.  Defaults to 2.2 × base_radius.
    adaptive_radius : bool
        If True, modulate each hole's radius by how far its field value is
        from zero, producing naturally variable-size holes.
    max_holes : int
        Upper bound on returned holes.

    Returns
    -------
    List of HoleCentre sorted by descending |field_value|.
    """
    field = result.field
    us, vs = result.us, result.vs
    abs_field = np.abs(field)

    if min_spacing is None:
        min_spacing = base_radius * 2.2

    # Detect local maxima of |f| using a morphological dilation footprint
    # sized to enforce minimum spacing.
    du = us[1] - us[0] if len(us) > 1 else 1.0
    fp_size = max(3, int(min_spacing / du) | 1)  # ensure odd
    if fp_size % 2 == 0:
        fp_size += 1
    footprint = np.ones((fp_size, fp_size))

    local_max = ndimage.maximum_filter(abs_field, footprint=footprint)
    peaks = (abs_field == local_max) & (abs_field > 0.15 * abs_field.max())

    peak_coords = np.argwhere(peaks)
    if len(peak_coords) == 0:
        logger.warning("TPMS %s: no peaks found, falling back to grid sampling", result.name)
        return _fallback_grid(us, vs, base_radius, max_holes)

    # Compute per-peak field magnitude for ranking and radius modulation
    magnitudes = abs_field[peak_coords[:, 0], peak_coords[:, 1]]
    order = np.argsort(-magnitudes)
    peak_coords = peak_coords[order]
    magnitudes = magnitudes[order]

    # Greedy selection respecting min_spacing
    field_max = magnitudes[0] if len(magnitudes) > 0 else 1.0
    selected: list[HoleCentre] = []
    used_uv: list[tuple[float, float]] = []

    for idx in range(len(peak_coords)):
        if len(selected) >= max_holes:
            break
        row, col = int(peak_coords[idx, 0]), int(peak_coords[idx, 1])
        u_val = float(us[col])
        v_val = float(vs[row])
        mag = float(magnitudes[idx])

        # Check distance to already-selected holes
        too_close = False
        for eu, ev in used_uv:
            if (u_val - eu) ** 2 + (v_val - ev) ** 2 < min_spacing ** 2:
                too_close = True
                break
        if too_close:
            continue

        if adaptive_radius:
            # Radius proportional to field magnitude: stronger field → larger hole
            ratio = mag / max(field_max, 1e-9)
            r = base_radius * (0.5 + 0.5 * ratio)  # range: [0.5r, r]
        else:
            r = base_radius

        selected.append(HoleCentre(u=u_val, v=v_val, radius=r, field_value=float(field[row, col])))
        used_uv.append((u_val, v_val))

    logger.info("TPMS %s: extracted %d hole centres (res=%d, fp=%d)",
                result.name, len(selected), len(us), fp_size)
    return selected


def _fallback_grid(
    us: np.ndarray, vs: np.ndarray, radius: float, max_holes: int,
) -> list[HoleCentre]:
    """Simple hex grid fallback when TPMS extraction fails."""
    spacing = radius * 3.0
    lo_u, hi_u = float(us[0]), float(us[-1])
    lo_v, hi_v = float(vs[0]), float(vs[-1])
    out: list[HoleCentre] = []
    row = 0
    v = lo_v
    while v < hi_v and len(out) < max_holes:
        u = lo_u + (spacing * 0.5 if row % 2 else 0.0)
        while u < hi_u and len(out) < max_holes:
            out.append(HoleCentre(u=u, v=v, radius=radius, field_value=0.0))
            u += spacing
        v += spacing * math.sqrt(3) / 2
        row += 1
    return out


# ── Field-driven radius modulation ───────────────────────────────────

def apply_field_modulation(
    holes: list[HoleCentre],
    half_span: float,
    field_type: str = "edge",
    min_factor: float = 0.4,
    max_factor: float = 1.0,
) -> list[HoleCentre]:
    """Modulate hole *radius* (not just removal) based on a spatial field.

    Unlike a binary keep/remove strategy, this smoothly varies hole size
    across the plate, producing nTopology-style graded perforations.

    Parameters
    ----------
    field_type : str
        "edge"       — smaller holes near the centre, larger near edges
        "center"     — larger holes at centre, smaller near edges
        "radial"     — radius increases radially from centre
        "stress"     — proxy stress field (larger holes in low-stress zones)
        "uniform"    — all holes shrunk to min_factor × base_radius
    min_factor, max_factor : float
        Multiplier range for the hole radius.

    Returns
    -------
    New list with modulated radii (holes below 30% of original are removed).
    """
    result: list[HoleCentre] = []
    for h in holes:
        t = _field_value(h.u, h.v, half_span, field_type)
        factor = min_factor + (max_factor - min_factor) * t
        new_r = h.radius * factor
        if new_r >= h.radius * 0.3:
            result.append(HoleCentre(u=h.u, v=h.v, radius=new_r, field_value=h.field_value))
    return result


def _field_value(u: float, v: float, half_span: float, field_type: str) -> float:
    """Compute a [0, 1] field value at (u, v) for the given field type."""
    hs = max(half_span, 1e-6)
    if field_type == "edge":
        edge_dist = min(abs(u + hs), abs(u - hs), abs(v + hs), abs(v - hs))
        return 1.0 - edge_dist / hs  # 1 near edge, 0 at centre
    elif field_type == "center":
        edge_dist = min(abs(u + hs), abs(u - hs), abs(v + hs), abs(v - hs))
        return edge_dist / hs  # 0 near edge, 1 at centre
    elif field_type == "radial":
        r = math.sqrt(u * u + v * v)
        return min(r / (hs * 1.414), 1.0)
    elif field_type == "stress":
        # Proxy: higher stress at edges & corners → smaller holes there
        edge_dist = min(abs(u + hs), abs(u - hs), abs(v + hs), abs(v - hs))
        return edge_dist / hs
    else:  # "uniform"
        return 0.0


# ── Convenience: one-call layout ─────────────────────────────────────

def generate_tpms_holes(
    tpms_name: str,
    half_span: float,
    hole_diameter: float,
    cell_size: float | None = None,
    z_slice: float = 0.0,
    resolution: int | None = None,
    adaptive_radius: bool = True,
    max_holes: int = 300,
    density_field: str | None = None,
    density_min: float = 0.4,
    density_max: float = 1.0,
) -> list[tuple[float, float, float]]:
    """High-level API: generate hole centres using a TPMS pattern.

    Returns list of (u, v, radius) tuples compatible with the existing
    InsertGenerator._carve_holes interface.
    """
    radius = hole_diameter / 2.0
    if cell_size is None:
        cell_size = hole_diameter * 3.0

    margin = radius * 1.5
    if resolution is None:
        span = 2.0 * (half_span - margin)
        resolution = max(60, min(400, int(span / (cell_size * 0.08))))

    field_result = evaluate_field_2d(
        name=tpms_name,
        half_span=half_span,
        cell_size=cell_size,
        z_slice=z_slice,
        resolution=resolution,
        margin=margin,
    )

    holes = extract_hole_centres(
        field_result,
        base_radius=radius,
        min_spacing=radius * 2.2,
        max_holes=max_holes,
        adaptive_radius=adaptive_radius,
    )

    if density_field and density_field != "none":
        holes = apply_field_modulation(
            holes, half_span,
            field_type=density_field,
            min_factor=density_min,
            max_factor=density_max,
        )

    return [(h.u, h.v, h.radius) for h in holes]
