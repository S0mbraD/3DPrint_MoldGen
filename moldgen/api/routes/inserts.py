"""支撑板 API — 位置分析/生成/锚固/立柱/装配验证"""

from __future__ import annotations

import asyncio
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
    n_plates: int = 1
    mold_id: str | None = None
    internal_offset: float = 5.0
    plate_scale: float = 0.55
    conformal_offset: float = 3.0
    # Feature toggles
    add_mesh_holes: bool = False
    mesh_hole_size: float = 2.0
    hole_pattern: str = "hex"  # hex|grid|diamond|voronoi|gyroid|schwarz_p|schwarz_d|neovius|lidinoid|iwp|frd
    variable_density: bool = False
    density_field: str = "edge"  # edge|center|radial|stress|uniform
    tpms_cell_size: float | None = None
    tpms_z_slice: float = 0.0
    max_holes: int = 300
    add_ribs: bool = False
    rib_height: float = 3.0
    rib_spacing: float = 8.0
    add_interlocking: str | None = None
    interlock_feature_size: float = 2.0
    # Pillars
    pillar_diameter: float = 2.0
    pillar_count: int = 4
    pillar_side: str = "auto"
    # Manual hole planning (list of {u, v, radius} in mm relative to plate center)
    custom_hole_regions: list[dict] | None = None
    # Manual rib planning (list of {u, v, radius} in mm relative to plate center)
    custom_rib_regions: list[dict] | None = None
    # Legacy compat
    anchor_type: str | None = None
    anchor_density: float = 0.3
    skeleton_type: str | None = None


class ValidateRequest(BaseModel):
    model_id: str
    insert_id: str
    mold_id: str | None = None


@router.post("/analyze")
async def analyze_positions(req: AnalyzePositionsRequest):
    mesh = _get_mesh(req.model_id)
    organ = OrganType(req.organ_type) if req.organ_type in [e.value for e in OrganType] else OrganType.GENERAL
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
    mesh = _get_mesh(req.model_id)
    mold_shells = _get_mold_shells(req.mold_id)

    organ = OrganType(req.organ_type) if req.organ_type in [e.value for e in OrganType] else OrganType.GENERAL

    itype_str = req.skeleton_type or req.insert_type or "flat"
    try:
        itype = InsertType(itype_str)
    except ValueError:
        itype = InsertType.FLAT

    # Legacy anchor_type -> feature toggles mapping
    anchor = None
    if req.anchor_type and req.anchor_type in [e.value for e in AnchorType]:
        anchor = AnchorType(req.anchor_type)

    config = InsertConfig(
        thickness=req.thickness,
        insert_type=itype,
        organ_type=organ,
        anchor_type=anchor,
        anchor_density=req.anchor_density,
        internal_offset=req.internal_offset,
        plate_scale=req.plate_scale,
        conformal_offset=req.conformal_offset,
        add_mesh_holes=req.add_mesh_holes,
        mesh_hole_size=req.mesh_hole_size,
        hole_pattern=req.hole_pattern,
        variable_density=req.variable_density,
        density_field=req.density_field,
        tpms_cell_size=req.tpms_cell_size,
        tpms_z_slice=req.tpms_z_slice,
        max_holes=req.max_holes,
        add_ribs=req.add_ribs,
        rib_height=req.rib_height,
        rib_spacing=req.rib_spacing,
        add_interlocking=req.add_interlocking,
        interlock_feature_size=req.interlock_feature_size,
        pillar_diameter=req.pillar_diameter,
        pillar_count=req.pillar_count,
        pillar_side=req.pillar_side,
        custom_hole_regions=req.custom_hole_regions,
        custom_rib_regions=req.custom_rib_regions,
    )

    gen = InsertGenerator(config)
    try:
        result = await asyncio.to_thread(gen.full_pipeline, mesh, mold_shells, req.n_plates)
    except Exception as e:
        logger.exception("Insert generation failed")
        raise HTTPException(500, f"Insert generation error: {e}") from e

    # Cut pillar holes in mold shells if both inserts and mold exist
    if req.mold_id and result.plates:
        try:
            from moldgen.api.routes.molds import _mold_results
            from moldgen.core.mold_builder import MoldBuilder
            mold_result = _mold_results.get(req.mold_id)
            if mold_result and mold_result.shells:
                all_pillars = []
                for plate in result.plates:
                    for p in plate.pillars:
                        all_pillars.append(p.to_dict())
                if all_pillars:
                    builder = MoldBuilder()
                    mold_result.shells = builder.cut_pillar_holes(
                        mold_result.shells, all_pillars,
                    )
                    logger.info("Cut %d pillar holes in mold shells", len(all_pillars))
        except Exception as e:
            logger.warning("Failed to cut pillar holes in mold: %s", e)

    insert_id = str(uuid.uuid4())[:8]
    _insert_results[insert_id] = {"result": result, "model_id": req.model_id, "mold_id": req.mold_id}
    return {"insert_id": insert_id, "model_id": req.model_id, **result.to_dict()}


@router.post("/anchor")
async def add_anchor_to_plate(req: dict):
    return {"message": "Anchoring is now integrated into the generation pipeline"}


@router.post("/validate")
async def validate_assembly(req: ValidateRequest):
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
    return {"insert_id": req.insert_id, "assembly_valid": is_valid, "messages": messages}


@router.get("/result/{insert_id}")
async def get_insert_result(insert_id: str):
    stored = _insert_results.get(insert_id)
    if not stored:
        raise HTTPException(404, f"Insert {insert_id} not found")
    return {"insert_id": insert_id, "model_id": stored["model_id"], "mold_id": stored["mold_id"], **stored["result"].to_dict()}


@router.get("/result/{insert_id}/plate/{plate_index}/glb")
async def get_insert_plate_glb(insert_id: str, plate_index: int):
    from fastapi.responses import Response
    stored = _insert_results.get(insert_id)
    if not stored:
        raise HTTPException(404, f"Insert {insert_id} not found")
    result = stored["result"]
    if plate_index >= len(result.plates):
        raise HTTPException(400, f"Plate index {plate_index} out of range")
    glb_bytes = result.plates[plate_index].mesh.to_glb()
    return Response(content=glb_bytes, media_type="model/gltf-binary")


@router.get("/result/{insert_id}/plate/{plate_index}/pillars.glb")
async def get_pillar_glb(insert_id: str, plate_index: int):
    from fastapi.responses import Response
    stored = _insert_results.get(insert_id)
    if not stored:
        raise HTTPException(404, f"Insert {insert_id} not found")
    result = stored["result"]
    if plate_index >= len(result.plates):
        raise HTTPException(400, f"Plate index {plate_index} out of range")
    plate = result.plates[plate_index]
    if plate.pillar_mesh is None:
        raise HTTPException(404, "No pillar mesh available")
    glb_bytes = plate.pillar_mesh.to_glb()
    return Response(content=glb_bytes, media_type="model/gltf-binary")


@router.get("/list")
async def list_inserts():
    return {
        "inserts": [
            {"insert_id": k, "model_id": v["model_id"], "n_plates": len(v["result"].plates), "assembly_valid": v["result"].assembly_valid}
            for k, v in _insert_results.items()
        ]
    }
