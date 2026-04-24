"""灌注仿真与优化 API（v4: 可视化数据 + 分析报告 + 截面切片）"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from moldgen.api.routes.models import _get_mesh
from moldgen.api.routes.molds import _mold_results
from moldgen.core.fea import FEAConfig, FEAResult, FEASolver
from moldgen.core.flow_sim import FlowSimulator, SimConfig, SimulationResult
from moldgen.core.gating import GatingConfig, GatingResult, GatingSystem
from moldgen.core.material import MATERIAL_PRESETS
from moldgen.core.optimizer import AutoOptimizer, OptimizationConfig

logger = logging.getLogger(__name__)
router = APIRouter()

_gating_results: dict[str, GatingResult] = {}
_sim_results: dict[str, SimulationResult] = {}
_fea_results: dict[str, FEAResult] = {}


# ── Materials ─────────────────────────────────────────────────────────

@router.get("/materials")
async def list_materials():
    """列出所有预设材料"""
    return {
        "materials": {k: v.to_dict() for k, v in MATERIAL_PRESETS.items()}
    }


# ── Gating System ────────────────────────────────────────────────────

class GatingRequest(BaseModel):
    model_id: str
    mold_id: str
    material: str = "silicone_a30"
    gate_diameter: float = 12.0
    n_vents: int = 4
    runner_type: str = "cold"
    n_gates: int = 1
    runner_width: float = 4.0


@router.post("/gating/design")
async def design_gating(req: GatingRequest):
    """设计浇注系统"""
    import time as _time
    t0 = _time.perf_counter()
    mesh = _get_mesh(req.model_id)
    mold = _mold_results.get(req.mold_id)
    if mold is None:
        raise HTTPException(404, f"Mold {req.mold_id} not found. Generate mold first.")

    mat = MATERIAL_PRESETS.get(req.material)
    if mat is None:
        raise HTTPException(400, f"Unknown material: {req.material}. Use /simulation/materials to list.")

    logger.info(
        "Gating design: model=%s mold=%s gate_diam=%.1fmm vents=%d n_gates=%d runner=%s/%.1fmm",
        req.model_id, req.mold_id, req.gate_diameter, req.n_vents,
        req.n_gates, req.runner_type, req.runner_width,
    )
    config = GatingConfig(
        gate_diameter=req.gate_diameter,
        n_vents=req.n_vents,
        n_gates=req.n_gates,
        runner_type=req.runner_type,
        runner_width=req.runner_width,
    )
    gating = GatingSystem(config)

    try:
        result = gating.design(mold, mesh, mat)
    except Exception as e:
        logger.exception("Gating design failed")
        raise HTTPException(500, f"Gating design error: {e}") from e

    try:
        gating.apply_to_mold(mold, result)
    except Exception:
        logger.exception("apply_to_mold failed (non-fatal)")

    gating_id = str(uuid4())[:8]
    _gating_results[gating_id] = result
    elapsed = _time.perf_counter() - t0
    logger.info("Gating design OK: id=%s score=%.2f (%.2fs)", gating_id, result.gate.score, elapsed)

    return {"gating_id": gating_id, "result": result.to_dict()}


# ── Flow Simulation ──────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    model_id: str
    gating_id: str
    material: str = "silicone_a30"
    level: int = 1
    voxel_resolution: int = 48


@router.post("/run")
async def run_simulation(req: SimulationRequest):
    """运行灌注仿真"""
    import time as _time
    t0 = _time.perf_counter()
    mesh = _get_mesh(req.model_id)
    gating = _gating_results.get(req.gating_id)
    if gating is None:
        raise HTTPException(404, f"Gating {req.gating_id} not found. Design gating first.")

    mat = MATERIAL_PRESETS.get(req.material)
    if mat is None:
        raise HTTPException(400, f"Unknown material: {req.material}")

    logger.info("Simulation: model=%s gating=%s level=%d voxel=%d", req.model_id, req.gating_id, req.level, req.voxel_resolution)
    config = SimConfig(level=req.level, voxel_resolution=req.voxel_resolution)
    simulator = FlowSimulator(config)

    try:
        result = simulator.simulate(mesh, gating, mat)
    except Exception as e:
        logger.exception("Simulation failed")
        raise HTTPException(500, f"Simulation error: {e}") from e

    sim_id = str(uuid4())[:8]
    _sim_results[sim_id] = result
    elapsed = _time.perf_counter() - t0
    rd = result.to_dict()
    logger.info(
        "Simulation OK: id=%s fill=%.1f%% time=%.2fs defects=%d (%.2fs)",
        sim_id, rd["fill_fraction"] * 100, rd.get("fill_time_seconds", 0), len(rd.get("defects", [])), elapsed,
    )

    return {"sim_id": sim_id, "result": rd}


# ── Visualization Data ───────────────────────────────────────────────

@router.get("/visualization/{sim_id}")
async def get_visualization_data(sim_id: str):
    """获取仿真可视化点云数据（用于3D热力图渲染）"""
    result = _sim_results.get(sim_id)
    if result is None:
        raise HTTPException(404, f"Simulation {sim_id} not found")

    simulator = FlowSimulator()
    vis_data = simulator.extract_visualization_data(result)
    if vis_data is None:
        raise HTTPException(
            404,
            "No visualization data available (L1 simulations do not produce volumetric data)",
        )

    return {"sim_id": sim_id, **vis_data}


# ── Surface-Mapped Data ──────────────────────────────────────────────

@router.get("/surface-map/{sim_id}")
async def get_surface_mapped_data(
    sim_id: str,
    model_id: str = Query(...),
    field: str = Query("fill_time"),
):
    """Project sim field onto model surface vertices for overlay visualization."""
    result = _sim_results.get(sim_id)
    if result is None:
        raise HTTPException(404, f"Simulation {sim_id} not found")

    mesh = _get_mesh(model_id)
    simulator = FlowSimulator()
    data = simulator.extract_surface_mapped_data(result, mesh, field_name=field)
    if data is None:
        raise HTTPException(404, f"Cannot map field '{field}' to surface")

    return {"sim_id": sim_id, "model_id": model_id, **data}


# ── Analysis Report ──────────────────────────────────────────────────

@router.get("/analysis/{sim_id}")
async def get_analysis_report(sim_id: str):
    """获取综合仿真分析报告"""
    result = _sim_results.get(sim_id)
    if result is None:
        raise HTTPException(404, f"Simulation {sim_id} not found")

    base = result.to_dict()
    analysis = result.analysis.to_dict() if result.analysis else {}

    return {
        "sim_id": sim_id,
        "summary": {
            "fill_fraction": base["fill_fraction"],
            "fill_time_seconds": base["fill_time_seconds"],
            "max_pressure": base["max_pressure"],
            "n_defects": len(base["defects"]),
        },
        "defects": base["defects"],
        "analysis": analysis,
        "available_fields": [
            k.replace("has_", "").replace("_field", "")
            for k in base
            if k.startswith("has_") and base[k] is True
        ],
    }


# ── Cross-Section Slice ──────────────────────────────────────────────

@router.get("/cross-section/{sim_id}")
async def get_cross_section(
    sim_id: str,
    axis: str = Query("z", pattern="^[xyz]$"),
    position: float = Query(0.5, ge=0.0, le=1.0),
    field: str = Query("fill_time"),
):
    """获取仿真场的2D截面切片（用于热力图渲染）"""
    result = _sim_results.get(sim_id)
    if result is None:
        raise HTTPException(404, f"Simulation {sim_id} not found")

    simulator = FlowSimulator()
    section = simulator.extract_cross_section(result, axis=axis, position=position, field_name=field)
    if section is None:
        raise HTTPException(
            404,
            f"Cannot extract cross-section for field '{field}' (not computed or L1 simulation)",
        )

    return {"sim_id": sim_id, **section}


# ── Auto Optimization ────────────────────────────────────────────────

class OptimizeRequest(BaseModel):
    model_id: str
    mold_id: str
    gating_id: str
    material: str = "silicone_a30"
    max_iterations: int = 5


@router.post("/optimize")
async def run_optimization(req: OptimizeRequest):
    """运行自动优化"""
    mesh = _get_mesh(req.model_id)
    mold = _mold_results.get(req.mold_id)
    if mold is None:
        raise HTTPException(404, f"Mold {req.mold_id} not found")

    gating = _gating_results.get(req.gating_id)
    if gating is None:
        raise HTTPException(404, f"Gating {req.gating_id} not found")

    mat = MATERIAL_PRESETS.get(req.material)
    if mat is None:
        raise HTTPException(400, f"Unknown material: {req.material}")

    opt_config = OptimizationConfig(max_iterations=req.max_iterations, sim_level=1)
    optimizer = AutoOptimizer(opt_config)

    try:
        result = optimizer.optimize(mesh, mold, mat, gating)
    except Exception as e:
        logger.exception("Optimization failed")
        raise HTTPException(500, f"Optimization error: {e}") from e

    gating_id = None
    sim_id = None
    if result.final_gating:
        gating_id = str(uuid4())[:8]
        _gating_results[gating_id] = result.final_gating
    if result.final_simulation:
        sim_id = str(uuid4())[:8]
        _sim_results[sim_id] = result.final_simulation

    return {
        "result": result.to_dict(),
        "optimized_gating_id": gating_id,
        "optimized_sim_id": sim_id,
    }


# ── Results ───────────────────────────────────────────────────────────

@router.get("/result/{sim_id}")
async def get_sim_result(sim_id: str):
    """获取仿真结果"""
    result = _sim_results.get(sim_id)
    if result is None:
        raise HTTPException(404, f"Simulation {sim_id} not found")
    return {"sim_id": sim_id, "result": result.to_dict()}


@router.get("/")
async def list_simulations():
    """列出所有仿真"""
    return {
        "simulations": {
            sid: {
                "fill_fraction": r.fill_fraction,
                "defects": len(r.defects),
                "has_visualization": r.voxel_origin is not None,
            }
            for sid, r in _sim_results.items()
        }
    }


# ── FEA (Finite Element Analysis) ────────────────────────────────────

class FEARequest(BaseModel):
    model_id: str
    youngs_modulus: float = 2000.0
    poissons_ratio: float = 0.4
    density: float = 1.1e-6
    yield_strength: float = 40.0
    pressure_load: float = 0.1
    gravity: bool = True
    gravity_direction: list[float] = [0, 0, -1]
    material_preset: str | None = None


MATERIAL_FEA_PRESETS = {
    "pla": FEAConfig(youngs_modulus=2500, poissons_ratio=0.36, density=1.24e-6, yield_strength=40),
    "abs": FEAConfig(youngs_modulus=2100, poissons_ratio=0.39, density=1.04e-6, yield_strength=35),
    "petg": FEAConfig(youngs_modulus=2020, poissons_ratio=0.40, density=1.27e-6, yield_strength=50),
    "nylon": FEAConfig(youngs_modulus=1700, poissons_ratio=0.42, density=1.14e-6, yield_strength=70),
    "silicone": FEAConfig(youngs_modulus=5.0, poissons_ratio=0.48, density=1.1e-6, yield_strength=5),
    "resin": FEAConfig(youngs_modulus=2800, poissons_ratio=0.35, density=1.18e-6, yield_strength=55),
    "aluminum": FEAConfig(youngs_modulus=69000, poissons_ratio=0.33, density=2.7e-6, yield_strength=240),
    "steel": FEAConfig(youngs_modulus=200000, poissons_ratio=0.30, density=7.85e-6, yield_strength=250),
}


@router.post("/fea/run")
async def run_fea(req: FEARequest):
    """运行有限元结构分析"""
    import asyncio

    mesh = _get_mesh(req.model_id)

    if req.material_preset and req.material_preset in MATERIAL_FEA_PRESETS:
        config = MATERIAL_FEA_PRESETS[req.material_preset]
        config.pressure_load = req.pressure_load
        config.gravity = req.gravity
        config.gravity_direction = req.gravity_direction
    else:
        config = FEAConfig(
            youngs_modulus=req.youngs_modulus,
            poissons_ratio=req.poissons_ratio,
            density=req.density,
            yield_strength=req.yield_strength,
            pressure_load=req.pressure_load,
            gravity=req.gravity,
            gravity_direction=req.gravity_direction,
        )

    solver = FEASolver(config)

    try:
        result = await asyncio.to_thread(solver.analyze, mesh)
    except Exception as e:
        logger.exception("FEA failed")
        raise HTTPException(500, f"FEA error: {e}") from e

    fea_id = str(uuid4())[:8]
    _fea_results[fea_id] = result

    return {
        "fea_id": fea_id,
        "model_id": req.model_id,
        "result": result.to_dict(),
    }


@router.get("/fea/visualization/{fea_id}")
async def get_fea_visualization(fea_id: str):
    """获取FEA可视化数据（逐顶点应力/位移/安全系数）"""
    result = _fea_results.get(fea_id)
    if result is None:
        raise HTTPException(404, f"FEA result {fea_id} not found")

    return {"fea_id": fea_id, **result.to_visualization_dict()}


@router.get("/fea/materials")
async def list_fea_materials():
    """列出 FEA 材料预设"""
    return {
        "materials": {
            k: {
                "youngs_modulus": v.youngs_modulus,
                "poissons_ratio": v.poissons_ratio,
                "density": v.density,
                "yield_strength": v.yield_strength,
            }
            for k, v in MATERIAL_FEA_PRESETS.items()
        }
    }
