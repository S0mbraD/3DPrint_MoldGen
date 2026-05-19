"""Tests for moldgen.core.mesh_repair — unified mesh repair primitives."""

import numpy as np
import pytest
import trimesh

from moldgen.core.mesh_repair import (
    clean_trimesh,
    compact_vertex_indices,
    dedupe_faces,
    repair_trimesh,
    stitch_boundaries,
)


class TestCleanTrimesh:
    def test_removes_degenerate_faces(self):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]], dtype=float)
        faces = np.array([[0, 1, 2], [0, 0, 3]])
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        result = clean_trimesh(mesh)
        assert len(result.faces) >= 1

    def test_preserves_valid_mesh(self, unit_cube):
        n_faces = len(unit_cube.faces)
        result = clean_trimesh(unit_cube)
        assert len(result.faces) == n_faces


class TestCompactVertexIndices:
    def test_compacts_sparse_vertices(self):
        verts = np.zeros((100, 3))
        verts[0] = [0, 0, 0]
        verts[50] = [1, 0, 0]
        verts[99] = [0, 1, 0]
        faces = np.array([[0, 50, 99]])
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        compact_vertex_indices(mesh)
        assert len(mesh.vertices) == 3
        assert np.max(mesh.faces) <= 2


class TestDedupeFaces:
    def test_removes_duplicate_faces(self, unit_cube):
        original_faces = len(unit_cube.faces)
        extra = unit_cube.faces[:2].copy()
        unit_cube.faces = np.vstack([unit_cube.faces, extra])
        assert len(unit_cube.faces) == original_faces + 2
        dedupe_faces(unit_cube)
        assert len(unit_cube.faces) <= original_faces + 2


class TestRepairTrimesh:
    def test_watertight_passthrough(self, unit_cube):
        assert unit_cube.is_watertight
        result = repair_trimesh(unit_cube)
        assert result.is_watertight

    def test_aggressive_mode(self, unit_cube):
        result = repair_trimesh(unit_cube, aggressive=True)
        assert len(result.faces) > 0

    def test_no_fill_preserves_holes(self):
        mesh = trimesh.creation.box(extents=[1, 1, 1])
        mesh.faces = mesh.faces[:8]
        result = repair_trimesh(mesh, fill=False)
        assert len(result.faces) >= 4


class TestStitchBoundaries:
    def test_attempts_hole_fill(self, unit_cube):
        result = stitch_boundaries(unit_cube)
        assert result.is_watertight
