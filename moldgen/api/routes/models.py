"""模型上传、加载、编辑、导出 API"""

from __future__ import annotations

import asyncio
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
    import time as _time
    t0 = _time.perf_counter()
    config = get_config()
    config.ensure_dirs()

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_IMPORT:
        logger.warning("Upload rejected: unsupported format %s", suffix)
        raise HTTPException(400, f"Unsupported format: {suffix}")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    logger.info("Upload: %s (%.2f MB, %s)", file.filename, size_mb, suffix)
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
        logger.error("Failed to parse model %s: %s", file.filename, e)
        raise HTTPException(422, f"Failed to parse model: {e}") from e

    info = mesh.info()
    elapsed = _time.perf_counter() - t0
    logger.info(
        "Upload OK: id=%s faces=%d verts=%d watertight=%s (%.2fs)",
        model_id, info["face_count"], info["vertex_count"], info["is_watertight"], elapsed,
    )

    return {
        "model_id": model_id,
        "filename": file.filename,
        "format": suffix,
        "size_mb": round(size_mb, 2),
        "mesh_info": info,
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


class DesignRulesRequest(BaseModel):
    min_wall_thickness: float = 1.5
    min_feature_size: float = 0.5
    max_overhang_angle: float = 45.0
    min_draft_angle: float = 1.0
    min_clearance: float = 0.5


@router.post("/{model_id}/design-rules")
async def check_design_rules(model_id: str, req: DesignRulesRequest):
    """nTopology-style design rules validation."""
    mesh = _get_mesh(model_id)
    info = mesh.info()
    tm = mesh.to_trimesh()
    extents = tm.bounding_box.extents if tm.bounding_box is not None else [0, 0, 0]
    min_dim = float(min(extents))
    volume = float(tm.volume) if tm.is_watertight else 0.0
    sa = float(tm.area)

    rules = []

    rules.append({
        "id": "wall_thickness",
        "label": "最小壁厚",
        "threshold": req.min_wall_thickness,
        "value": round(min_dim * 0.05, 2),
        "unit": "mm",
        "pass": min_dim * 0.05 >= req.min_wall_thickness,
        "severity": "error" if min_dim * 0.05 < req.min_wall_thickness * 0.5 else "warning",
    })

    rules.append({
        "id": "watertight",
        "label": "水密网格",
        "threshold": True,
        "value": bool(tm.is_watertight),
        "unit": "",
        "pass": bool(tm.is_watertight),
        "severity": "error",
    })

    face_count = len(tm.faces)
    rules.append({
        "id": "mesh_density",
        "label": "网格密度",
        "threshold": 5000,
        "value": face_count,
        "unit": "面",
        "pass": face_count >= 5000,
        "severity": "warning" if face_count >= 1000 else "error",
    })

    rules.append({
        "id": "volume_valid",
        "label": "有效体积",
        "threshold": 0,
        "value": round(volume, 1),
        "unit": "mm³",
        "pass": volume > 0,
        "severity": "error",
    })

    aspect = float(max(extents) / max(min(extents), 0.01))
    rules.append({
        "id": "aspect_ratio",
        "label": "长宽比",
        "threshold": 10.0,
        "value": round(aspect, 1),
        "unit": "",
        "pass": aspect <= 10.0,
        "severity": "warning",
    })

    sa_vol_ratio = sa / max(volume, 1.0)
    rules.append({
        "id": "surface_to_volume",
        "label": "表面积/体积比",
        "threshold": 1.0,
        "value": round(sa_vol_ratio, 3),
        "unit": "1/mm",
        "pass": sa_vol_ratio < 1.0,
        "severity": "info",
    })

    pass_count = sum(1 for r in rules if r["pass"])
    return {
        "model_id": model_id,
        "rules": rules,
        "summary": {
            "total": len(rules),
            "passed": pass_count,
            "failed": len(rules) - pass_count,
            "score": round(pass_count / max(len(rules), 1) * 100),
        },
    }


class ThicknessAnalysisRequest(BaseModel):
    n_samples: int = 5000
    method: str = "ray"  # "ray" or "sphere"


@router.post("/{model_id}/thickness")
async def analyze_thickness(model_id: str, req: ThicknessAnalysisRequest):
    """nTopology-style wall thickness analysis via ray-based sampling.
    
    Shoots opposing rays from sampled surface points to measure local
    wall thickness.  Returns per-sample thickness values, statistics,
    and a thin-region heatmap.
    """
    import asyncio
    import numpy as np

    mesh = _get_mesh(model_id)
    tm = mesh.to_trimesh()
    if not tm.is_watertight:
        raise HTTPException(400, "Thickness analysis requires a watertight mesh")

    def _compute():
        n = min(req.n_samples, len(tm.faces) * 3)
        points, face_idx = tm.sample(n, return_index=True)
        normals = tm.face_normals[face_idx]

        thicknesses = np.full(len(points), np.nan)
        for i in range(len(points)):
            origin = points[i] + normals[i] * 0.01
            direction = -normals[i]
            locations, ray_idx, _ = tm.ray.intersects_location(
                [origin], [direction]
            )
            if len(locations) > 0:
                dists = np.linalg.norm(locations - points[i], axis=1)
                valid = dists > 0.02
                if valid.any():
                    thicknesses[i] = float(dists[valid].min())

        valid_mask = ~np.isnan(thicknesses)
        valid_t = thicknesses[valid_mask]
        if len(valid_t) == 0:
            return {"error": "No valid thickness samples obtained"}

        thin_threshold = float(np.percentile(valid_t, 10))
        thin_mask = valid_mask & (thicknesses < thin_threshold)

        return {
            "n_samples": int(valid_mask.sum()),
            "min": round(float(valid_t.min()), 3),
            "max": round(float(valid_t.max()), 3),
            "mean": round(float(valid_t.mean()), 3),
            "median": round(float(np.median(valid_t)), 3),
            "std": round(float(valid_t.std()), 3),
            "p5": round(float(np.percentile(valid_t, 5)), 3),
            "p10": round(float(np.percentile(valid_t, 10)), 3),
            "p90": round(float(np.percentile(valid_t, 90)), 3),
            "thin_threshold": round(thin_threshold, 3),
            "n_thin_regions": int(thin_mask.sum()),
            "thin_fraction": round(float(thin_mask.sum()) / max(len(valid_t), 1), 4),
            "histogram": {
                "bins": [round(float(b), 3) for b in np.linspace(valid_t.min(), valid_t.max(), 11)],
                "counts": [int(c) for c in np.histogram(valid_t, bins=10)[0]],
            },
            "samples": [
                {"x": round(float(p[0]), 2), "y": round(float(p[1]), 2), "z": round(float(p[2]), 2),
                 "thickness": round(float(thicknesses[i]), 3)}
                for i, p in enumerate(points[:200]) if valid_mask[i]
            ],
        }

    result = await asyncio.to_thread(_compute)
    return {"model_id": model_id, "thickness": result}


class DeviationAnalysisRequest(BaseModel):
    reference_model_id: str
    n_samples: int = 5000


@router.post("/{model_id}/deviation")
async def analyze_deviation(model_id: str, req: DeviationAnalysisRequest):
    """Mesh-to-mesh deviation analysis (nTopology Compare Bodies).
    
    Computes point-to-surface distance from the target mesh to a reference
    mesh.  Useful for checking how much a simplified/modified mesh deviates
    from the original.
    """
    import asyncio
    import numpy as np

    mesh_a = _get_mesh(model_id)
    mesh_b = _get_mesh(req.reference_model_id)
    tm_a = mesh_a.to_trimesh()
    tm_b = mesh_b.to_trimesh()

    def _compute():
        n = min(req.n_samples, len(tm_a.faces) * 3)
        points_a = tm_a.sample(n)
        closest, distances, _ = tm_b.nearest.on_surface(points_a)
        
        return {
            "n_samples": len(distances),
            "min_deviation": round(float(distances.min()), 4),
            "max_deviation": round(float(distances.max()), 4),
            "mean_deviation": round(float(distances.mean()), 4),
            "rms_deviation": round(float(np.sqrt((distances ** 2).mean())), 4),
            "median_deviation": round(float(np.median(distances)), 4),
            "p95_deviation": round(float(np.percentile(distances, 95)), 4),
            "histogram": {
                "bins": [round(float(b), 4) for b in np.linspace(distances.min(), distances.max(), 11)],
                "counts": [int(c) for c in np.histogram(distances, bins=10)[0]],
            },
        }

    result = await asyncio.to_thread(_compute)
    return {"model_id": model_id, "reference_id": req.reference_model_id, "deviation": result}


class CurvatureAnalysisRequest(BaseModel):
    n_samples: int = 3000


@router.post("/{model_id}/curvature")
async def analyze_curvature(model_id: str, req: CurvatureAnalysisRequest):
    """Surface curvature analysis for identifying feature regions."""
    import asyncio
    import numpy as np

    mesh = _get_mesh(model_id)
    tm = mesh.to_trimesh()

    def _compute():
        vn = tm.vertex_normals
        adj = tm.vertex_neighbors

        curvatures = np.zeros(len(tm.vertices))
        for i in range(min(len(tm.vertices), req.n_samples)):
            neighbors = adj[i]
            if len(neighbors) < 2:
                continue
            n_i = vn[i]
            angle_sum = 0.0
            for j in neighbors:
                cos_a = np.dot(n_i, vn[j])
                cos_a = np.clip(cos_a, -1.0, 1.0)
                angle_sum += np.arccos(cos_a)
            curvatures[i] = angle_sum / len(neighbors)

        valid = curvatures[:req.n_samples]
        valid = valid[valid > 0]

        flat_threshold = np.percentile(valid, 25) if len(valid) > 0 else 0
        curved_threshold = np.percentile(valid, 75) if len(valid) > 0 else 0

        return {
            "n_vertices": len(tm.vertices),
            "n_sampled": min(len(tm.vertices), req.n_samples),
            "min_curvature": round(float(valid.min()), 4) if len(valid) > 0 else 0,
            "max_curvature": round(float(valid.max()), 4) if len(valid) > 0 else 0,
            "mean_curvature": round(float(valid.mean()), 4) if len(valid) > 0 else 0,
            "flat_threshold": round(float(flat_threshold), 4),
            "curved_threshold": round(float(curved_threshold), 4),
            "flat_fraction": round(float((valid < flat_threshold).sum() / max(len(valid), 1)), 3),
            "curved_fraction": round(float((valid > curved_threshold).sum() / max(len(valid), 1)), 3),
        }

    result = await asyncio.to_thread(_compute)
    return {"model_id": model_id, "curvature": result}


@router.post("/{model_id}/repair")
async def repair_model(model_id: str):
    import time as _time
    t0 = _time.perf_counter()
    mesh = _get_mesh(model_id)
    logger.info("Repair: model=%s faces=%d", model_id, mesh.face_count)
    result = MeshRepair.repair(mesh)
    elapsed = _time.perf_counter() - t0
    if result.success:
        _loaded_meshes[model_id] = result.mesh
        logger.info(
            "Repair OK: model=%s actions=%s faces_after=%d (%.2fs)",
            model_id, result.actions, result.mesh.face_count, elapsed,
        )
    else:
        logger.warning("Repair: no changes applied for model=%s (%.2fs)", model_id, elapsed)
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
    import time as _time
    t0 = _time.perf_counter()
    mesh = _get_mesh(model_id)
    if req.target_faces and req.target_faces > 0:
        target = req.target_faces
    elif req.ratio and req.ratio > 0:
        target = max(4, int(mesh.face_count * req.ratio))
    else:
        raise HTTPException(400, "Provide target_faces or ratio")

    if target >= mesh.face_count:
        raise HTTPException(400, f"目标面数 {target} 不少于当前面数 {mesh.face_count}")

    logger.info("Simplify: model=%s %d→%d faces (ratio=%.2f)", model_id, mesh.face_count, target, target / mesh.face_count)
    try:
        result = await asyncio.to_thread(_editor.simplify_qem, mesh, target)
    except Exception as exc:
        logger.exception("Simplify failed: %s", exc)
        raise HTTPException(500, f"简化失败: {exc}") from exc

    elapsed = _time.perf_counter() - t0
    logger.info("Simplify OK: model=%s %d→%d faces (%.2fs)", model_id, mesh.face_count, result.face_count, elapsed)
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
