"""模型上传、加载、编辑、导出 API"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from moldgen.config import get_config
from moldgen.core.mesh_data import MeshData
from moldgen.core.mesh_editor import MeshEditor
from moldgen.core.mesh_io import SUPPORTED_IMPORT, MeshIO
from moldgen.core.mesh_repair import MeshRepair

logger = logging.getLogger(__name__)
router = APIRouter()

_loaded_meshes: dict[str, MeshData] = {}
_editor = MeshEditor()


def _get_mesh(model_id: str) -> MeshData:
    if model_id not in _loaded_meshes:
        raise HTTPException(404, f"Model {model_id} not loaded. Upload and load first.")
    return _loaded_meshes[model_id]


# ─── Upload & Load ───────────────────────────────────


@router.post("/upload")
async def upload_model(file: UploadFile):
    """Upload a 3D model file, parse it, and return mesh info."""
    config = get_config()
    config.ensure_dirs()

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_IMPORT:
        raise HTTPException(400, f"Unsupported format: {suffix}")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > config.max_upload_size_mb:
        raise HTTPException(413, f"File too large: {size_mb:.1f}MB (max {config.max_upload_size_mb}MB)")

    model_id = uuid4().hex[:12]
    dest = config.upload_dir / f"{model_id}{suffix}"
    dest.write_bytes(content)

    try:
        mesh = MeshIO.load(dest)
        _loaded_meshes[model_id] = mesh
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"Failed to parse model: {e}") from e

    return {
        "model_id": model_id,
        "filename": file.filename,
        "format": suffix,
        "size_mb": round(size_mb, 2),
        "mesh_info": mesh.info(),
    }


@router.get("/")
async def list_models():
    config = get_config()
    config.ensure_dirs()
    files = []
    for f in config.upload_dir.iterdir():
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMPORT:
            files.append({
                "model_id": f.stem,
                "filename": f.name,
                "format": f.suffix.lower(),
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "loaded": f.stem in _loaded_meshes,
            })
    return {"models": files}


@router.get("/{model_id}")
async def get_model_info(model_id: str):
    mesh = _get_mesh(model_id)
    return {"model_id": model_id, "mesh_info": mesh.info()}


@router.get("/{model_id}/glb")
async def get_model_glb(model_id: str):
    """Return the model as GLB binary for frontend rendering."""
    mesh = _get_mesh(model_id)
    glb_data = mesh.to_glb()
    return Response(content=glb_data, media_type="model/gltf-binary")


# ─── Quality & Repair ────────────────────────────────


@router.get("/{model_id}/quality")
async def check_quality(model_id: str):
    mesh = _get_mesh(model_id)
    report = MeshRepair.check_quality(mesh)
    return {"model_id": model_id, "quality": report.to_dict()}


@router.post("/{model_id}/repair")
async def repair_model(model_id: str):
    mesh = _get_mesh(model_id)
    result = MeshRepair.repair(mesh)
    if result.success:
        _loaded_meshes[model_id] = result.mesh
    return {
        "model_id": model_id,
        "success": result.success,
        "actions": result.actions,
        "before": result.before.to_dict() if result.before else None,
        "after": result.after.to_dict() if result.after else None,
    }


# ─── Edit Operations ─────────────────────────────────


class SimplifyRequest(BaseModel):
    target_faces: int | None = None
    ratio: float | None = None


@router.post("/{model_id}/simplify")
async def simplify_model(model_id: str, req: SimplifyRequest):
    mesh = _get_mesh(model_id)
    if req.target_faces:
        result = _editor.simplify_qem(mesh, req.target_faces)
    elif req.ratio:
        result = _editor.simplify_ratio(mesh, req.ratio)
    else:
        raise HTTPException(400, "Provide target_faces or ratio")
    _loaded_meshes[model_id] = result
    return {"model_id": model_id, "mesh_info": result.info()}


class SubdivideRequest(BaseModel):
    max_edge: float | None = None
    iterations: int = 1


@router.post("/{model_id}/subdivide")
async def subdivide_model(model_id: str, req: SubdivideRequest):
    mesh = _get_mesh(model_id)
    if req.max_edge:
        result = _editor.subdivide_to_size(mesh, req.max_edge)
    else:
        result = _editor.subdivide_loop(mesh, req.iterations)
    _loaded_meshes[model_id] = result
    return {"model_id": model_id, "mesh_info": result.info()}


class TransformRequest(BaseModel):
    operation: str  # translate, rotate, scale, mirror, center, align_to_floor
    offset: list[float] | None = None
    axis: list[float] | None = None
    angle_deg: float | None = None
    factor: float | list[float] | None = None
    plane_normal: list[float] | None = None


@router.post("/{model_id}/transform")
async def transform_model(model_id: str, req: TransformRequest):
    mesh = _get_mesh(model_id)
    op = req.operation

    if op == "translate" and req.offset:
        result = _editor.translate(mesh, req.offset)
    elif op == "rotate" and req.axis is not None and req.angle_deg is not None:
        result = _editor.rotate(mesh, req.axis, req.angle_deg)
    elif op == "scale" and req.factor is not None:
        result = _editor.scale(mesh, req.factor)
    elif op == "mirror" and req.plane_normal:
        result = _editor.mirror(mesh, req.plane_normal)
    elif op == "center":
        result = _editor.center(mesh)
    elif op == "align_to_floor":
        result = _editor.align_to_floor(mesh)
    else:
        raise HTTPException(400, f"Invalid operation or missing params: {op}")

    _loaded_meshes[model_id] = result
    return {"model_id": model_id, "mesh_info": result.info()}


@router.post("/{model_id}/undo")
async def undo_edit(model_id: str):
    result = _editor.undo()
    if result is None:
        raise HTTPException(400, "Nothing to undo")
    _loaded_meshes[model_id] = result
    return {"model_id": model_id, "mesh_info": result.info()}


# ─── Export ───────────────────────────────────────────


class ExportRequest(BaseModel):
    format: str = "stl"


@router.post("/{model_id}/export")
async def export_model(model_id: str, req: ExportRequest):
    mesh = _get_mesh(model_id)
    config = get_config()
    suffix = req.format if req.format.startswith(".") else f".{req.format}"
    export_path = config.data_dir / "exports" / f"{model_id}{suffix}"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    MeshIO.export(mesh, export_path)
    return {"model_id": model_id, "path": str(export_path), "format": suffix}
