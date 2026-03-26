"""nTopology-inspired analysis API routes.

Provides thickness, curvature, draft, symmetry, overhang analysis and
advanced mesh operations (smooth, remesh, thicken, offset).  Each endpoint
wraps the corresponding `moldgen.core.analysis` or `moldgen.core.mesh_editor`
function, runs it on the background thread pool, and returns structured JSON.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_mesh(model_id: str):
    """Retrieve a loaded MeshData or raise 404."""
    from moldgen.api.routes.models import _loaded_meshes
    if model_id not in _loaded_meshes:
        raise HTTPException(404, f"Model {model_id} not found — upload first")
    return _loaded_meshes[model_id]


# ── Request schemas ───────────────────────────────────────────────────

class ThicknessRequest(BaseModel):
    n_rays: int = Field(6, ge=1, le=32, description="Number of inward rays per vertex")
    max_distance: float = Field(50.0, gt=0, description="Max ray travel distance (mm)")
    thin_threshold: float = Field(1.0, gt=0, description="Thin-wall warning threshold (mm)")


class DraftRequest(BaseModel):
    pull_direction: list[float] | None = Field(None, description="[x,y,z] — default +Z")
    critical_angle: float = Field(3.0, ge=0, le=90, description="Critical draft angle (deg)")


class OverhangRequest(BaseModel):
    build_direction: list[float] | None = Field(None, description="[x,y,z] — default +Z")
    critical_angle: float = Field(45.0, ge=0, le=90, description="Overhang threshold (deg)")


class SmoothRequest(BaseModel):
    method: str = Field("laplacian", description="laplacian | taubin | humphrey")
    iterations: int = Field(3, ge=1, le=50, description="Smoothing iterations")
    lamb: float = Field(0.5, ge=0.01, le=1.0)
    mu: float = Field(-0.53, le=0)
    alpha: float = Field(0.1, ge=0, le=1.0)
    beta: float = Field(0.5, ge=0, le=1.0)


class RemeshRequest(BaseModel):
    target_edge_length: float | None = Field(None, gt=0, description="Target edge length (mm)")


class ThickenRequest(BaseModel):
    thickness: float = Field(2.0, gt=0, le=50, description="Shell thickness (mm)")
    direction: str = Field("both", description="outward | inward | both")


class OffsetRequest(BaseModel):
    distance: float = Field(1.0, description="Offset distance (mm), +outward, −inward")


# ── Analysis endpoints ────────────────────────────────────────────────

@router.post("/{model_id}/thickness")
async def analyze_thickness(model_id: str, req: ThicknessRequest | None = None):
    """Multi-ray wall thickness analysis per vertex."""
    mesh = _get_mesh(model_id)
    req = req or ThicknessRequest()
    try:
        from moldgen.core.analysis import compute_thickness
        result = await asyncio.to_thread(
            compute_thickness, mesh, req.n_rays, req.max_distance, req.thin_threshold,
        )
    except Exception as exc:
        logger.error("Thickness analysis failed for %s: %s", model_id, exc, exc_info=True)
        raise HTTPException(500, f"Thickness analysis failed: {exc}") from exc
    return {"model_id": model_id, "thickness": result.to_dict()}


@router.post("/{model_id}/curvature")
async def analyze_curvature(model_id: str):
    """Discrete Gaussian + mean curvature per vertex."""
    mesh = _get_mesh(model_id)
    try:
        from moldgen.core.analysis import compute_curvature
        result = await asyncio.to_thread(compute_curvature, mesh)
    except Exception as exc:
        logger.error("Curvature analysis failed for %s: %s", model_id, exc, exc_info=True)
        raise HTTPException(500, f"Curvature analysis failed: {exc}") from exc
    return {"model_id": model_id, "curvature": result.to_dict()}


@router.post("/{model_id}/draft")
async def analyze_draft(model_id: str, req: DraftRequest | None = None):
    """Per-face draft angle relative to pull direction."""
    mesh = _get_mesh(model_id)
    req = req or DraftRequest()
    try:
        from moldgen.core.analysis import compute_draft_analysis
        result = await asyncio.to_thread(
            compute_draft_analysis, mesh, req.pull_direction, req.critical_angle,
        )
    except Exception as exc:
        logger.error("Draft analysis failed for %s: %s", model_id, exc, exc_info=True)
        raise HTTPException(500, f"Draft analysis failed: {exc}") from exc
    return {"model_id": model_id, "draft": result.to_dict()}


@router.post("/{model_id}/symmetry")
async def analyze_symmetry(model_id: str):
    """Axis-plane symmetry estimation with PCA."""
    mesh = _get_mesh(model_id)
    try:
        from moldgen.core.analysis import compute_symmetry
        result = await asyncio.to_thread(compute_symmetry, mesh)
    except Exception as exc:
        logger.error("Symmetry analysis failed for %s: %s", model_id, exc, exc_info=True)
        raise HTTPException(500, f"Symmetry analysis failed: {exc}") from exc
    return {"model_id": model_id, "symmetry": result.to_dict()}


@router.post("/{model_id}/overhang")
async def analyze_overhang(model_id: str, req: OverhangRequest | None = None):
    """3D-printing overhang detection per face."""
    mesh = _get_mesh(model_id)
    req = req or OverhangRequest()
    try:
        from moldgen.core.analysis import compute_overhang
        result = await asyncio.to_thread(
            compute_overhang, mesh, req.build_direction, req.critical_angle,
        )
    except Exception as exc:
        logger.error("Overhang analysis failed for %s: %s", model_id, exc, exc_info=True)
        raise HTTPException(500, f"Overhang analysis failed: {exc}") from exc
    return {"model_id": model_id, "overhang": result.to_dict()}


# ── Mesh operation endpoints ──────────────────────────────────────────

@router.post("/{model_id}/smooth")
async def smooth_mesh(model_id: str, req: SmoothRequest):
    """Apply smoothing (Laplacian / Taubin / HC)."""
    from moldgen.api.routes.models import _loaded_meshes, _editor
    mesh = _get_mesh(model_id)
    try:
        if req.method == "taubin":
            result = await asyncio.to_thread(
                _editor.smooth_taubin, mesh, req.iterations, req.lamb, req.mu,
            )
        elif req.method == "humphrey":
            result = await asyncio.to_thread(
                _editor.smooth_humphrey, mesh, req.iterations, req.alpha, req.beta,
            )
        else:
            result = await asyncio.to_thread(
                _editor.smooth_laplacian, mesh, req.iterations, req.lamb,
            )
    except Exception as exc:
        logger.error("Smoothing (%s) failed for %s: %s", req.method, model_id, exc, exc_info=True)
        raise HTTPException(500, f"Smoothing failed: {exc}") from exc
    _loaded_meshes[model_id] = result
    logger.info("Smoothed %s with %s ×%d", model_id, req.method, req.iterations)
    return {"model_id": model_id, "method": req.method, "mesh_info": result.info()}


@router.post("/{model_id}/remesh")
async def remesh(model_id: str, req: RemeshRequest | None = None):
    """Isotropic remeshing via subdivide-decimate cycle."""
    from moldgen.api.routes.models import _loaded_meshes, _editor
    mesh = _get_mesh(model_id)
    req = req or RemeshRequest()
    try:
        result = await asyncio.to_thread(
            _editor.remesh_isotropic, mesh, req.target_edge_length,
        )
    except Exception as exc:
        logger.error("Remesh failed for %s: %s", model_id, exc, exc_info=True)
        raise HTTPException(500, f"Remesh failed: {exc}") from exc
    _loaded_meshes[model_id] = result
    logger.info("Remeshed %s → %d faces", model_id, result.face_count)
    return {"model_id": model_id, "mesh_info": result.info()}


@router.post("/{model_id}/thicken")
async def thicken_mesh(model_id: str, req: ThickenRequest):
    """Thicken a surface mesh into a solid."""
    from moldgen.api.routes.models import _loaded_meshes, _editor
    mesh = _get_mesh(model_id)
    if req.direction not in ("outward", "inward", "both"):
        raise HTTPException(400, f"Invalid direction '{req.direction}' — use outward|inward|both")
    try:
        result = await asyncio.to_thread(
            _editor.thicken, mesh, req.thickness, req.direction,
        )
    except Exception as exc:
        logger.error("Thicken failed for %s: %s", model_id, exc, exc_info=True)
        raise HTTPException(500, f"Thicken failed: {exc}") from exc
    _loaded_meshes[model_id] = result
    return {"model_id": model_id, "mesh_info": result.info()}


@router.post("/{model_id}/offset")
async def offset_mesh(model_id: str, req: OffsetRequest):
    """Offset surface along vertex normals."""
    from moldgen.api.routes.models import _loaded_meshes, _editor
    mesh = _get_mesh(model_id)
    try:
        result = await asyncio.to_thread(
            _editor.offset_surface, mesh, req.distance,
        )
    except Exception as exc:
        logger.error("Offset failed for %s: %s", model_id, exc, exc_info=True)
        raise HTTPException(500, f"Offset failed: {exc}") from exc
    _loaded_meshes[model_id] = result
    return {"model_id": model_id, "mesh_info": result.info()}
