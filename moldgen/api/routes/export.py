"""多格式导出接口 — 模型/模具壳体/支撑板批量导出"""

from __future__ import annotations

import io
import logging
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_mesh(model_id: str):
    from moldgen.api.routes.models import _loaded_meshes
    mesh = _loaded_meshes.get(model_id)
    if not mesh:
        raise HTTPException(404, f"Model {model_id} not found")
    return mesh


EXPORT_FORMATS = ["stl", "obj", "ply", "glb", "3mf"]


class ExportModelRequest(BaseModel):
    model_id: str
    format: str = "stl"


class ExportMoldRequest(BaseModel):
    mold_id: str
    format: str = "stl"
    include_model: bool = False
    model_id: str | None = None


class ExportInsertRequest(BaseModel):
    insert_id: str
    format: str = "stl"


class ExportAllRequest(BaseModel):
    model_id: str | None = None
    mold_id: str | None = None
    insert_id: str | None = None
    format: str = "stl"


@router.get("/formats")
async def list_export_formats():
    return {"formats": EXPORT_FORMATS}


@router.post("/model")
async def export_model(req: ExportModelRequest):
    """导出模型文件"""
    if req.format not in EXPORT_FORMATS:
        raise HTTPException(400, f"Unsupported format: {req.format}")

    mesh = _get_mesh(req.model_id)
    tm = mesh.to_trimesh()

    buf = io.BytesIO()
    tm.export(buf, file_type=req.format)
    buf.seek(0)

    mime = _get_mime(req.format)
    filename = f"model_{req.model_id}.{req.format}"

    return Response(
        content=buf.getvalue(),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/mold")
async def export_mold(req: ExportMoldRequest):
    """导出模具壳体（ZIP 包含所有壳体）"""
    from moldgen.api.routes.molds import _mold_results

    if req.format not in EXPORT_FORMATS:
        raise HTTPException(400, f"Unsupported format: {req.format}")

    mold = _mold_results.get(req.mold_id)
    if not mold:
        raise HTTPException(404, f"Mold {req.mold_id} not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for shell in mold.shells:
            shell_tm = shell.mesh.to_trimesh()
            shell_buf = io.BytesIO()
            shell_tm.export(shell_buf, file_type=req.format)
            zf.writestr(f"shell_{shell.shell_id}.{req.format}", shell_buf.getvalue())

        if req.include_model and req.model_id:
            model_mesh = _get_mesh(req.model_id)
            model_tm = model_mesh.to_trimesh()
            model_buf = io.BytesIO()
            model_tm.export(model_buf, file_type=req.format)
            zf.writestr(f"original_model.{req.format}", model_buf.getvalue())

    buf.seek(0)
    filename = f"mold_{req.mold_id}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/insert")
async def export_insert(req: ExportInsertRequest):
    """导出支撑板（ZIP 包含所有板）"""
    from moldgen.api.routes.inserts import _insert_results

    if req.format not in EXPORT_FORMATS:
        raise HTTPException(400, f"Unsupported format: {req.format}")

    stored = _insert_results.get(req.insert_id)
    if not stored:
        raise HTTPException(404, f"Insert {req.insert_id} not found")

    result = stored["result"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, plate in enumerate(result.plates):
            plate_tm = plate.mesh.to_trimesh()
            plate_buf = io.BytesIO()
            plate_tm.export(plate_buf, file_type=req.format)
            zf.writestr(f"insert_plate_{i}.{req.format}", plate_buf.getvalue())

    buf.seek(0)
    filename = f"inserts_{req.insert_id}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/all")
async def export_all(req: ExportAllRequest):
    """一键导出全部（模型+模具+支撑板 ZIP）"""
    from moldgen.api.routes.inserts import _insert_results
    from moldgen.api.routes.molds import _mold_results

    if req.format not in EXPORT_FORMATS:
        raise HTTPException(400, f"Unsupported format: {req.format}")

    buf = io.BytesIO()
    file_count = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if req.model_id:
            try:
                mesh = _get_mesh(req.model_id)
                tm = mesh.to_trimesh()
                model_buf = io.BytesIO()
                tm.export(model_buf, file_type=req.format)
                zf.writestr(f"model/original.{req.format}", model_buf.getvalue())
                file_count += 1
            except HTTPException:
                pass

        if req.mold_id:
            mold = _mold_results.get(req.mold_id)
            if mold:
                for shell in mold.shells:
                    shell_tm = shell.mesh.to_trimesh()
                    shell_buf = io.BytesIO()
                    shell_tm.export(shell_buf, file_type=req.format)
                    zf.writestr(f"mold/shell_{shell.shell_id}.{req.format}", shell_buf.getvalue())
                    file_count += 1

        if req.insert_id:
            stored = _insert_results.get(req.insert_id)
            if stored:
                for i, plate in enumerate(stored["result"].plates):
                    plate_tm = plate.mesh.to_trimesh()
                    plate_buf = io.BytesIO()
                    plate_tm.export(plate_buf, file_type=req.format)
                    zf.writestr(f"inserts/plate_{i}.{req.format}", plate_buf.getvalue())
                    file_count += 1

    if file_count == 0:
        raise HTTPException(400, "No data to export")

    buf.seek(0)
    filename = "moldgen_export.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _get_mime(fmt: str) -> str:
    return {
        "stl": "application/sla",
        "obj": "text/plain",
        "ply": "application/octet-stream",
        "glb": "model/gltf-binary",
        "3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
    }.get(fmt, "application/octet-stream")
