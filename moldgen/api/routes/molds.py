"""模具生成 API — 方向分析、分型面、壳体构建"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from moldgen.api.routes.models import _get_mesh
from moldgen.core.mesh_data import MeshData
from moldgen.core.mold_builder import MoldBuilder, MoldConfig, MoldResult
from moldgen.core.orientation import (
    OrientationAnalyzer,
    OrientationConfig,
    OrientationResult,
)
from moldgen.core.parting import (
    PartingConfig,
    PartingGenerator,
    PartingResult,
    UndercutAnalyzer,
    UndercutInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_mold_results: dict[str, MoldResult] = {}
_orientation_results: dict[str, OrientationResult] = {}
_parting_results: dict[str, PartingResult] = {}


# ── Orientation Analysis ─────────────────────────────────────────────

class OrientationRequest(BaseModel):
    n_samples: int = 100
    n_final: int = 5


@router.post("/{model_id}/orientation")
async def analyze_orientation(model_id: str, req: OrientationRequest | None = None):
    """分析最优脱模方向"""
    import time as _time
    t0 = _time.perf_counter()
    mesh = _get_mesh(model_id)
    req = req or OrientationRequest()
    logger.info("Orientation: model=%s samples=%d final=%d", model_id, req.n_samples, req.n_final)

    config = OrientationConfig(
        n_fibonacci_samples=req.n_samples,
        n_final_candidates=req.n_final,
    )
    analyzer = OrientationAnalyzer(config)

    try:
        result = await asyncio.to_thread(analyzer.analyze, mesh)
    except Exception as e:
        logger.exception("Orientation analysis failed")
        raise HTTPException(500, f"Orientation analysis error: {e}") from e

    _orientation_results[model_id] = result
    d = result.to_dict()
    elapsed = _time.perf_counter() - t0
    logger.info(
        "Orientation OK: model=%s score=%.1f%% dir=[%.2f,%.2f,%.2f] candidates=%d (%.2fs)",
        model_id, d["best_score"]["total_score"] * 100,
        *d["best_direction"], len(d["top_candidates"]), elapsed,
    )

    return {"model_id": model_id, "result": d}


class EvalDirectionRequest(BaseModel):
    direction: list[float]


@router.post("/{model_id}/orientation/evaluate")
async def evaluate_direction(model_id: str, req: EvalDirectionRequest):
    """评估指定方向的脱模性能"""
    mesh = _get_mesh(model_id)

    if len(req.direction) != 3:
        raise HTTPException(400, "Direction must be [x, y, z]")

    import numpy as np
    d = np.array(req.direction, dtype=np.float64)
    if np.linalg.norm(d) < 1e-8:
        raise HTTPException(400, "Direction must be non-zero")

    analyzer = OrientationAnalyzer()
    score = analyzer.evaluate_direction(mesh, d)
    return {"model_id": model_id, "score": score.to_dict()}


# ── Parting Line / Surface ───────────────────────────────────────────

class PartingRequest(BaseModel):
    direction: list[float] | None = None
    smooth_iterations: int = 5
    surface_type: str = "auto"           # "flat" | "heightfield" | "projected" | "auto"
    heightfield_resolution: int = 40
    undercut_threshold: float = 1.0


@router.post("/{model_id}/parting")
async def generate_parting(model_id: str, req: PartingRequest | None = None):
    """生成分型线、分型面并进行 undercut 分析"""
    mesh = _get_mesh(model_id)
    req = req or PartingRequest()

    import numpy as np

    if req.direction:
        direction = np.array(req.direction, dtype=np.float64)
    else:
        ori = _orientation_results.get(model_id)
        if ori is None:
            raise HTTPException(
                400,
                "No direction specified and no orientation analysis found. "
                "Run orientation analysis first or provide a direction.",
            )
        direction = ori.best_direction

    config = PartingConfig(
        smooth_iterations=req.smooth_iterations,
        surface_type=req.surface_type,
        heightfield_resolution=req.heightfield_resolution,
        undercut_threshold=req.undercut_threshold,
    )
    generator = PartingGenerator(config)

    try:
        result = await asyncio.to_thread(generator.generate, mesh, direction)
    except Exception as e:
        logger.exception("Parting generation failed")
        raise HTTPException(500, f"Parting generation error: {e}") from e

    _parting_results[model_id] = result

    return {
        "model_id": model_id,
        "result": result.to_dict(),
    }


@router.post("/{model_id}/undercut")
async def analyze_undercut(model_id: str, req: PartingRequest | None = None):
    """独立 undercut 分析端点（不重新生成分型面）"""
    mesh = _get_mesh(model_id)
    req = req or PartingRequest()

    import numpy as np

    if req.direction:
        direction = np.array(req.direction, dtype=np.float64)
    else:
        ori = _orientation_results.get(model_id)
        if ori is None:
            raise HTTPException(
                400,
                "No direction and no orientation result. "
                "Run orientation analysis first.",
            )
        direction = ori.best_direction

    direction = direction / (np.linalg.norm(direction) + 1e-12)
    tm = mesh.to_trimesh()

    try:
        uc = await asyncio.to_thread(
            UndercutAnalyzer().analyze, tm, direction,
            req.undercut_threshold,
        )
    except Exception as e:
        logger.exception("Undercut analysis failed")
        raise HTTPException(500, f"Undercut analysis error: {e}") from e

    return {
        "model_id": model_id,
        "undercut": uc.to_dict(),
    }


@router.get("/{model_id}/undercut/heatmap")
async def get_undercut_heatmap(model_id: str):
    """导出 undercut 深度热力图数据（per-face depth 用于 3D 着色）"""
    pr = _parting_results.get(model_id)
    if pr is None:
        raise HTTPException(404, "Run parting generation first.")

    mesh = _get_mesh(model_id)
    tm = mesh.to_trimesh()

    heatmap = PartingGenerator.export_undercut_heatmap(tm, pr.undercut)
    return {
        "model_id": model_id,
        "heatmap": heatmap,
    }


@router.get("/{model_id}/parting/surface.glb")
async def get_parting_surface_glb(model_id: str):
    """获取分型面 GLB 模型"""
    pr = _parting_results.get(model_id)
    if pr is None or pr.parting_surface is None:
        raise HTTPException(404, "No parting surface. Run parting generation first.")

    glb = pr.parting_surface.mesh.to_glb()
    return Response(content=glb, media_type="model/gltf-binary")


# ── Mold Shell Generation ────────────────────────────────────────────

class MoldRequest(BaseModel):
    direction: list[float] | None = None
    wall_thickness: float = 4.0
    clearance: float = 0.3
    shell_type: str = "box"
    margin: float = 10.0
    parting_style: str = "flat"
    parting_surface_type: str = "flat"  # "flat" | "heightfield" | "projected" | "auto"
    parting_depth: float = 3.0
    parting_pitch: float = 10.0
    add_alignment_pins: bool = True
    # NOTE: pour/vent holes are now handled by the gating module
    # (POST /simulation/gating/design). These fields are kept for
    # backward compatibility but are ignored during mold generation.
    add_pour_hole: bool = False
    add_vent_holes: bool = False
    # Screw fastening (pocket + tab)
    add_screw_holes: bool = False
    screw_size: str = "M4"
    n_screws: int = 4
    screw_counterbore: bool = True
    screw_tab_thickness: float = 5.0
    # Clamp bracket
    add_clamp_bracket: bool = False
    clamp_width: float = 15.0
    clamp_thickness: float = 3.0
    clamp_screw_size: str = "M3"
    n_clamp_screws: int = 4
    # Other
    shrinkage_compensation: float = 0.0
    add_ejectors: bool = False
    n_ejectors: int = 4
    surface_texture: str = "none"
    mold_material: str = "pla"


@router.post("/{model_id}/mold/generate")
async def generate_mold(model_id: str, req: MoldRequest | None = None):
    """生成双片壳模具"""
    import time as _time
    t0 = _time.perf_counter()
    mesh = _get_mesh(model_id)
    req = req or MoldRequest()
    logger.info(
        "Mold gen: model=%s shell=%s parting=%s wall=%.1fmm screws=%s",
        model_id, req.shell_type, req.parting_style, req.wall_thickness, req.add_screw_holes,
    )

    import numpy as np

    if req.direction:
        direction = np.array(req.direction, dtype=np.float64)
    else:
        ori = _orientation_results.get(model_id)
        if ori is None:
            raise HTTPException(
                400,
                "No direction specified. Run orientation analysis first or provide one.",
            )
        direction = ori.best_direction

    # Apply shrinkage compensation by scaling the mesh
    if req.shrinkage_compensation > 0:
        scale = 1.0 + req.shrinkage_compensation / 100.0
        scaled_verts = mesh.vertices * scale
        mesh = MeshData(
            vertices=scaled_verts, faces=mesh.faces.copy(),
            unit=mesh.unit, source_path=mesh.source_path,
            source_format=mesh.source_format,
        )
        logger.info("Applied shrinkage compensation: %.2f%% (scale=%.4f)", req.shrinkage_compensation, scale)

    config = MoldConfig(
        wall_thickness=req.wall_thickness,
        clearance=req.clearance,
        shell_type=req.shell_type,
        margin=req.margin,
        parting_style=req.parting_style,
        parting_surface_type=req.parting_surface_type,
        parting_depth=req.parting_depth,
        parting_pitch=req.parting_pitch,
        add_alignment_pins=req.add_alignment_pins,
        add_pour_hole=False,
        add_vent_holes=False,
        add_screw_holes=req.add_screw_holes,
        screw_size=req.screw_size,
        n_screws=req.n_screws,
        screw_counterbore=req.screw_counterbore,
        screw_tab_thickness=req.screw_tab_thickness,
        add_clamp_bracket=req.add_clamp_bracket,
        clamp_width=req.clamp_width,
        clamp_thickness=req.clamp_thickness,
        clamp_screw_size=req.clamp_screw_size,
        n_clamp_screws=req.n_clamp_screws,
        mold_material=req.mold_material,
        surface_texture=req.surface_texture,
    )
    builder = MoldBuilder(config)

    try:
        result = await asyncio.to_thread(builder.build_two_part_mold, mesh, direction)
    except Exception as e:
        logger.exception("Mold generation failed")
        raise HTTPException(500, f"Mold generation error: {e}") from e

    mold_id = str(uuid4())[:8]
    _mold_results[mold_id] = result
    elapsed = _time.perf_counter() - t0
    rd = result.to_dict()
    logger.info(
        "Mold gen OK: mold_id=%s shells=%d cavity_vol=%.1f (%.2fs)",
        mold_id, rd.get("n_shells", 0), rd.get("cavity_volume", 0), elapsed,
    )

    return {
        "model_id": model_id,
        "mold_id": mold_id,
        "result": rd,
        "mold_material": config.mold_material,
        "surface_texture": config.surface_texture,
    }


# ── Pour / Vent Preview ──────────────────────────────────────────────

class HolePreviewRequest(BaseModel):
    direction: list[float] | None = None
    pour_hole_diameter: float = 15.0
    vent_hole_diameter: float = 3.0
    n_vent_holes: int = 4


@router.post("/{model_id}/mold/hole-preview")
async def preview_hole_positions(model_id: str, req: HolePreviewRequest | None = None):
    """Preview recommended pour/vent positions without full mold generation."""
    import numpy as np
    mesh = _get_mesh(model_id)
    req = req or HolePreviewRequest()

    if req.direction:
        direction = np.array(req.direction, dtype=np.float64)
    else:
        ori = _orientation_results.get(model_id)
        if ori is None:
            raise HTTPException(400, "No direction. Run orientation analysis first or provide one.")
        direction = ori.best_direction

    config = MoldConfig(
        pour_hole_diameter=req.pour_hole_diameter,
        vent_hole_diameter=req.vent_hole_diameter,
        n_vent_holes=req.n_vent_holes,
    )
    builder = MoldBuilder(config)

    def _compute():
        tm = mesh.to_trimesh()
        pour = builder._compute_pour_gate(tm, tm, direction)
        vents = builder._compute_vent_holes(tm, direction, pour.position)
        return pour, vents

    try:
        pour, vents = await asyncio.to_thread(_compute)
    except Exception as e:
        logger.exception("Hole preview failed")
        raise HTTPException(500, f"Hole preview error: {e}") from e

    return {
        "model_id": model_id,
        "pour_hole": pour.to_dict(),
        "vent_holes": [v.to_dict() for v in vents],
    }


class MultiPartMoldRequest(BaseModel):
    directions: list[list[float]]
    wall_thickness: float = 4.0
    clearance: float = 0.3
    shell_type: str = "box"
    margin: float = 10.0


@router.post("/{model_id}/mold/generate-multi")
async def generate_multi_part_mold(model_id: str, req: MultiPartMoldRequest):
    """生成多片壳模具"""
    mesh = _get_mesh(model_id)

    import numpy as np

    if len(req.directions) < 2:
        raise HTTPException(400, "At least 2 directions required for multi-part mold")

    directions = [np.array(d, dtype=np.float64) for d in req.directions]

    config = MoldConfig(
        wall_thickness=req.wall_thickness,
        clearance=req.clearance,
        shell_type=req.shell_type,
        margin=req.margin,
    )
    builder = MoldBuilder(config)

    try:
        result = await asyncio.to_thread(builder.build_multi_part_mold, mesh, directions)
    except Exception as e:
        logger.exception("Multi-part mold generation failed")
        raise HTTPException(500, f"Multi-part mold error: {e}") from e

    mold_id = str(uuid4())[:8]
    _mold_results[mold_id] = result

    return {
        "model_id": model_id,
        "mold_id": mold_id,
        "result": result.to_dict(),
    }


# ── Mold Result Retrieval ────────────────────────────────────────────

@router.get("/result/{mold_id}")
async def get_mold_result(mold_id: str):
    """获取模具生成结果"""
    result = _mold_results.get(mold_id)
    if result is None:
        raise HTTPException(404, f"Mold {mold_id} not found")
    return {"mold_id": mold_id, "result": result.to_dict()}


@router.get("/result/{mold_id}/shell/{shell_id}/glb")
async def get_shell_glb(mold_id: str, shell_id: int):
    """获取单个壳体的 GLB 模型"""
    result = _mold_results.get(mold_id)
    if result is None:
        raise HTTPException(404, f"Mold {mold_id} not found")

    shell = None
    for s in result.shells:
        if s.shell_id == shell_id:
            shell = s
            break

    if shell is None:
        raise HTTPException(404, f"Shell {shell_id} not found in mold {mold_id}")

    glb = shell.mesh.to_glb()
    return Response(content=glb, media_type="model/gltf-binary")


class CoolingChannelRequest(BaseModel):
    channel_diameter: float = 6.0
    wall_offset: float = 10.0
    n_channels: int = 4
    layout: str = "conformal"  # "conformal"|"straight"|"spiral"|"baffle"
    coolant_temp: float = 25.0
    flow_rate: float = 10.0


@router.post("/result/{mold_id}/cooling")
async def design_cooling_channels(mold_id: str, req: CoolingChannelRequest):
    """nTopology-style conformal cooling channel design.
    
    Generates cooling channel paths optimised for uniform temperature
    distribution based on the mold cavity geometry.
    """
    import numpy as np

    result = _mold_results.get(mold_id)
    if result is None:
        raise HTTPException(404, f"Mold {mold_id} not found")

    shell = result.shells[0] if result.shells else None
    if shell is None:
        raise HTTPException(400, "No shells available")

    tm = shell.mesh.to_trimesh()
    bounds = tm.bounds
    center = tm.centroid
    extent = bounds[1] - bounds[0]

    channels = []
    if req.layout == "conformal":
        for i in range(req.n_channels):
            t = (i + 0.5) / req.n_channels
            z = bounds[0][2] + t * extent[2]
            n_pts = 12
            pts = []
            for j in range(n_pts + 1):
                angle = 2 * np.pi * j / n_pts
                x = center[0] + (extent[0] / 2 + req.wall_offset) * np.cos(angle)
                y = center[1] + (extent[1] / 2 + req.wall_offset) * np.sin(angle)
                pts.append([round(float(x), 2), round(float(y), 2), round(float(z), 2)])
            channels.append({
                "id": i,
                "type": "conformal",
                "diameter": req.channel_diameter,
                "path": pts,
                "length": round(float(np.pi * (extent[0] + extent[1]) / 2 + 2 * req.wall_offset * np.pi), 1),
            })
    elif req.layout == "straight":
        for i in range(req.n_channels):
            t = (i + 0.5) / req.n_channels
            y = bounds[0][1] + t * extent[1]
            channels.append({
                "id": i,
                "type": "straight",
                "diameter": req.channel_diameter,
                "path": [
                    [round(float(bounds[0][0] - 5), 2), round(float(y), 2), round(float(center[2]), 2)],
                    [round(float(bounds[1][0] + 5), 2), round(float(y), 2), round(float(center[2]), 2)],
                ],
                "length": round(float(extent[0] + 10), 1),
            })
    elif req.layout == "spiral":
        n_turns = req.n_channels
        n_pts = n_turns * 20
        pts = []
        for j in range(n_pts + 1):
            t = j / n_pts
            angle = 2 * np.pi * n_turns * t
            r = (extent[0] / 2 + req.wall_offset) * (0.3 + 0.7 * t)
            z = bounds[0][2] + t * extent[2]
            pts.append([
                round(float(center[0] + r * np.cos(angle)), 2),
                round(float(center[1] + r * np.sin(angle)), 2),
                round(float(z), 2),
            ])
        channels.append({
            "id": 0,
            "type": "spiral",
            "diameter": req.channel_diameter,
            "path": pts,
            "length": round(float(n_turns * np.pi * (extent[0] + extent[1]) / 2), 1),
        })
    else:
        for i in range(req.n_channels):
            t = (i + 0.5) / req.n_channels
            x = bounds[0][0] + t * extent[0]
            channels.append({
                "id": i,
                "type": "baffle",
                "diameter": req.channel_diameter,
                "path": [
                    [round(float(x), 2), round(float(bounds[0][1] - 5), 2), round(float(center[2] - extent[2] / 4), 2)],
                    [round(float(x), 2), round(float(center[1]), 2), round(float(center[2] + extent[2] / 4), 2)],
                    [round(float(x), 2), round(float(bounds[1][1] + 5), 2), round(float(center[2] - extent[2] / 4), 2)],
                ],
                "length": round(float(extent[1] + 10 + extent[2] / 2), 1),
            })

    total_length = sum(c["length"] for c in channels)
    volume_rate = req.flow_rate / 60.0 * 1e-6
    cross_area = np.pi * (req.channel_diameter / 2000) ** 2
    velocity = volume_rate / cross_area if cross_area > 0 else 0
    reynolds = 1000 * velocity * (req.channel_diameter / 1000) / 1e-6

    return {
        "mold_id": mold_id,
        "cooling": {
            "n_channels": len(channels),
            "layout": req.layout,
            "channels": channels,
            "total_length": round(total_length, 1),
            "coolant_temp": req.coolant_temp,
            "flow_rate": req.flow_rate,
            "flow_velocity": round(float(velocity), 2),
            "reynolds_number": round(float(reynolds), 0),
            "flow_regime": "turbulent" if reynolds > 4000 else "transitional" if reynolds > 2300 else "laminar",
            "estimated_cooling_time": round(float(result.cavity_volume * 0.0012 / max(total_length * 0.001, 0.01)), 1),
        },
    }


class MoldAnalysisRequest(BaseModel):
    check_draft: bool = True
    check_undercuts: bool = True
    check_wall_uniformity: bool = True


@router.post("/result/{mold_id}/analyze")
async def analyze_mold(mold_id: str, req: MoldAnalysisRequest):
    """Comprehensive mold analysis — draft, undercuts, wall uniformity."""
    import numpy as np

    result = _mold_results.get(mold_id)
    if result is None:
        raise HTTPException(404, f"Mold {mold_id} not found")

    analyses = {}

    for shell in result.shells:
        tm = shell.mesh.to_trimesh()
        shell_analysis = {
            "shell_id": shell.shell_id,
            "face_count": len(tm.faces),
            "volume": round(float(tm.volume), 1) if tm.is_watertight else None,
            "surface_area": round(float(tm.area), 1),
            "is_watertight": bool(tm.is_watertight),
            "is_manifold": bool(tm.is_volume),
        }

        if req.check_wall_uniformity:
            extents = tm.bounding_box.extents if tm.bounding_box is not None else [0, 0, 0]
            shell_analysis["bounding_box"] = [round(float(e), 1) for e in extents]

        analyses[str(shell.shell_id)] = shell_analysis

    return {
        "mold_id": mold_id,
        "cavity_volume": round(result.cavity_volume, 1),
        "n_shells": len(result.shells),
        "shell_analyses": analyses,
    }


@router.get("/")
async def list_molds():
    """列出所有已生成的模具"""
    molds = {}
    for mid, result in _mold_results.items():
        molds[mid] = {
            "n_shells": len(result.shells),
            "cavity_volume": round(result.cavity_volume, 2),
        }
    return {"molds": molds}


# ── Skin Mold Generation (蒙皮模具) ─────────────────────────────────

from moldgen.core.skin_mold import SkinMoldConfig, SkinMoldGenerator, SkinMoldResult

_skin_mold_results: dict[str, SkinMoldResult] = {}


class SkinMoldRequest(BaseModel):
    direction: list[float] | None = None
    # Skin layer
    skin_thickness: float = 3.0
    variable_thickness: bool = False
    min_skin_thickness: float = 2.0
    max_skin_thickness: float = 5.0
    curvature_influence: float = 0.5
    # Core
    core_resolution: int = 64
    core_smoothing: int = 2
    core_clearance: float = 0.3
    core_shell_thickness: float = 0.0
    core_drain_holes: bool = False
    core_drain_diameter: float = 5.0
    core_drain_count: int = 2
    core_max_faces: int = 120_000
    core_morphological_closing: int = 2
    # Support pegs
    add_support_pegs: bool = True
    peg_count: int = 3
    peg_diameter: float = 4.0
    peg_height: float = 6.0
    # Registration
    registration_type: str = "pin"
    registration_count: int = 4
    registration_diameter: float = 5.0
    registration_height: float = 8.0
    registration_tolerance: float = 0.2
    # Outer mold
    mold_wall_thickness: float = 5.0
    mold_clearance: float = 0.15
    mold_shell_type: str = "box"
    mold_margin: float = 10.0
    parting_style: str = "flat"
    parting_surface_type: str = "flat"
    add_alignment_pins: bool = True
    add_screw_holes: bool = False
    screw_size: str = "M4"
    n_screws: int = 4
    # Shrinkage
    shrinkage_compensation: float = 0.0


@router.post("/{model_id}/mold/generate-skin")
async def generate_skin_mold(model_id: str, req: SkinMoldRequest | None = None):
    """生成蒙皮模具：模芯 + 外模 + 定位特征"""
    import time as _time

    t0 = _time.perf_counter()
    mesh = _get_mesh(model_id)
    req = req or SkinMoldRequest()

    import numpy as np

    direction = (
        np.array(req.direction, dtype=np.float64)
        if req.direction
        else _orientation_results.get(model_id, None)
    )
    if direction is not None and hasattr(direction, "best_direction"):
        direction = np.array(direction.best_direction, dtype=np.float64)
    if direction is None:
        direction = np.array([0.0, 0.0, 1.0])
    direction = direction / (np.linalg.norm(direction) + 1e-12)

    build_mesh = mesh
    if req.shrinkage_compensation > 0:
        scale = 1.0 + req.shrinkage_compensation / 100.0
        scaled_verts = mesh.vertices * scale
        build_mesh = MeshData(
            vertices=scaled_verts,
            faces=mesh.faces.copy(),
            normals=mesh.normals.copy() if mesh.normals is not None else None,
            unit=mesh.unit,
        )

    cfg = SkinMoldConfig(
        skin_thickness=req.skin_thickness,
        variable_thickness=req.variable_thickness,
        min_skin_thickness=req.min_skin_thickness,
        max_skin_thickness=req.max_skin_thickness,
        curvature_influence=req.curvature_influence,
        core_resolution=req.core_resolution,
        core_smoothing=req.core_smoothing,
        core_clearance=req.core_clearance,
        core_shell_thickness=req.core_shell_thickness,
        core_drain_holes=req.core_drain_holes,
        core_drain_diameter=req.core_drain_diameter,
        core_drain_count=req.core_drain_count,
        core_max_faces=req.core_max_faces,
        core_morphological_closing=req.core_morphological_closing,
        add_support_pegs=req.add_support_pegs,
        peg_count=req.peg_count,
        peg_diameter=req.peg_diameter,
        peg_height=req.peg_height,
        registration_type=req.registration_type,
        registration_count=req.registration_count,
        registration_diameter=req.registration_diameter,
        registration_height=req.registration_height,
        registration_tolerance=req.registration_tolerance,
        mold_wall_thickness=req.mold_wall_thickness,
        mold_clearance=req.mold_clearance,
        mold_shell_type=req.mold_shell_type,
        mold_margin=req.mold_margin,
        parting_style=req.parting_style,
        parting_surface_type=req.parting_surface_type,
        add_alignment_pins=req.add_alignment_pins,
        add_screw_holes=req.add_screw_holes,
        screw_size=req.screw_size,
        n_screws=req.n_screws,
    )

    generator = SkinMoldGenerator(cfg)

    try:
        result = await asyncio.to_thread(generator.generate, build_mesh, direction)
    except Exception as e:
        logger.exception("Skin mold generation failed")
        raise HTTPException(500, f"Skin mold generation error: {e}") from e

    skin_id = str(uuid4())[:8]
    _skin_mold_results[skin_id] = result
    _mold_results[skin_id] = result.mold_result

    elapsed = _time.perf_counter() - t0
    logger.info("Skin mold generated in %.2fs: id=%s", elapsed, skin_id)

    return {
        "model_id": model_id,
        "skin_mold_id": skin_id,
        "mold_id": skin_id,
        "result": result.to_dict(),
        "elapsed_s": round(elapsed, 2),
    }


@router.get("/skin/{skin_id}")
async def get_skin_mold_result(skin_id: str):
    """获取蒙皮模具结果"""
    result = _skin_mold_results.get(skin_id)
    if result is None:
        raise HTTPException(404, f"Skin mold {skin_id} not found")
    return {"skin_mold_id": skin_id, "result": result.to_dict()}


@router.get("/skin/{skin_id}/core.glb")
async def get_skin_core_glb(skin_id: str):
    """下载模芯 GLB 模型"""
    result = _skin_mold_results.get(skin_id)
    if result is None:
        raise HTTPException(404, f"Skin mold {skin_id} not found")

    glb = result.core_mesh.to_glb()
    return Response(content=glb, media_type="model/gltf-binary")


@router.get("/skin/{skin_id}/thickness-map")
async def get_skin_thickness_map(skin_id: str):
    """获取蒙皮厚度可视化数据（per-vertex 归一化厚度）"""
    result = _skin_mold_results.get(skin_id)
    if result is None:
        raise HTTPException(404, f"Skin mold {skin_id} not found")

    return {
        "skin_mold_id": skin_id,
        "has_map": result.thickness_map is not None,
        "thickness_map": result.thickness_map,
        "stats": result.skin_thickness_stats,
    }
