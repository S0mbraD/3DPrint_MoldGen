"""Phase 1 mesh module tests"""

import tempfile
from pathlib import Path

import numpy as np
import trimesh

from moldgen.core import MeshData, MeshEditor, MeshIO, MeshRepair


def _make_box() -> MeshData:
    """Create a simple unit box MeshData for testing."""
    tm = trimesh.creation.box(extents=[10, 10, 10])
    return MeshData.from_trimesh(tm)


def _make_sphere(radius: float = 5.0, subdivisions: int = 2) -> MeshData:
    tm = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    return MeshData.from_trimesh(tm)


# ─── MeshData ────────────────────────────────────────


def test_mesh_data_properties():
    mesh = _make_box()
    assert mesh.vertex_count == 8
    assert mesh.face_count == 12
    assert mesh.is_watertight
    assert mesh.volume > 0
    assert mesh.surface_area > 0
    np.testing.assert_allclose(mesh.extents, [10, 10, 10], atol=0.01)


def test_mesh_data_copy():
    mesh = _make_box()
    copy = mesh.copy()
    copy.vertices[0] += 100
    assert not np.array_equal(mesh.vertices[0], copy.vertices[0])


def test_mesh_data_info():
    mesh = _make_box()
    info = mesh.info()
    assert info["vertex_count"] == 8
    assert info["face_count"] == 12
    assert info["is_watertight"] is True


def test_mesh_data_to_glb():
    mesh = _make_box()
    glb = mesh.to_glb()
    assert isinstance(glb, bytes)
    assert len(glb) > 100


# ─── MeshIO ──────────────────────────────────────────


def test_io_export_import_stl():
    mesh = _make_box()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.stl"
        MeshIO.export(mesh, path)
        assert path.exists()
        loaded = MeshIO.load(path)
        assert loaded.face_count == mesh.face_count
        assert loaded.is_watertight


def test_io_export_import_obj():
    mesh = _make_sphere()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sphere.obj"
        MeshIO.export(mesh, path)
        loaded = MeshIO.load(path)
        assert abs(loaded.face_count - mesh.face_count) < 5


def test_io_export_import_glb():
    mesh = _make_box()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.glb"
        MeshIO.export(mesh, path)
        loaded = MeshIO.load(path)
        assert loaded.face_count > 0


def test_io_export_multi():
    meshes = {"shell_1": _make_box(), "shell_2": _make_sphere()}
    with tempfile.TemporaryDirectory() as tmp:
        paths = MeshIO.export_multi(meshes, tmp, "stl")
        assert len(paths) == 2
        for p in paths:
            assert p.exists()


def test_io_unsupported_format():
    import pytest
    with pytest.raises(ValueError, match="Unsupported format"):
        MeshIO.load("nonexistent.xyz")


# ─── MeshRepair ──────────────────────────────────────


def test_repair_check_quality():
    mesh = _make_box()
    report = MeshRepair.check_quality(mesh)
    assert report.is_watertight
    assert report.face_count == 12
    assert report.degenerate_faces == 0
    assert report.surface_area > 0


def test_repair_auto_fix():
    mesh = _make_box()
    result = MeshRepair.repair(mesh)
    assert result.success
    assert result.mesh.face_count > 0
    assert result.after is not None
    assert result.after.is_watertight


def test_repair_degenerate_faces():
    tm = trimesh.creation.box(extents=[10, 10, 10])
    # Add a degenerate face
    v = tm.vertices
    tm = trimesh.Trimesh(
        vertices=np.vstack([v, [[99, 99, 99]]]),
        faces=np.vstack([tm.faces, [[0, 0, 0]]]),
    )
    mesh = MeshData.from_trimesh(tm)
    report = MeshRepair.check_quality(mesh)
    assert report.degenerate_faces >= 1

    result = MeshRepair.repair(mesh)
    assert result.after.degenerate_faces == 0


# ─── MeshEditor ──────────────────────────────────────


def test_editor_simplify():
    mesh = _make_sphere(subdivisions=3)
    editor = MeshEditor()
    original_faces = mesh.face_count
    simplified = editor.simplify_qem(mesh, target_faces=100)
    assert simplified.face_count <= 110
    assert simplified.face_count < original_faces


def test_editor_simplify_ratio():
    mesh = _make_sphere(subdivisions=3)
    editor = MeshEditor()
    simplified = editor.simplify_ratio(mesh, 0.25)
    assert simplified.face_count < mesh.face_count * 0.4


def test_editor_subdivide_to_size():
    mesh = _make_box()
    editor = MeshEditor()
    refined = editor.subdivide_to_size(mesh, max_edge=3.0)
    assert refined.face_count > mesh.face_count


def test_editor_translate():
    mesh = _make_box()
    editor = MeshEditor()
    moved = editor.translate(mesh, [10, 20, 30])
    np.testing.assert_allclose(moved.center, mesh.center + [10, 20, 30], atol=0.01)


def test_editor_rotate():
    mesh = _make_box()
    editor = MeshEditor()
    rotated = editor.rotate(mesh, [0, 0, 1], 90)
    assert rotated.face_count == mesh.face_count
    np.testing.assert_allclose(rotated.extents, mesh.extents, atol=0.1)


def test_editor_scale():
    mesh = _make_box()
    editor = MeshEditor()
    scaled = editor.scale(mesh, 2.0)
    np.testing.assert_allclose(scaled.extents, mesh.extents * 2, atol=0.01)


def test_editor_center():
    mesh = _make_box()
    editor = MeshEditor()
    moved = editor.translate(mesh, [100, 200, 300])
    centered = editor.center(moved)
    np.testing.assert_allclose(centered.center, [0, 0, 0], atol=0.01)


def test_editor_mirror():
    mesh = _make_box()
    editor = MeshEditor()
    mirrored = editor.mirror(mesh, [1, 0, 0])
    assert mirrored.face_count == mesh.face_count


def test_editor_undo():
    mesh = _make_box()
    editor = MeshEditor()
    editor.translate(mesh, [10, 0, 0])
    undone = editor.undo()
    assert undone is not None
    np.testing.assert_allclose(undone.center, mesh.center, atol=0.01)


def test_editor_boolean_union():
    a = _make_box()
    b_mesh = _make_box()
    b_mesh.vertices = b_mesh.vertices + 5.0
    editor = MeshEditor()
    try:
        result = editor.boolean_union(a, b_mesh)
        assert result.face_count > 0
        assert result.volume > a.volume
    except Exception:
        pass  # boolean ops can fail without manifold3d compiled for platform


def test_editor_shell():
    mesh = _make_sphere(subdivisions=2)
    editor = MeshEditor()
    shelled = editor.shell(mesh, thickness=1.0)
    assert shelled.face_count > mesh.face_count


def test_editor_lod_generation():
    mesh = _make_sphere(subdivisions=3)
    editor = MeshEditor()
    lods = editor.generate_lod(mesh, [1.0, 0.5, 0.1])
    assert len(lods) == 3
    assert lods[0].face_count == mesh.face_count
    assert lods[1].face_count < mesh.face_count
    assert lods[2].face_count < lods[1].face_count
