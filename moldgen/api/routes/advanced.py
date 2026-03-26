"""Advanced nTopology-style API routes.

Provides REST endpoints for:
- Mesh boolean operations (union, intersection, difference, smooth blend)
- Topology optimisation (2D/3D SIMP)
- 3D lattice generation (graph, TPMS volume, Voronoi foam)
- Interference / clearance analysis
- Comprehensive mesh quality metrics
- SDF / distance field operations
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_mesh(model_id: str):
    from moldgen.api.routes.models import _loaded_meshes
    mesh = _loaded_meshes.get(model_id)
    if not mesh:
        raise HTTPException(404, f"Model {model_id} not found")
    return mesh


# ══════════════════════════════════════════════════════════════════════
# Mesh Boolean Operations
# ══════════════════════════════════════════════════════════════════════

class BooleanRequest(BaseModel):
    model_a_id: str
    model_b_id: str
    operation: str = Field("union", description="union|intersection|difference")
    blend_radius: float = Field(0.0, ge=0, description="Smooth blend radius (mm). 0 = sharp.")


@router.post("/boolean")
async def mesh_boolean(req: BooleanRequest):
    """Perform boolean operation between two meshes.

    Supports sharp and smooth (fillet) blending via SDF when blend_radius > 0.
    """
    mesh_a = _get_mesh(req.model_a_id)
    mesh_b = _get_mesh(req.model_b_id)
    from moldgen.core.mesh_data import MeshData

    try:
        if req.blend_radius > 0:
            from moldgen.core.distance_field import (
                mesh_to_sdf_shared, field_blend, extract_isosurface,
            )
            resolution = 80
            tm_a, tm_b = mesh_a.to_trimesh(), mesh_b.to_trimesh()
            sdf_a, sdf_b = await asyncio.to_thread(
                mesh_to_sdf_shared, tm_a, tm_b, resolution,
            )
            combined = field_blend(sdf_a, sdf_b, operation=req.operation, blend_radius=req.blend_radius)
            tm_result = extract_isosurface(combined)
            result_md = MeshData.from_trimesh(tm_result)
        else:
            from moldgen.core.mesh_editor import MeshEditor
            editor = MeshEditor()
            result_md = await asyncio.to_thread(
                editor._boolean_op, mesh_a, mesh_b, req.operation,
            )
    except Exception as exc:
        logger.error("Boolean operation failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Boolean operation failed: {exc}") from exc

    result_id = str(uuid.uuid4())[:8]
    from moldgen.api.routes.models import _loaded_meshes
    _loaded_meshes[result_id] = result_md

    tm = result_md.to_trimesh()
    return {
        "result_id": result_id,
        "operation": req.operation,
        "blend_radius": req.blend_radius,
        "vertices": len(tm.vertices),
        "faces": len(tm.faces),
    }


# ══════════════════════════════════════════════════════════════════════
# Topology Optimisation
# ══════════════════════════════════════════════════════════════════════

class TORequest2D(BaseModel):
    nelx: int = Field(60, ge=10, le=200)
    nely: int = Field(30, ge=10, le=200)
    volfrac: float = Field(0.4, gt=0.05, le=0.9)
    penal: float = Field(3.0, ge=1.0, le=5.0)
    rmin: float = Field(1.5, ge=1.0, le=5.0)
    bc_type: str = Field("cantilever", description="cantilever|mbb|bridge")
    max_iter: int = Field(100, ge=10, le=500)


class TORequest3D(BaseModel):
    nelx: int = Field(20, ge=5, le=60)
    nely: int = Field(10, ge=5, le=60)
    nelz: int = Field(10, ge=5, le=60)
    volfrac: float = Field(0.3, gt=0.05, le=0.9)
    penal: float = Field(3.0, ge=1.0, le=5.0)
    rmin: float = Field(1.5, ge=1.0, le=5.0)
    bc_type: str = Field("cantilever")
    max_iter: int = Field(60, ge=10, le=200)


@router.post("/topology-opt/2d")
async def topology_opt_2d_route(req: TORequest2D):
    """Run 2D SIMP topology optimisation."""
    from moldgen.core.topology_opt import TOConfig2D, topology_opt_2d
    cfg = TOConfig2D(
        nelx=req.nelx, nely=req.nely, volfrac=req.volfrac,
        penal=req.penal, rmin=req.rmin, bc_type=req.bc_type,
        max_iter=req.max_iter,
    )
    try:
        result = await asyncio.to_thread(topology_opt_2d, cfg)
    except Exception as exc:
        logger.error("2D TO failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Topology optimisation failed: {exc}") from exc

    return {
        "iterations": result.iterations,
        "final_compliance": result.final_compliance,
        "final_volfrac": result.final_volfrac,
        "compliance_history": result.compliance_history,
        "density": result.density.tolist(),
    }


@router.post("/topology-opt/3d")
async def topology_opt_3d_route(req: TORequest3D):
    """Run 3D SIMP topology optimisation."""
    from moldgen.core.topology_opt import TOConfig3D, topology_opt_3d
    cfg = TOConfig3D(
        nelx=req.nelx, nely=req.nely, nelz=req.nelz,
        volfrac=req.volfrac, penal=req.penal, rmin=req.rmin,
        bc_type=req.bc_type, max_iter=req.max_iter,
    )
    try:
        result = await asyncio.to_thread(topology_opt_3d, cfg)
    except Exception as exc:
        logger.error("3D TO failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"3D topology optimisation failed: {exc}") from exc

    return {
        "iterations": result.iterations,
        "final_compliance": result.final_compliance,
        "final_volfrac": result.final_volfrac,
        "compliance_history": result.compliance_history,
        "density_shape": list(result.density.shape),
    }


# ══════════════════════════════════════════════════════════════════════
# 3D Lattice Generation
# ══════════════════════════════════════════════════════════════════════

class LatticeRequest(BaseModel):
    model_id: str
    lattice_type: str = Field("tpms", description="graph|tpms|foam")
    cell_type: str = Field("bcc", description="bcc|fcc|octet|kelvin|diamond (for graph)")
    tpms_type: str = Field("gyroid", description="gyroid|schwarz_p|schwarz_d|neovius|lidinoid|iwp|frd")
    cell_size: float = Field(5.0, gt=0.5, le=50)
    beam_radius: float = Field(0.5, gt=0.1, le=5.0)
    wall_thickness: float = Field(0.5, gt=0.1, le=5.0)
    variable_thickness: bool = False
    thickness_field: str = Field("uniform", description="uniform|radial|axial_z|distance_from_surface")
    thickness_min: float = Field(0.3, gt=0.05)
    thickness_max: float = Field(1.0, gt=0.1)
    resolution: int = Field(80, ge=30, le=200)
    n_cells: int = Field(200, ge=20, le=2000, description="Number of cells for foam")


@router.post("/lattice/generate")
async def generate_lattice_route(req: LatticeRequest):
    """Generate 3D lattice structure within a bounding mesh."""
    mesh = _get_mesh(req.model_id)
    from moldgen.core.lattice import LatticeConfig, generate_lattice

    cfg = LatticeConfig(
        cell_type=req.cell_type,
        cell_size=req.cell_size,
        beam_radius=req.beam_radius,
        tpms_type=req.tpms_type,
        wall_thickness=req.wall_thickness,
        variable_thickness=req.variable_thickness,
        thickness_field=req.thickness_field,
        thickness_min=req.thickness_min,
        thickness_max=req.thickness_max,
        resolution=req.resolution,
    )

    try:
        result = await asyncio.to_thread(
            generate_lattice, mesh.to_trimesh(),
            lattice_type=req.lattice_type, config=cfg,
            n_cells=req.n_cells,
        )
    except Exception as exc:
        logger.error("Lattice generation failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Lattice generation failed: {exc}") from exc

    result_id = str(uuid.uuid4())[:8]
    from moldgen.core.mesh_data import MeshData
    from moldgen.api.routes.models import _loaded_meshes
    md = MeshData.from_trimesh(result.mesh)
    _loaded_meshes[result_id] = md

    return {
        "result_id": result_id,
        "lattice_type": result.lattice_type,
        "cell_count": result.cell_count,
        "beam_count": result.beam_count,
        "volume_fraction": result.volume_fraction,
        "vertices": len(result.mesh.vertices),
        "faces": len(result.mesh.faces),
    }


# ══════════════════════════════════════════════════════════════════════
# Interference / Clearance Analysis
# ══════════════════════════════════════════════════════════════════════

class InterferenceRequest(BaseModel):
    model_a_id: str
    model_b_id: str
    sample_count: int = Field(5000, ge=500, le=50000)


class AssemblyCheckRequest(BaseModel):
    model_ids: list[str]
    min_clearance: float = Field(0.5, ge=0, le=10, description="Minimum required clearance (mm)")


@router.post("/interference/check")
async def check_interference(req: InterferenceRequest):
    """Check interference / clearance between two meshes."""
    mesh_a = _get_mesh(req.model_a_id)
    mesh_b = _get_mesh(req.model_b_id)

    from moldgen.core.interference import compute_clearance
    try:
        result = await asyncio.to_thread(
            compute_clearance, mesh_a.to_trimesh(), mesh_b.to_trimesh(), req.sample_count,
        )
    except Exception as exc:
        logger.error("Interference check failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Interference check failed: {exc}") from exc

    return {
        "interference_detected": result.interference_detected,
        "min_clearance": result.min_clearance,
        "max_clearance": result.max_clearance,
        "mean_clearance": result.mean_clearance,
        "interference_volume": result.interference_volume,
        "interference_faces_a": len(result.interference_faces_a),
        "interference_faces_b": len(result.interference_faces_b),
        "histogram": result.clearance_histogram,
    }


@router.post("/interference/assembly")
async def check_assembly(req: AssemblyCheckRequest):
    """Check all part pairs in an assembly for interference."""
    parts = []
    for mid in req.model_ids:
        mesh = _get_mesh(mid)
        parts.append((mid, mesh.to_trimesh()))

    from moldgen.core.interference import validate_assembly
    try:
        result = await asyncio.to_thread(validate_assembly, parts, req.min_clearance)
    except Exception as exc:
        logger.error("Assembly check failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Assembly validation failed: {exc}") from exc

    return {
        "all_clear": result.all_clear,
        "total_interference_volume": result.total_interference_volume,
        "checks": result.checks,
    }


# ══════════════════════════════════════════════════════════════════════
# Mesh Quality Analysis
# ══════════════════════════════════════════════════════════════════════

@router.post("/{model_id}/mesh-quality")
async def analyze_mesh_quality(model_id: str):
    """Comprehensive mesh quality analysis — aspect ratios, edge stats, topology."""
    mesh = _get_mesh(model_id)
    from moldgen.core.analysis import compute_mesh_quality
    try:
        result = await asyncio.to_thread(compute_mesh_quality, mesh)
    except Exception as exc:
        logger.error("Mesh quality analysis failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Mesh quality analysis failed: {exc}") from exc

    return {
        "model_id": model_id,
        "n_vertices": result.n_vertices,
        "n_faces": result.n_faces,
        "n_edges": result.n_edges,
        "aspect_ratio_mean": result.aspect_ratio_mean,
        "aspect_ratio_max": result.aspect_ratio_max,
        "skinny_triangle_count": result.skinny_triangle_count,
        "skinny_fraction": result.skinny_fraction,
        "degenerate_face_count": result.degenerate_face_count,
        "edge_length": {
            "min": result.edge_length_min,
            "max": result.edge_length_max,
            "mean": result.edge_length_mean,
            "std": result.edge_length_std,
        },
        "area": {
            "min": result.area_min,
            "max": result.area_max,
            "mean": result.area_mean,
        },
        "topology": {
            "is_watertight": result.is_watertight,
            "is_manifold": result.is_manifold,
            "euler_characteristic": result.euler_characteristic,
            "genus": result.genus,
        },
        "volume": result.volume,
        "surface_area": result.surface_area,
        "compactness": result.compactness,
        "histograms": {
            "aspect_ratio": result.aspect_ratio_histogram,
            "edge_length": result.edge_length_histogram,
            "min_angle": result.angle_histogram,
        },
    }


# ══════════════════════════════════════════════════════════════════════
# SDF / Distance Field Operations
# ══════════════════════════════════════════════════════════════════════

class SDFRequest(BaseModel):
    model_id: str
    resolution: int = Field(64, ge=16, le=200)


class FieldShellRequest(BaseModel):
    model_id: str
    base_thickness: float = Field(2.0, gt=0.1, le=20)
    thickness_variation: float = Field(1.0, ge=0, le=10)
    field_type: str = Field("distance_from_center",
                            description="distance_from_center|distance_from_base|curvature_proxy")
    resolution: int = Field(64, ge=16, le=128)


@router.post("/sdf/compute")
async def compute_sdf_route(req: SDFRequest):
    """Compute signed distance field for a mesh."""
    mesh = _get_mesh(req.model_id)
    from moldgen.core.distance_field import mesh_to_sdf
    try:
        sdf = await asyncio.to_thread(mesh_to_sdf, mesh.to_trimesh(), req.resolution)
    except Exception as exc:
        logger.error("SDF computation failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"SDF computation failed: {exc}") from exc

    return {
        "model_id": req.model_id,
        "shape": list(sdf.shape),
        "spacing": sdf.spacing,
        "origin": sdf.origin.tolist(),
        "value_range": [float(sdf.values.min()), float(sdf.values.max())],
    }


@router.post("/sdf/variable-shell")
async def variable_shell_route(req: FieldShellRequest):
    """Create a variable-thickness shell driven by a spatial field."""
    mesh = _get_mesh(req.model_id)
    from moldgen.core.distance_field import field_driven_shell
    try:
        result = await asyncio.to_thread(
            field_driven_shell, mesh.to_trimesh(),
            base_thickness=req.base_thickness,
            thickness_variation=req.thickness_variation,
            field_type=req.field_type,
            resolution=req.resolution,
        )
    except Exception as exc:
        logger.error("Variable shell failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Variable shell failed: {exc}") from exc

    result_id = str(uuid.uuid4())[:8]
    from moldgen.core.mesh_data import MeshData
    from moldgen.api.routes.models import _loaded_meshes
    md = MeshData.from_trimesh(result.mesh)
    _loaded_meshes[result_id] = md

    return {
        "result_id": result_id,
        "min_thickness": result.min_thickness,
        "max_thickness": result.max_thickness,
        "mean_thickness": result.mean_thickness,
        "vertices": len(result.mesh.vertices),
        "faces": len(result.mesh.faces),
    }
