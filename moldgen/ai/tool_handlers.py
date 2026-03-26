"""Tool handler 实现 — 将 ToolRegistry 的工具连接到实际核心算法

每个 handler 接受与 ToolDef.parameters 匹配的 kwargs，
返回序列化友好的 dict，由 ToolResult.data 包装。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory state (shared with API routes) ──────────────────────────

def _get_loaded_meshes() -> dict:
    from moldgen.api.routes.models import _loaded_meshes
    return _loaded_meshes


def _get_mold_results() -> dict:
    from moldgen.api.routes.molds import _mold_results
    return _mold_results


def _get_insert_results() -> dict:
    from moldgen.api.routes.inserts import _insert_results
    return _insert_results


def _require_mesh(model_id: str):
    meshes = _get_loaded_meshes()
    mesh = meshes.get(model_id)
    if mesh is None:
        raise ValueError(f"模型 {model_id} 未加载。请先上传或加载模型。")
    return mesh


# ═══════════════════════════════════════════════════════════════════════
#  Model tool handlers
# ═══════════════════════════════════════════════════════════════════════

def handle_model_load(file_path: str, **_: Any) -> dict:
    from moldgen.core.mesh_io import MeshIO
    import uuid
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    mesh = MeshIO.load(str(p))
    model_id = str(uuid.uuid4())[:8]
    _get_loaded_meshes()[model_id] = mesh
    return {"model_id": model_id, "filename": p.name, **mesh.info()}


def handle_model_quality_check(model_id: str, **_: Any) -> dict:
    from moldgen.core.mesh_repair import MeshRepair
    mesh = _require_mesh(model_id)
    report = MeshRepair.check_quality(mesh)
    data = report.to_dict()
    data["model_id"] = model_id
    data["needs_repair"] = not report.is_watertight or report.degenerate_faces > 0
    return data


def handle_model_repair(model_id: str, **_: Any) -> dict:
    from moldgen.core.mesh_repair import MeshRepair
    mesh = _require_mesh(model_id)
    result = MeshRepair.repair(mesh)
    _get_loaded_meshes()[model_id] = result.mesh
    return {
        "model_id": model_id,
        "success": result.success,
        "actions": result.actions,
        "before": result.before.to_dict() if result.before else None,
        "after": result.after.to_dict() if result.after else None,
    }


def handle_model_simplify(model_id: str, target_faces: int | None = None, ratio: float = 0.5, **_: Any) -> dict:
    from moldgen.core.mesh_editor import MeshEditor
    mesh = _require_mesh(model_id)
    editor = MeshEditor()
    before = mesh.face_count
    if target_faces:
        result = editor.simplify_qem(mesh, target_faces)
    else:
        result = editor.simplify_ratio(mesh, ratio)
    _get_loaded_meshes()[model_id] = result
    return {
        "model_id": model_id,
        "faces_before": before,
        "faces_after": result.face_count,
        "reduction": round(1 - result.face_count / max(before, 1), 3),
    }


def handle_model_subdivide(model_id: str, iterations: int = 1, **_: Any) -> dict:
    from moldgen.core.mesh_editor import MeshEditor
    mesh = _require_mesh(model_id)
    editor = MeshEditor()
    before = mesh.face_count
    result = editor.subdivide_loop(mesh, iterations)
    _get_loaded_meshes()[model_id] = result
    return {
        "model_id": model_id,
        "faces_before": before,
        "faces_after": result.face_count,
        "iterations": iterations,
    }


def handle_model_transform(model_id: str, operation: str, params: dict | None = None, **_: Any) -> dict:
    from moldgen.core.mesh_editor import MeshEditor
    mesh = _require_mesh(model_id)
    editor = MeshEditor()
    params = params or {}

    ops = {
        "center": lambda: editor.center(mesh),
        "align_to_floor": lambda: editor.align_to_floor(mesh),
        "translate": lambda: editor.translate(mesh, params.get("offset", [0, 0, 0])),
        "rotate": lambda: editor.rotate(mesh, params.get("axis", [0, 0, 1]), params.get("angle_deg", 0)),
        "scale": lambda: editor.scale(mesh, params.get("factor", 1.0)),
        "mirror": lambda: editor.mirror(mesh, params.get("plane_normal", [1, 0, 0])),
    }

    fn = ops.get(operation)
    if not fn:
        raise ValueError(f"未知变换操作: {operation}")

    result = fn()
    _get_loaded_meshes()[model_id] = result
    return {"model_id": model_id, "operation": operation, "applied": True}


def handle_model_boolean(model_id_a: str, model_id_b: str, operation: str, **_: Any) -> dict:
    from moldgen.core.mesh_editor import MeshEditor
    mesh_a = _require_mesh(model_id_a)
    mesh_b = _require_mesh(model_id_b)
    editor = MeshEditor()
    result = editor._boolean_op(mesh_a, mesh_b, operation)
    import uuid
    new_id = str(uuid.uuid4())[:8]
    _get_loaded_meshes()[new_id] = result
    return {"result_model_id": new_id, "operation": operation, "faces": result.face_count}


def handle_model_get_info(model_id: str, **_: Any) -> dict:
    mesh = _require_mesh(model_id)
    return {"model_id": model_id, **mesh.info()}


def handle_model_undo(model_id: str, **_: Any) -> dict:
    from moldgen.api.routes.models import _editor
    result = _editor.undo()
    if result is None:
        raise ValueError("没有可撤销的操作")
    _get_loaded_meshes()[model_id] = result
    return {"model_id": model_id, **result.info()}


# ═══════════════════════════════════════════════════════════════════════
#  Mold tool handlers
# ═══════════════════════════════════════════════════════════════════════

def handle_mold_analyze_orientation(model_id: str, n_samples: int = 100, **_: Any) -> dict:
    from moldgen.core.orientation import OrientationAnalyzer, OrientationConfig
    mesh = _require_mesh(model_id)
    config = OrientationConfig(n_fibonacci_samples=n_samples)
    analyzer = OrientationAnalyzer(config)
    result = analyzer.analyze(mesh)
    from moldgen.api.routes.molds import _orientation_results
    _orientation_results[model_id] = result
    return {
        "model_id": model_id,
        **result.to_dict(),
    }


def handle_mold_evaluate_direction(model_id: str, direction: list, **_: Any) -> dict:
    from moldgen.core.orientation import OrientationAnalyzer
    import numpy as np
    mesh = _require_mesh(model_id)
    analyzer = OrientationAnalyzer()
    d = np.array(direction, dtype=float)
    score = analyzer.evaluate_direction(mesh, d)
    return {"model_id": model_id, "direction": direction, **score.to_dict()}


def handle_mold_generate_parting(model_id: str, direction: list | None = None, **_: Any) -> dict:
    from moldgen.core.parting import PartingGenerator
    import numpy as np
    mesh = _require_mesh(model_id)
    d = np.array(direction, dtype=float) if direction else np.array([0, 0, 1.0])
    gen = PartingGenerator()
    result = gen.generate(mesh, d)
    from moldgen.api.routes.molds import _parting_results
    _parting_results[model_id] = result
    return {"model_id": model_id, **result.to_dict()}


def handle_mold_build_two_part(
    model_id: str, direction: list | None = None,
    wall_thickness: float = 4.0, shell_type: str = "box", **_: Any
) -> dict:
    from moldgen.core.mold_builder import MoldBuilder, MoldConfig
    import numpy as np, uuid
    mesh = _require_mesh(model_id)
    d = np.array(direction, dtype=float) if direction else np.array([0, 0, 1.0])
    config = MoldConfig(wall_thickness=wall_thickness, shell_type=shell_type)
    builder = MoldBuilder(config)
    result = builder.build_two_part_mold(mesh, d)
    mid = str(uuid.uuid4())[:8]
    _get_mold_results()[mid] = result
    return {
        "mold_id": mid,
        "model_id": model_id,
        **result.to_dict(),
    }


def handle_mold_build_multi_part(
    model_id: str, directions: list, wall_thickness: float = 4.0, **_: Any
) -> dict:
    from moldgen.core.mold_builder import MoldBuilder, MoldConfig
    import numpy as np, uuid
    mesh = _require_mesh(model_id)
    dirs = [np.array(d, dtype=float) for d in directions]
    config = MoldConfig(wall_thickness=wall_thickness)
    builder = MoldBuilder(config)
    result = builder.build_multi_part_mold(mesh, dirs)
    mid = str(uuid.uuid4())[:8]
    _get_mold_results()[mid] = result
    return {
        "mold_id": mid,
        "model_id": model_id,
        **result.to_dict(),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Insert tool handlers
# ═══════════════════════════════════════════════════════════════════════

def handle_insert_analyze_positions(
    model_id: str, n_candidates: int = 5, organ_type: str = "general", **_: Any
) -> dict:
    from moldgen.core.insert_generator import InsertGenerator, InsertConfig, OrganType
    mesh = _require_mesh(model_id)
    organ = OrganType(organ_type) if organ_type in [e.value for e in OrganType] else OrganType.GENERAL
    config = InsertConfig(organ_type=organ)
    gen = InsertGenerator(config)
    positions = gen.analyze_positions(mesh, n_candidates=n_candidates)
    return {
        "model_id": model_id,
        "candidates": [p.to_dict() for p in positions],
        "organ_type": organ.value,
    }


def handle_insert_generate(
    model_id: str, n_plates: int = 1, thickness: float = 2.0,
    organ_type: str = "general", anchor_type: str = "mesh_holes",
    mold_id: str | None = None, **_: Any
) -> dict:
    from moldgen.core.insert_generator import InsertGenerator, InsertConfig, OrganType
    import uuid
    mesh = _require_mesh(model_id)
    organ = OrganType(organ_type) if organ_type in [e.value for e in OrganType] else OrganType.GENERAL
    config = InsertConfig(thickness=thickness, organ_type=organ)
    gen = InsertGenerator(config)

    mold_shells = None
    if mold_id:
        mold = _get_mold_results().get(mold_id)
        if mold and hasattr(mold, 'shells'):
            mold_shells = [s.mesh if hasattr(s, 'mesh') else s for s in mold.shells]

    result = gen.full_pipeline(mesh, mold_shells=mold_shells, n_plates=n_plates)

    iid = str(uuid.uuid4())[:8]
    _get_insert_results()[iid] = {"result": result, "model_id": model_id, "mold_id": mold_id}
    return {
        "insert_id": iid,
        "model_id": model_id,
        "plates_count": len(result.plates),
        **result.to_dict(),
    }


def handle_insert_validate(model_id: str, insert_id: str, mold_id: str | None = None, **_: Any) -> dict:
    mesh = _require_mesh(model_id)
    stored = _get_insert_results().get(insert_id)
    if not stored:
        raise ValueError(f"支撑板结果 {insert_id} 不存在")
    result = stored["result"]
    from moldgen.core.insert_generator import InsertGenerator

    mold_shells = None
    if mold_id:
        mold = _get_mold_results().get(mold_id)
        if mold and hasattr(mold, 'shells'):
            mold_shells = [s.mesh if hasattr(s, 'mesh') else s for s in mold.shells]

    gen = InsertGenerator()
    is_valid, messages = gen.validate_assembly(mesh, result.plates, mold_shells)
    return {
        "insert_id": insert_id,
        "valid": is_valid,
        "messages": messages,
    }


def handle_insert_add_anchor(insert_id: str, plate_index: int = 0, anchor_type: str = "mesh_holes", **_: Any) -> dict:
    stored = _get_insert_results().get(insert_id)
    if not stored:
        raise ValueError(f"支撑板结果 {insert_id} 不存在")
    result = stored["result"]
    if plate_index >= len(result.plates):
        raise ValueError(f"板索引 {plate_index} 超出范围")
    from moldgen.core.insert_generator import InsertGenerator, InsertConfig, AnchorType
    try:
        atype = AnchorType(anchor_type)
    except ValueError:
        atype = AnchorType.MESH_HOLES
    config = InsertConfig(anchor_type=atype)
    gen = InsertGenerator(config)
    plate = result.plates[plate_index]
    updated = gen.add_anchor(plate)
    result.plates[plate_index] = updated
    return {
        "insert_id": insert_id,
        "plate_index": plate_index,
        "anchor_type": anchor_type,
        "applied": True,
    }


def handle_insert_get_info(insert_id: str, **_: Any) -> dict:
    stored = _get_insert_results().get(insert_id)
    if not stored:
        raise ValueError(f"支撑板结果 {insert_id} 不存在")
    result = stored["result"]
    return {
        "insert_id": insert_id,
        "plates_count": len(result.plates),
        **result.to_dict(),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Simulation tool handlers
# ═══════════════════════════════════════════════════════════════════════

def handle_sim_design_gating(
    model_id: str, mold_id: str, material: str = "silicone_a30", **_: Any
) -> dict:
    from moldgen.core.gating import GatingSystem
    from moldgen.core.material import MATERIAL_PRESETS
    import uuid
    mesh = _require_mesh(model_id)
    mold = _get_mold_results().get(mold_id)
    if not mold:
        raise ValueError(f"模具 {mold_id} 不存在")
    gating = GatingSystem()
    mat = MATERIAL_PRESETS.get(material, MATERIAL_PRESETS["silicone_a30"])
    result = gating.design(mold, mesh, mat)
    gid = str(uuid.uuid4())[:8]
    from moldgen.api.routes.simulation import _gating_results
    _gating_results[gid] = result
    return {
        "gating_id": gid,
        "material": material,
        **result.to_dict(),
    }


def handle_sim_run(
    model_id: str, gating_id: str, material: str = "silicone_a30", level: int = 1, **_: Any
) -> dict:
    from moldgen.core.flow_sim import FlowSimulator, SimConfig
    from moldgen.core.material import MATERIAL_PRESETS
    import uuid
    mesh = _require_mesh(model_id)
    from moldgen.api.routes.simulation import _gating_results
    gating = _gating_results.get(gating_id)
    if not gating:
        raise ValueError(f"浇注系统 {gating_id} 不存在")
    mat = MATERIAL_PRESETS.get(material, MATERIAL_PRESETS["silicone_a30"])
    sim = FlowSimulator(SimConfig(level=level))
    result = sim.simulate(mesh, gating, mat)
    sid = str(uuid.uuid4())[:8]
    from moldgen.api.routes.simulation import _sim_results
    _sim_results[sid] = result
    return {
        "sim_id": sid,
        "level": level,
        **result.to_dict(),
    }


def handle_sim_optimize(
    model_id: str, mold_id: str, gating_id: str,
    material: str = "silicone_a30", max_iterations: int = 5, **_: Any
) -> dict:
    from moldgen.core.optimizer import AutoOptimizer
    from moldgen.core.material import MATERIAL_PRESETS
    mesh = _require_mesh(model_id)
    mold = _get_mold_results().get(mold_id)
    from moldgen.api.routes.simulation import _gating_results
    gating = _gating_results.get(gating_id)
    if not mold or not gating:
        raise ValueError("模具或浇注系统不存在")
    mat = MATERIAL_PRESETS.get(material, MATERIAL_PRESETS["silicone_a30"])
    optimizer = AutoOptimizer()
    result = optimizer.optimize(
        model=mesh, mold=mold, material=mat, initial_gating=gating,
        max_iterations=max_iterations,
    )
    return result.to_dict()


def handle_sim_list_materials(**_: Any) -> dict:
    from moldgen.core.material import MATERIAL_PRESETS
    return {
        "materials": [
            {"id": mid, **mat.to_dict()}
            for mid, mat in MATERIAL_PRESETS.items()
        ]
    }


# ═══════════════════════════════════════════════════════════════════════
#  Export tool handlers
# ═══════════════════════════════════════════════════════════════════════

def handle_export_model(model_id: str, format: str = "stl", output_dir: str | None = None, **_: Any) -> dict:
    from moldgen.core.mesh_io import MeshIO
    mesh = _require_mesh(model_id)
    from moldgen.config import get_config
    out = Path(output_dir) if output_dir else get_config().data_dir / "exports"
    out.mkdir(parents=True, exist_ok=True)
    filename = f"{model_id}.{format}"
    filepath = out / filename
    MeshIO.export(mesh, str(filepath), file_format=format)
    return {"path": str(filepath), "format": format, "size_kb": round(filepath.stat().st_size / 1024, 1)}


def handle_export_mold_shells(mold_id: str, format: str = "stl", **_: Any) -> dict:
    from moldgen.core.mesh_io import MeshIO
    from moldgen.config import get_config
    mold = _get_mold_results().get(mold_id)
    if not mold:
        raise ValueError(f"模具 {mold_id} 不存在")
    out = get_config().data_dir / "exports" / mold_id
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, shell in enumerate(mold.shells):
        fp = out / f"shell_{i}.{format}"
        mesh_data = shell.mesh if hasattr(shell, 'mesh') else shell
        MeshIO.export(mesh_data, str(fp), file_format=format)
        paths.append(str(fp))
    return {"mold_id": mold_id, "paths": paths, "shell_count": len(paths)}


# ═══════════════════════════════════════════════════════════════════════
#  Registration function
# ═══════════════════════════════════════════════════════════════════════

HANDLER_MAP: dict[str, Any] = {
    "model_load": handle_model_load,
    "model_quality_check": handle_model_quality_check,
    "model_repair": handle_model_repair,
    "model_simplify": handle_model_simplify,
    "model_subdivide": handle_model_subdivide,
    "model_transform": handle_model_transform,
    "model_boolean": handle_model_boolean,
    "model_get_info": handle_model_get_info,
    "model_undo": handle_model_undo,
    "mold_analyze_orientation": handle_mold_analyze_orientation,
    "mold_evaluate_direction": handle_mold_evaluate_direction,
    "mold_generate_parting": handle_mold_generate_parting,
    "mold_build_two_part": handle_mold_build_two_part,
    "mold_build_multi_part": handle_mold_build_multi_part,
    "insert_analyze_positions": handle_insert_analyze_positions,
    "insert_generate": handle_insert_generate,
    "insert_validate": handle_insert_validate,
    "insert_add_anchor": handle_insert_add_anchor,
    "insert_get_info": handle_insert_get_info,
    "sim_design_gating": handle_sim_design_gating,
    "sim_run": handle_sim_run,
    "sim_optimize": handle_sim_optimize,
    "sim_list_materials": handle_sim_list_materials,
    "export_model": handle_export_model,
    "export_mold_shells": handle_export_mold_shells,
}


def wire_handlers() -> int:
    """Wire all handlers into the ToolRegistry. Returns count of handlers wired."""
    from moldgen.ai.tool_registry import ToolRegistry
    registry = ToolRegistry()
    wired = 0
    for name, handler in HANDLER_MAP.items():
        tool = registry.get(name)
        if tool:
            tool.handler = handler
            wired += 1
            logger.debug("Wired handler for tool: %s", name)
        else:
            logger.warning("Tool %s not in registry, skipping handler", name)
    logger.info("Wired %d/%d tool handlers", wired, len(HANDLER_MAP))
    return wired
