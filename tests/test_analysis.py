"""Tests for moldgen.core.analysis — nTopology-inspired mesh analysis suite.

Each test creates a simple mesh fixture and verifies the analysis function
returns structurally valid results with reasonable values.
"""

import numpy as np
import trimesh

from moldgen.core.mesh_data import MeshData
from moldgen.core.analysis import (
    compute_thickness,
    compute_curvature,
    compute_draft_analysis,
    compute_symmetry,
    compute_overhang,
    compute_bom,
)


def _make_box() -> MeshData:
    tm = trimesh.creation.box(extents=[10, 10, 10])
    return MeshData.from_trimesh(tm)


def _make_sphere(radius: float = 5.0) -> MeshData:
    tm = trimesh.creation.icosphere(subdivisions=2, radius=radius)
    return MeshData.from_trimesh(tm)


# ── Thickness Analysis ────────────────────────────────────────────────

class TestThicknessAnalysis:

    def test_box_thickness_range(self):
        result = compute_thickness(_make_box(), n_rays=3, max_distance=20)
        assert result.min_thickness > 0
        assert result.max_thickness <= 20
        assert result.mean_thickness > 0
        assert len(result.per_vertex) == _make_box().vertex_count

    def test_sphere_thickness(self):
        sphere = _make_sphere(radius=5.0)
        result = compute_thickness(sphere, n_rays=4, max_distance=15)
        assert result.mean_thickness > 0
        assert result.std_thickness >= 0

    def test_histogram_bins(self):
        result = compute_thickness(_make_box(), n_rays=2, max_distance=20)
        assert len(result.histogram_bins) == len(result.histogram_counts) + 1

    def test_to_dict_keys(self):
        result = compute_thickness(_make_box(), n_rays=2)
        d = result.to_dict()
        for key in ("min", "max", "mean", "std", "thin_count", "n_vertices",
                     "histogram_bins", "histogram_counts", "values"):
            assert key in d, f"Missing key: {key}"


# ── Curvature Analysis ────────────────────────────────────────────────

class TestCurvatureAnalysis:

    def test_box_curvature(self):
        result = compute_curvature(_make_box())
        assert len(result.gaussian) == _make_box().vertex_count
        assert len(result.mean_curvature) == len(result.gaussian)

    def test_sphere_curvature_positive(self):
        result = compute_curvature(_make_sphere())
        assert result.max_val > 0

    def test_to_dict_keys(self):
        d = compute_curvature(_make_box()).to_dict()
        for key in ("n_vertices", "gaussian_min", "gaussian_max",
                     "mean_curvature_min", "mean_curvature_max"):
            assert key in d


# ── Draft Analysis ────────────────────────────────────────────────────

class TestDraftAnalysis:

    def test_box_default_direction(self):
        result = compute_draft_analysis(_make_box())
        assert result.min_draft <= result.max_draft
        assert 0 <= result.undercut_fraction <= 1

    def test_custom_direction(self):
        result = compute_draft_analysis(_make_box(), pull_direction=[1, 0, 0])
        assert len(result.per_face_angle) == _make_box().face_count

    def test_histogram(self):
        result = compute_draft_analysis(_make_sphere())
        assert len(result.histogram_bins) == len(result.histogram_counts) + 1

    def test_to_dict_keys(self):
        d = compute_draft_analysis(_make_box()).to_dict()
        for key in ("n_faces", "min_draft", "max_draft", "mean_draft",
                     "undercut_fraction", "critical_fraction"):
            assert key in d


# ── Symmetry Analysis ─────────────────────────────────────────────────

class TestSymmetryAnalysis:

    def test_box_symmetry_high(self):
        """A centered box should be highly symmetric about all axes."""
        result = compute_symmetry(_make_box())
        assert result.x_symmetry > 0.7
        assert result.y_symmetry > 0.7
        assert result.z_symmetry > 0.7

    def test_sphere_symmetry(self):
        result = compute_symmetry(_make_sphere())
        assert result.best_score > 0.5

    def test_principal_axes(self):
        result = compute_symmetry(_make_box())
        assert len(result.principal_axes) == 3
        for axis in result.principal_axes:
            assert len(axis) == 3

    def test_to_dict_keys(self):
        d = compute_symmetry(_make_box()).to_dict()
        for key in ("x_symmetry", "y_symmetry", "z_symmetry",
                     "best_plane", "best_score", "principal_axes"):
            assert key in d


# ── Overhang Analysis ─────────────────────────────────────────────────

class TestOverhangAnalysis:

    def test_box_overhang(self):
        result = compute_overhang(_make_box())
        assert 0 <= result.overhang_fraction <= 1
        assert result.total_area > 0

    def test_sphere_overhang(self):
        result = compute_overhang(_make_sphere(), critical_angle=30)
        assert result.overhang_fraction >= 0

    def test_custom_build_direction(self):
        result = compute_overhang(_make_box(), build_direction=[1, 0, 0])
        assert len(result.per_face_overhang) == _make_box().face_count

    def test_to_dict_keys(self):
        d = compute_overhang(_make_box()).to_dict()
        for key in ("n_faces", "overhang_fraction", "overhang_area_mm2",
                     "total_area_mm2", "critical_angle_deg"):
            assert key in d


# ── BOM ───────────────────────────────────────────────────────────────

class TestBOM:

    def test_single_component(self):
        entries = compute_bom({"model": _make_box()})
        assert len(entries) == 1
        assert entries[0].component == "model"
        assert entries[0].volume_mm3 > 0
        assert entries[0].estimated_weight_g > 0

    def test_multiple_components(self):
        entries = compute_bom({
            "model": _make_box(),
            "mold": _make_sphere(),
        })
        assert len(entries) == 2
        names = {e.component for e in entries}
        assert names == {"model", "mold"}

    def test_to_dict(self):
        entries = compute_bom({"part": _make_box()})
        d = entries[0].to_dict()
        for key in ("component", "volume_mm3", "surface_area_mm2",
                     "face_count", "estimated_weight_g", "estimated_print_time_min"):
            assert key in d
