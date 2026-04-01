"""API integration tests"""

import io
import struct

from fastapi.testclient import TestClient

from moldgen.main import app

client = TestClient(app)


def _make_stl_bytes() -> bytes:
    """Create a minimal valid binary STL with a single triangle."""
    header = b"\x00" * 80
    num_triangles = struct.pack("<I", 1)
    normal = struct.pack("<fff", 0.0, 0.0, 1.0)
    v1 = struct.pack("<fff", 0.0, 0.0, 0.0)
    v2 = struct.pack("<fff", 10.0, 0.0, 0.0)
    v3 = struct.pack("<fff", 5.0, 10.0, 0.0)
    attr = struct.pack("<H", 0)
    return header + num_triangles + normal + v1 + v2 + v3 + attr


def _make_box_stl_bytes() -> bytes:
    """Create a box STL via trimesh and return bytes."""
    import trimesh
    box = trimesh.creation.box(extents=[10, 10, 10])
    buf = io.BytesIO()
    box.export(buf, file_type="stl")
    return buf.getvalue()


# ─── System ──────────────────────────────────────────


def test_health():
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_system_info():
    resp = client.get("/api/v1/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "gpu" in data
    assert "version" in data


def test_gpu_status():
    resp = client.get("/api/v1/system/gpu")
    assert resp.status_code == 200
    assert "total_mb" in resp.json()


# ─── Models Upload & Load ────────────────────────────


def test_upload_stl():
    stl = _make_box_stl_bytes()
    resp = client.post(
        "/api/v1/models/upload",
        files={"file": ("box.stl", io.BytesIO(stl), "application/octet-stream")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "model_id" in data
    assert data["format"] == ".stl"
    assert "mesh_info" in data
    assert data["mesh_info"]["face_count"] == 12
    assert data["mesh_info"]["is_watertight"] is True
    return data["model_id"]


def test_upload_unsupported_format():
    resp = client.post(
        "/api/v1/models/upload",
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


def test_list_models():
    resp = client.get("/api/v1/models/")
    assert resp.status_code == 200
    assert "models" in resp.json()


# ─── Model Operations ────────────────────────────────


def test_model_quality_and_repair():
    model_id = test_upload_stl()

    resp = client.get(f"/api/v1/models/{model_id}/quality")
    assert resp.status_code == 200
    quality = resp.json()["quality"]
    assert quality["face_count"] == 12
    assert quality["is_watertight"] is True

    resp = client.post(f"/api/v1/models/{model_id}/repair")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_model_simplify():
    model_id = test_upload_stl()
    resp = client.post(
        f"/api/v1/models/{model_id}/simplify",
        json={"target_faces": 8},
    )
    assert resp.status_code == 200
    assert resp.json()["mesh_info"]["face_count"] <= 12


def test_model_transform():
    model_id = test_upload_stl()

    resp = client.post(
        f"/api/v1/models/{model_id}/transform",
        json={"operation": "center"},
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/api/v1/models/{model_id}/transform",
        json={"operation": "scale", "factor": 2.0},
    )
    assert resp.status_code == 200
    info = resp.json()["mesh_info"]
    assert max(info["extents"]) > 15  # was 10, now ~20


def test_model_glb():
    model_id = test_upload_stl()
    resp = client.get(f"/api/v1/models/{model_id}/glb")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/gltf-binary"
    assert len(resp.content) > 100


def test_model_export():
    model_id = test_upload_stl()
    resp = client.post(
        f"/api/v1/models/{model_id}/export",
        json={"format": "obj"},
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == ".obj"


# ─── AI (structural) ─────────────────────────────────


def test_ai_chat_status():
    resp = client.get("/api/v1/ai/chat/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "services" in data
    assert "deepseek" in data["services"]


def test_agent_list():
    resp = client.get("/api/v1/ai/agent/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["agents"]) == 6
    roles = [a["role"] for a in data["agents"]]
    assert "master" in roles
    assert "model" in roles


def test_agent_execute():
    resp = client.post("/api/v1/ai/agent/execute", json={
        "request": "你好",
        "mode": "auto",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]


def test_agent_classify():
    resp = client.get("/api/v1/ai/agent/classify?task=修复模型")
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_agent"] == "model"


def test_agent_pipelines():
    resp = client.get("/api/v1/ai/agent/pipelines")
    assert resp.status_code == 200
    data = resp.json()
    assert "full_from_model" in data["pipelines"]


def test_agent_tools():
    resp = client.get("/api/v1/ai/agent/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 10
    assert "model" in data["categories"]


def test_agent_execute_single():
    resp = client.post("/api/v1/ai/agent/execute/single", json={
        "agent": "creative",
        "task": "生成心脏模型",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    assert "optimized_prompt" in data["output"]


# ─── Phase 2: Mold Generation ─────────────────────────


def test_orientation_analysis():
    model_id = test_upload_stl()
    resp = client.post(
        f"/api/v1/molds/{model_id}/orientation",
        json={"n_samples": 20, "n_final": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    r = data["result"]
    assert len(r["best_direction"]) == 3
    assert r["best_score"]["total_score"] > 0
    assert len(r["top_candidates"]) <= 3


def test_evaluate_direction():
    model_id = test_upload_stl()
    resp = client.post(
        f"/api/v1/molds/{model_id}/orientation/evaluate",
        json={"direction": [0, 0, 1]},
    )
    assert resp.status_code == 200
    assert resp.json()["score"]["visibility_ratio"] > 0


def test_parting_generation():
    model_id = test_upload_stl()
    # Run orientation first
    client.post(
        f"/api/v1/molds/{model_id}/orientation",
        json={"n_samples": 20, "n_final": 3},
    )
    resp = client.post(f"/api/v1/molds/{model_id}/parting")
    assert resp.status_code == 200
    data = resp.json()["result"]
    assert data["n_upper_faces"] > 0 or data["n_lower_faces"] > 0


def test_parting_with_explicit_direction():
    model_id = test_upload_stl()
    resp = client.post(
        f"/api/v1/molds/{model_id}/parting",
        json={"direction": [0, 0, 1]},
    )
    assert resp.status_code == 200


def test_mold_generation():
    model_id = test_upload_stl()
    resp = client.post(
        f"/api/v1/molds/{model_id}/mold/generate",
        json={"direction": [0, 0, 1], "wall_thickness": 3.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "mold_id" in data
    assert data["result"]["n_shells"] >= 1


def test_mold_shell_glb():
    model_id = test_upload_stl()
    resp = client.post(
        f"/api/v1/molds/{model_id}/mold/generate",
        json={"direction": [0, 0, 1]},
    )
    mold_id = resp.json()["mold_id"]
    shell_id = resp.json()["result"]["shells"][0]["shell_id"]

    resp = client.get(f"/api/v1/molds/result/{mold_id}/shell/{shell_id}/glb")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/gltf-binary"


def test_list_molds():
    resp = client.get("/api/v1/molds/")
    assert resp.status_code == 200
    assert "molds" in resp.json()


# ─── Phase 3: Simulation ──────────────────────────────


def _setup_mold_and_model():
    """Helper: upload model + generate mold, return (model_id, mold_id)."""
    model_id = test_upload_stl()
    resp = client.post(
        f"/api/v1/molds/{model_id}/mold/generate",
        json={"direction": [0, 0, 1]},
    )
    return model_id, resp.json()["mold_id"]


def test_list_materials():
    resp = client.get("/api/v1/simulation/materials")
    assert resp.status_code == 200
    data = resp.json()["materials"]
    assert "silicone_a30" in data
    assert "epoxy_resin" in data


def test_gating_design():
    model_id, mold_id = _setup_mold_and_model()
    resp = client.post(
        "/api/v1/simulation/gating/design",
        json={"model_id": model_id, "mold_id": mold_id, "material": "silicone_a30"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "gating_id" in data
    assert data["result"]["cavity_volume"] > 0
    return model_id, mold_id, data["gating_id"]


def test_gating_design_updates_exported_shell_glb():
    """Design gating must boolean-cut stored shells so export/viewport mesh changes."""
    model_id, mold_id = _setup_mold_and_model()
    faces0 = client.get(f"/api/v1/molds/result/{mold_id}").json()["result"]["shells"]
    fc0 = sum(int(s["face_count"]) for s in faces0)
    glb0 = client.get(f"/api/v1/molds/result/{mold_id}/shell/0/glb").content
    resp = client.post(
        "/api/v1/simulation/gating/design",
        json={"model_id": model_id, "mold_id": mold_id, "material": "silicone_a30"},
    )
    assert resp.status_code == 200
    faces1 = client.get(f"/api/v1/molds/result/{mold_id}").json()["result"]["shells"]
    fc1 = sum(int(s["face_count"]) for s in faces1)
    glb1 = client.get(f"/api/v1/molds/result/{mold_id}/shell/0/glb").content
    assert fc1 != fc0 or glb0 != glb1


def test_run_simulation_l1():
    model_id, mold_id, gating_id = test_gating_design()
    resp = client.post(
        "/api/v1/simulation/run",
        json={
            "model_id": model_id,
            "gating_id": gating_id,
            "material": "silicone_a30",
            "level": 1,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "sim_id" in data
    assert data["result"]["fill_fraction"] > 0


def test_run_optimization():
    model_id, mold_id, gating_id = test_gating_design()
    resp = client.post(
        "/api/v1/simulation/optimize",
        json={
            "model_id": model_id,
            "mold_id": mold_id,
            "gating_id": gating_id,
            "material": "silicone_a30",
            "max_iterations": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["result"]
    assert "converged" in data
    assert data["final_fill_fraction"] > 0


def test_list_simulations():
    resp = client.get("/api/v1/simulation/")
    assert resp.status_code == 200
    assert "simulations" in resp.json()


# ─── Phase 5: Insert / Support Plates ─────────────────


def _upload_box_for_insert():
    stl_bytes = _make_box_stl_bytes()
    resp = client.post(
        "/api/v1/models/upload",
        files={"file": ("insert_box.stl", stl_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    return resp.json()["model_id"]


def test_insert_analyze_positions():
    model_id = _upload_box_for_insert()
    resp = client.post("/api/v1/inserts/analyze", json={
        "model_id": model_id,
        "n_candidates": 3,
        "organ_type": "solid",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["n_found"] > 0
    assert "positions" in data


def test_insert_generate():
    model_id = _upload_box_for_insert()
    resp = client.post("/api/v1/inserts/generate", json={
        "model_id": model_id,
        "n_plates": 1,
        "organ_type": "general",
        "anchor_type": "mesh_holes",
        "thickness": 2.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "insert_id" in data
    assert data["n_plates"] == 1
    assert len(data["plates"]) == 1
    return data["insert_id"], model_id


def test_insert_validate():
    insert_id, model_id = test_insert_generate()
    resp = client.post("/api/v1/inserts/validate", json={
        "model_id": model_id,
        "insert_id": insert_id,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "assembly_valid" in data
    assert "messages" in data


def test_insert_get_result():
    insert_id, _ = test_insert_generate()
    resp = client.get(f"/api/v1/inserts/result/{insert_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["insert_id"] == insert_id


def test_insert_plate_glb():
    insert_id, _ = test_insert_generate()
    resp = client.get(f"/api/v1/inserts/result/{insert_id}/plate/0/glb")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/gltf-binary"
    assert len(resp.content) > 100


def test_insert_list():
    resp = client.get("/api/v1/inserts/list")
    assert resp.status_code == 200
    assert "inserts" in resp.json()


# ─── Phase 6: Export ──────────────────────────────────


def test_export_formats():
    resp = client.get("/api/v1/export/formats")
    assert resp.status_code == 200
    data = resp.json()
    assert "stl" in data["formats"]
    assert "glb" in data["formats"]


def test_export_model():
    stl_bytes = _make_box_stl_bytes()
    upload = client.post(
        "/api/v1/models/upload",
        files={"file": ("export_test.stl", stl_bytes, "application/octet-stream")},
    )
    model_id = upload.json()["model_id"]

    resp = client.post("/api/v1/export/model", json={
        "model_id": model_id,
        "format": "stl",
    })
    assert resp.status_code == 200
    assert len(resp.content) > 80  # at least STL header


def test_export_model_glb():
    stl_bytes = _make_box_stl_bytes()
    upload = client.post(
        "/api/v1/models/upload",
        files={"file": ("export_glb.stl", stl_bytes, "application/octet-stream")},
    )
    model_id = upload.json()["model_id"]

    resp = client.post("/api/v1/export/model", json={
        "model_id": model_id,
        "format": "glb",
    })
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/gltf-binary"


def test_export_all_with_model():
    stl_bytes = _make_box_stl_bytes()
    upload = client.post(
        "/api/v1/models/upload",
        files={"file": ("export_all.stl", stl_bytes, "application/octet-stream")},
    )
    model_id = upload.json()["model_id"]

    resp = client.post("/api/v1/export/all", json={
        "model_id": model_id,
        "format": "stl",
    })
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"


def test_export_all_empty():
    resp = client.post("/api/v1/export/all", json={
        "format": "stl",
    })
    assert resp.status_code == 400
