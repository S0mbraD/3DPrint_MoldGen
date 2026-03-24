"""模具生成 API — 方向分析、分型面、壳体构建"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from moldgen.api.routes.models import _get_mesh
from moldgen.core.mold_builder import MoldBuilder, MoldConfig, MoldResult
from moldgen.core.orientation import (
    OrientationAnalyzer,
    OrientationConfig,
    OrientationResult,
)
from moldgen.core.parting import PartingConfig, PartingGenerator, PartingResult

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
    mesh = _get_mesh(model_id)
    req = req or OrientationRequest()

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

    return {
        "model_id": model_id,
        "result": result.to_dict(),
    }


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


@router.post("/{model_id}/parting")
async def generate_parting(model_id: str, req: PartingRequest | None = None):
    """生成分型线和分型面"""
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

    config = PartingConfig(smooth_iterations=req.smooth_iterations)
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
    parting_depth: float = 3.0
    parting_pitch: float = 10.0
    add_alignment_pins: bool = True
    add_pour_hole: bool = True
    add_vent_holes: bool = True
    add_flanges: bool = False
    flange_width: float = 12.0
    flange_thickness: float = 4.0
    screw_hole_diameter: float = 4.0
    n_flanges: int = 4


@router.post("/{model_id}/mold/generate")
async def generate_mold(model_id: str, req: MoldRequest | None = None):
    """生成双片壳模具"""
    mesh = _get_mesh(model_id)
    req = req or MoldRequest()

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

    config = MoldConfig(
        wall_thickness=req.wall_thickness,
        clearance=req.clearance,
        shell_type=req.shell_type,
        margin=req.margin,
        parting_style=req.parting_style,
        parting_depth=req.parting_depth,
        parting_pitch=req.parting_pitch,
        add_alignment_pins=req.add_alignment_pins,
        add_pour_hole=req.add_pour_hole,
        add_vent_holes=req.add_vent_holes,
        add_flanges=req.add_flanges,
        flange_width=req.flange_width,
        flange_thickness=req.flange_thickness,
        screw_hole_diameter=req.screw_hole_diameter,
        n_flanges=req.n_flanges,
    )
    builder = MoldBuilder(config)

    try:
        result = await asyncio.to_thread(builder.build_two_part_mold, mesh, direction)
    except Exception as e:
        logger.exception("Mold generation failed")
        raise HTTPException(500, f"Mold generation error: {e}") from e

    mold_id = str(uuid4())[:8]
    _mold_results[mold_id] = result

    return {
        "model_id": model_id,
        "mold_id": mold_id,
        "result": result.to_dict(),
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
