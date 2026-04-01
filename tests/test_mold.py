"""Phase 2 测试 — 方向分析、分型面、模具壳体"""

import numpy as np
import pytest
import trimesh

from moldgen.core.mesh_data import MeshData
from moldgen.core.mold_builder import MoldBuilder, MoldConfig
from moldgen.core.orientation import OrientationAnalyzer, OrientationConfig
from moldgen.core.parting import PartingConfig, PartingGenerator


def _make_box(extents=(20, 30, 40), center=(0, 0, 0)) -> MeshData:
    box = trimesh.primitives.Box(extents=extents)
    box.apply_translation(center)
    return MeshData.from_trimesh(box.to_mesh())


def _make_sphere(radius=15.0) -> MeshData:
    sphere = trimesh.primitives.Sphere(radius=radius, subdivisions=2)
    return MeshData.from_trimesh(sphere.to_mesh())


def _make_cylinder(radius=10.0, height=30.0) -> MeshData:
    cyl = trimesh.primitives.Cylinder(radius=radius, height=height)
    return MeshData.from_trimesh(cyl.to_mesh())


# ── OrientationAnalyzer ──────────────────────────────────────────────

class TestOrientationAnalyzer:
    def test_basic_analysis_box(self):
        mesh = _make_box()
        analyzer = OrientationAnalyzer(OrientationConfig(
            n_fibonacci_samples=30,
            n_final_candidates=3,
        ))
        result = analyzer.analyze(mesh)

        assert result.best_direction is not None
        assert len(result.best_direction) == 3
        assert result.best_score.total_score > 0
        assert len(result.top_candidates) <= 3

    def test_analysis_sphere(self):
        mesh = _make_sphere()
        analyzer = OrientationAnalyzer(OrientationConfig(n_fibonacci_samples=20))
        result = analyzer.analyze(mesh)

        assert result.best_score.total_score > 0
        assert result.best_score.visibility_ratio > 0

    def test_analysis_cylinder(self):
        mesh = _make_cylinder()
        analyzer = OrientationAnalyzer(OrientationConfig(n_fibonacci_samples=30))
        result = analyzer.analyze(mesh)

        assert result.best_direction is not None
        assert result.best_score.total_score > 0

    def test_evaluate_specific_direction(self):
        mesh = _make_box()
        analyzer = OrientationAnalyzer()
        score = analyzer.evaluate_direction(mesh, np.array([0, 0, 1]))

        assert score.visibility_ratio > 0
        assert score.total_score > 0
        assert score.direction[2] == pytest.approx(1.0)

    def test_to_dict(self):
        mesh = _make_box()
        analyzer = OrientationAnalyzer(OrientationConfig(n_fibonacci_samples=20))
        result = analyzer.analyze(mesh)
        d = result.to_dict()

        assert "best_direction" in d
        assert "best_score" in d
        assert "top_candidates" in d
        assert len(d["best_direction"]) == 3
        assert "visibility_ratio" in d["best_score"]

    def test_score_ordering(self):
        mesh = _make_box()
        analyzer = OrientationAnalyzer(OrientationConfig(
            n_fibonacci_samples=30,
            n_final_candidates=5,
        ))
        result = analyzer.analyze(mesh)
        scores = [c.total_score for c in result.top_candidates]
        assert scores == sorted(scores, reverse=True)


# ── PartingGenerator ─────────────────────────────────────────────────

class TestPartingGenerator:
    def test_parting_box_z(self):
        mesh = _make_box()
        gen = PartingGenerator()
        result = gen.generate(mesh, np.array([0, 0, 1]))

        assert result.n_upper > 0
        assert result.n_lower > 0
        assert result.direction[2] == pytest.approx(1.0)

    def test_parting_sphere(self):
        mesh = _make_sphere()
        gen = PartingGenerator()
        result = gen.generate(mesh, np.array([0, 0, 1]))

        assert result.n_upper > 0
        assert result.n_lower > 0
        assert len(result.parting_lines) > 0

    def test_parting_surface_generation(self):
        mesh = _make_sphere()
        gen = PartingGenerator()
        result = gen.generate(mesh, np.array([0, 0, 1]))

        assert result.parting_surface is not None
        assert result.parting_surface.mesh.face_count > 0
        assert len(result.parting_surface.normal) == 3

    def test_parting_to_dict(self):
        mesh = _make_box()
        gen = PartingGenerator()
        result = gen.generate(mesh, np.array([1, 0, 0]))
        d = result.to_dict()

        assert "direction" in d
        assert "parting_lines" in d
        assert "n_upper_faces" in d
        assert "n_lower_faces" in d

    def test_parting_with_custom_config(self):
        mesh = _make_sphere()
        config = PartingConfig(
            side_angle_threshold=10.0,
            smooth_iterations=10,
        )
        gen = PartingGenerator(config)
        result = gen.generate(mesh, np.array([0, 1, 0]))

        assert result.n_upper + result.n_lower > 0


# ── MoldBuilder ──────────────────────────────────────────────────────

class TestMoldBuilder:
    def test_two_part_mold_box(self):
        mesh = _make_box()
        builder = MoldBuilder()
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))

        assert len(result.shells) >= 1
        for shell in result.shells:
            assert shell.mesh.face_count > 0
            assert len(shell.direction) == 3

    def test_two_part_mold_sphere(self):
        mesh = _make_sphere()
        builder = MoldBuilder(MoldConfig(wall_thickness=3.0))
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))

        assert len(result.shells) >= 1

    def test_alignment_features(self):
        mesh = _make_box()
        builder = MoldBuilder(MoldConfig(add_alignment_pins=True, n_pins=4))
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))

        assert len(result.alignment_features) > 0
        types = {f.feature_type for f in result.alignment_features}
        assert "pin" in types
        assert "hole" in types

    def test_pour_and_vent_holes(self):
        mesh = _make_box()
        builder = MoldBuilder(MoldConfig(add_pour_hole=True, add_vent_holes=True))
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))

        assert result.pour_hole_position is not None
        assert len(result.vent_positions) > 0

    def test_no_features(self):
        mesh = _make_box()
        builder = MoldBuilder(MoldConfig(
            add_alignment_pins=False,
            add_pour_hole=False,
            add_vent_holes=False,
        ))
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))

        assert len(result.alignment_features) == 0
        assert result.pour_hole_position is None

    def test_conformal_shell(self):
        mesh = _make_sphere()
        builder = MoldBuilder(MoldConfig(shell_type="conformal"))
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))

        assert len(result.shells) >= 1

    def test_two_part_shells_closed_for_slicing(self):
        """Export meshes must have no open boundary edges (FDM slicers)."""
        from collections import Counter

        mesh = _make_box()
        builder = MoldBuilder(MoldConfig(
            add_pour_hole=False,
            add_vent_holes=False,
            add_alignment_pins=False,
        ))
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))
        for sh in result.shells:
            fe = trimesh.geometry.faces_to_edges(np.asarray(sh.mesh.faces, dtype=np.int64))
            fe = np.sort(fe, axis=1)
            n_open = sum(1 for _, v in Counter(map(tuple, fe)).items() if v == 1)
            assert n_open == 0, f"shell {sh.shell_id} has {n_open} open boundary edges"

    def test_direct_fallback_box_shell_keeps_outer_extent(self):
        """When boolean+voxel fail, box shell must still include outer block walls (regression)."""
        mesh = _make_sphere()
        direction = (
            np.array([0.18, 0.22, 0.959], dtype=np.float64)
            / np.linalg.norm([0.18, 0.22, 0.959])
        )
        cfg = MoldConfig(
            shell_type="box",
            add_pour_hole=False,
            add_vent_holes=False,
            add_alignment_pins=False,
        )
        builder = MoldBuilder(cfg)

        orig_sub = MoldBuilder._robust_boolean_subtract
        orig_vox = MoldBuilder._build_shells_voxel
        try:
            MoldBuilder._robust_boolean_subtract = lambda self, o, c: None  # type: ignore[assignment]
            MoldBuilder._build_shells_voxel = lambda self, *a, **k: None  # type: ignore[misc]
            result = builder.build_two_part_mold(mesh, direction)
        finally:
            MoldBuilder._robust_boolean_subtract = orig_sub
            MoldBuilder._build_shells_voxel = orig_vox

        assert len(result.shells) == 2
        for sh in result.shells:
            ext = sh.mesh.extents
            assert float(np.max(ext)) >= 44.0, (
                f"shell {sh.shell_id} too small (extents {ext.tolist()}); "
                "missing outer box walls in direct fallback?"
            )

    def test_mold_to_dict(self):
        mesh = _make_box()
        builder = MoldBuilder()
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))
        d = result.to_dict()

        assert "n_shells" in d
        assert "shells" in d
        assert "cavity_volume" in d
        assert "alignment_features" in d

    def test_shell_glb_export(self):
        mesh = _make_box()
        builder = MoldBuilder()
        result = builder.build_two_part_mold(mesh, np.array([0, 0, 1]))

        for shell in result.shells:
            glb = shell.mesh.to_glb()
            assert len(glb) > 0
            assert glb[:4] == b"glTF"

    def test_multi_part_mold(self):
        mesh = _make_sphere()
        builder = MoldBuilder()
        directions = [
            np.array([0, 0, 1]),
            np.array([1, 0, 0]),
        ]
        result = builder.build_multi_part_mold(mesh, directions)
        assert len(result.shells) >= 2

    def test_multi_part_mold_requires_min_directions(self):
        mesh = _make_box()
        builder = MoldBuilder()
        with pytest.raises(ValueError, match="at least 2"):
            builder.build_multi_part_mold(mesh, [np.array([0, 0, 1])])


# ── Integration: Orientation → Parting → Mold ────────────────────────

class TestMoldPipeline:
    def test_full_pipeline_box(self):
        mesh = _make_box()

        # Step 1: Find best orientation
        analyzer = OrientationAnalyzer(OrientationConfig(n_fibonacci_samples=20))
        ori = analyzer.analyze(mesh)
        direction = ori.best_direction

        # Step 2: Generate parting
        parting_gen = PartingGenerator()
        parting = parting_gen.generate(mesh, direction)
        assert parting.n_upper + parting.n_lower > 0

        # Step 3: Build mold
        builder = MoldBuilder()
        mold = builder.build_two_part_mold(mesh, direction)
        assert len(mold.shells) >= 1

    def test_full_pipeline_sphere(self):
        mesh = _make_sphere()

        analyzer = OrientationAnalyzer(OrientationConfig(n_fibonacci_samples=20))
        ori = analyzer.analyze(mesh)

        parting_gen = PartingGenerator()
        parting = parting_gen.generate(mesh, ori.best_direction)
        assert parting.parting_surface is not None

        builder = MoldBuilder(MoldConfig(wall_thickness=3.0))
        mold = builder.build_two_part_mold(mesh, ori.best_direction)
        assert len(mold.shells) >= 1
        assert mold.to_dict()["n_shells"] >= 1
