"""支撑板 API — 位置分析/生成/锚固/装配验证"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from moldgen.core.insert_generator import (
    AnchorType,
    InsertConfig,
    InsertGenerator,
    InsertType,
    OrganType,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_insert_results: dict[str, dict] = {}


def _get_mesh(model_id: str):
    from moldgen.api.routes.models import _loaded_meshes
    mesh = _loaded_meshes.get(model_id)
    if not mesh:
        raise HTTPException(404, f"Model {model_id} not found")
    return mesh


def _get_mold_shells(mold_id: str | None) -> list | None:
    if not mold_id:
        return None
    from moldgen.api.routes.molds import _mold_results
    mold = _mold_results.get(mold_id)
    if not mold:
        return None
    return [s.mesh for s in mold.shells]


class AnalyzePositionsRequest(BaseModel):
    model_id: str
    n_candidates: int = 5
    organ_type: str = "general"


class GenerateInsertRequest(BaseModel):
    model_id: str
    position_index: int = 0
    thickness: float = 2.0
    insert_type: str = "flat"
    organ_type: str = "general"
    anchor_type: str | None = None
    anchor_density: float = 0.3
    n_plates: int = 1
    mold_id: str | None = None
    # Conformal
    conformal_offset: float = 3.0
    # Ribbed
    rib_height: float = 3.0
    rib_spacing: float = 8.0
    # Lattice
    lattice_cell_size: float = 5.0
    lattice_strut_diameter: float = 1.2
    lattice_type: str = "bcc"


class AddAnchorRequest(BaseModel):
    insert_id: str
    plate_index: int = 0
    anchor_type: str = "mesh_holes"
    anchor_density: float = 0.3
    feature_size: float = 2.0


class ValidateRequest(BaseModel):
    model_id: str
    insert_id: str
    mold_id: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_positions(req: AnalyzePositionsRequest):
    """分析支撑板最佳位置"""
    mesh = _get_mesh(req.model_id)
    organ = OrganType(req.organ_type) if req.organ_type in OrganType.__members__.values() else OrganType.GENERAL

    config = InsertConfig(organ_type=organ)
    gen = InsertGenerator(config)
    positions = gen.analyze_positions(mesh, n_candidates=req.n_candidates)

    return {
        "model_id": req.model_id,
        "organ_type": organ.value,
        "positions": [p.to_dict() for p in positions],
        "n_found": len(positions),
    }


@router.post("/generate")
async def generate_inserts(req: GenerateInsertRequest):
    """生成支撑板（完整流程, 在线程池中执行避免阻塞）"""
    import asyncio

    mesh = _get_mesh(req.model_id)
    mold_shells = _get_mold_shells(req.mold_id)

    organ = OrganType(req.organ_type) if req.organ_type in OrganType.__members__.values() else OrganType.GENERAL
    anchor = None
    if req.anchor_type and req.anchor_type in AnchorType.__members__.values():
        anchor = AnchorType(req.anchor_type)

    itype = InsertType(req.insert_type) if req.insert_type in InsertType.__members__.values() else InsertType.FLAT

    config = InsertConfig(
        thickness=req.thickness,
        insert_type=itype,
        organ_type=organ,
        anchor_type=anchor,
        anchor_density=req.anchor_density,
        conformal_offset=req.conformal_offset,
        rib_height=req.rib_height,
        rib_spacing=req.rib_spacing,
        lattice_cell_size=req.lattice_cell_size,
        lattice_strut_diameter=req.lattice_strut_diameter,
        lattice_type=req.lattice_type,
    )

    gen = InsertGenerator(config)

    try:
        result = await asyncio.to_thread(
            gen.full_pipeline, mesh, mold_shells, req.n_plates,
        )
    except Exception as e:
        logger.exception("Insert generation failed")
        raise HTTPException(500, f"Insert generation error: {e}") from e

    insert_id = str(uuid.uuid4())[:8]
    _insert_results[insert_id] = {
        "result": result,
        "model_id": req.model_id,
        "mold_id": req.mold_id,
    }

    return {
        "insert_id": insert_id,
        "model_id": req.model_id,
        **result.to_dict(),
    }


@router.post("/anchor")
async def add_anchor_to_plate(req: AddAnchorRequest):
    """为已有支撑板添加/更换锚固结构"""
    stored = _insert_results.get(req.insert_id)
    if not stored:
        raise HTTPException(404, f"Insert {req.insert_id} not found")

    result = stored["result"]
    if req.plate_index >= len(result.plates):
        raise HTTPException(400, f"Plate index {req.plate_index} out of range")

    anchor_type = AnchorType(req.anchor_type) if req.anchor_type in AnchorType.__members__.values() else AnchorType.MESH_HOLES

    config = InsertConfig(
        anchor_type=anchor_type,
        anchor_density=req.anchor_density,
        anchor_feature_size=req.feature_size,
    )
    gen = InsertGenerator(config)
    plate = gen.add_anchor(result.plates[req.plate_index])

    return {
        "insert_id": req.insert_id,
        "plate_index": req.plate_index,
        "plate": plate.to_dict(),
    }


@router.post("/validate")
async def validate_assembly(req: ValidateRequest):
    """验证支撑板装配"""
    mesh = _get_mesh(req.model_id)
    stored = _insert_results.get(req.insert_id)
    if not stored:
        raise HTTPException(404, f"Insert {req.insert_id} not found")

    result = stored["result"]
    mold_shells_data = _get_mold_shells(req.mold_id)

    gen = InsertGenerator()
    is_valid, messages = gen.validate_assembly(mesh, result.plates, mold_shells_data)

    result.assembly_valid = is_valid
    result.validation_messages = messages

    return {
        "insert_id": req.insert_id,
        "assembly_valid": is_valid,
        "messages": messages,
    }


@router.get("/result/{insert_id}")
async def get_insert_result(insert_id: str):
    """获取支撑板结果"""
    stored = _insert_results.get(insert_id)
    if not stored:
        raise HTTPException(404, f"Insert {insert_id} not found")

    return {
        "insert_id": insert_id,
        "model_id": stored["model_id"],
        "mold_id": stored["mold_id"],
        **stored["result"].to_dict(),
    }


@router.get("/result/{insert_id}/plate/{plate_index}/glb")
async def get_insert_plate_glb(insert_id: str, plate_index: int):
    """获取支撑板 GLB 数据"""
    from fastapi.responses import Response

    stored = _insert_results.get(insert_id)
    if not stored:
        raise HTTPException(404, f"Insert {insert_id} not found")

    result = stored["result"]
    if plate_index >= len(result.plates):
        raise HTTPException(400, f"Plate index {plate_index} out of range")

    glb_bytes = result.plates[plate_index].mesh.to_glb()
    return Response(content=glb_bytes, media_type="model/gltf-binary")


@router.get("/list")
async def list_inserts():
    """列出所有生成的支撑板"""
    return {
        "inserts": [
            {
                "insert_id": k,
                "model_id": v["model_id"],
                "n_plates": len(v["result"].plates),
                "assembly_valid": v["result"].assembly_valid,
            }
            for k, v in _insert_results.items()
        ]
    }
