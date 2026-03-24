"""Phase 5 测试 — InsertGenerator, 锚固结构, 装配验证"""

import numpy as np
import trimesh

from moldgen.core.insert_generator import (
    AnchorType,
    InsertConfig,
    InsertGenerator,
    OrganType,
)
from moldgen.core.mesh_data import MeshData
from moldgen.core.mold_builder import MoldBuilder, MoldConfig


def _make_box(extents=None):
    extents = extents or [30, 20, 15]
    box = trimesh.creation.box(extents=extents)
    return MeshData.from_trimesh(box)


def _make_sphere(radius=15):
    sphere = trimesh.creation.icosphere(radius=radius, subdivisions=2)
    return MeshData.from_trimesh(sphere)


class TestInsertPositionAnalysis:
    def test_analyze_box(self):
        mesh = _make_box()
        gen = InsertGenerator()
        positions = gen.analyze_positions(mesh, n_candidates=5)
        assert len(positions) > 0
        assert positions[0].score > 0
        assert positions[0].section_area > 0

    def test_analyze_sphere(self):
        mesh = _make_sphere()
        gen = InsertGenerator()
        positions = gen.analyze_positions(mesh, n_candidates=3)
        assert len(positions) > 0

    def test_position_scoring(self):
        mesh = _make_box([40, 20, 10])
        gen = InsertGenerator()
        positions = gen.analyze_positions(mesh, n_candidates=10)
        scores = [p.score for p in positions]
        assert scores == sorted(scores, reverse=True)

    def test_position_to_dict(self):
        mesh = _make_box()
        gen = InsertGenerator()
        positions = gen.analyze_positions(mesh, n_candidates=2)
        d = positions[0].to_dict()
        assert "origin" in d
        assert "normal" in d
        assert "score" in d
        assert "reason" in d


class TestInsertGeneration:
    def test_generate_plate_box(self):
        mesh = _make_box()
        gen = InsertGenerator()
        positions = gen.analyze_positions(mesh, n_candidates=3)
        plate = gen.generate_plate(mesh, positions[0])
        assert plate.mesh.face_count > 0
        assert plate.thickness == 2.0

    def test_generate_plate_sphere(self):
        mesh = _make_sphere()
        gen = InsertGenerator()
        positions = gen.analyze_positions(mesh, n_candidates=3)
        plate = gen.generate_plate(mesh, positions[0])
        assert plate.mesh.face_count > 0

    def test_generate_with_custom_thickness(self):
        mesh = _make_box()
        config = InsertConfig(thickness=3.0)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        assert plate.thickness == 3.0

    def test_plate_to_dict(self):
        mesh = _make_box()
        gen = InsertGenerator()
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        d = plate.to_dict()
        assert "face_count" in d
        assert "thickness" in d
        assert "position" in d


class TestAnchorGeneration:
    def test_mesh_holes(self):
        mesh = _make_box()
        config = InsertConfig(anchor_type=AnchorType.MESH_HOLES)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        plate = gen.add_anchor(plate)
        assert plate.anchor is not None
        assert plate.anchor.type == AnchorType.MESH_HOLES
        assert plate.anchor.count > 0

    def test_bumps(self):
        mesh = _make_box()
        config = InsertConfig(anchor_type=AnchorType.BUMPS)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        plate = gen.add_anchor(plate)
        assert plate.anchor is not None
        assert plate.anchor.type == AnchorType.BUMPS

    def test_grooves(self):
        mesh = _make_box()
        config = InsertConfig(anchor_type=AnchorType.GROOVES)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        plate = gen.add_anchor(plate)
        assert plate.anchor is not None
        assert plate.anchor.type == AnchorType.GROOVES

    def test_dovetail(self):
        mesh = _make_box()
        config = InsertConfig(anchor_type=AnchorType.DOVETAIL)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        plate = gen.add_anchor(plate)
        assert plate.anchor is not None
        assert plate.anchor.type == AnchorType.DOVETAIL

    def test_diamond(self):
        mesh = _make_box()
        config = InsertConfig(anchor_type=AnchorType.DIAMOND)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        plate = gen.add_anchor(plate)
        assert plate.anchor is not None
        assert plate.anchor.type == AnchorType.DIAMOND

    def test_organ_type_auto_anchor(self):
        mesh = _make_box()
        config = InsertConfig(organ_type=OrganType.HOLLOW)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        plate = gen.add_anchor(plate)
        assert plate.anchor is not None
        assert plate.anchor.type == AnchorType.GROOVES

    def test_anchor_to_dict(self):
        mesh = _make_box()
        config = InsertConfig(anchor_type=AnchorType.MESH_HOLES)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        plate = gen.add_anchor(plate)
        d = plate.anchor.to_dict()
        assert "type" in d
        assert "count" in d
        assert "feature_size" in d


class TestAssemblyValidation:
    def test_validate_single_plate(self):
        mesh = _make_box()
        gen = InsertGenerator()
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        is_valid, messages = gen.validate_assembly(mesh, [plate])
        assert isinstance(is_valid, bool)
        assert len(messages) > 0

    def test_validate_with_anchor(self):
        mesh = _make_box()
        config = InsertConfig(anchor_type=AnchorType.MESH_HOLES)
        gen = InsertGenerator(config)
        positions = gen.analyze_positions(mesh)
        plate = gen.generate_plate(mesh, positions[0])
        plate = gen.add_anchor(plate)
        is_valid, messages = gen.validate_assembly(mesh, [plate])
        assert isinstance(is_valid, bool)
        assert len(messages) > 0


class TestFullPipeline:
    def test_full_pipeline_box(self):
        mesh = _make_box()
        gen = InsertGenerator()
        result = gen.full_pipeline(mesh, n_plates=1)
        assert len(result.plates) == 1
        assert result.plates[0].anchor is not None
        assert len(result.positions_analyzed) > 0
        assert len(result.validation_messages) > 0

    def test_full_pipeline_sphere(self):
        mesh = _make_sphere()
        gen = InsertGenerator()
        result = gen.full_pipeline(mesh, n_plates=1)
        assert len(result.plates) == 1

    def test_full_pipeline_multi_plate(self):
        mesh = _make_box([40, 30, 20])
        gen = InsertGenerator()
        result = gen.full_pipeline(mesh, n_plates=2)
        assert len(result.plates) == 2

    def test_full_pipeline_with_organ_type(self):
        mesh = _make_box()
        config = InsertConfig(organ_type=OrganType.SOLID)
        gen = InsertGenerator(config)
        result = gen.full_pipeline(mesh, n_plates=1)
        assert result.plates[0].anchor is not None
        assert result.plates[0].anchor.type == AnchorType.MESH_HOLES

    def test_result_to_dict(self):
        mesh = _make_box()
        gen = InsertGenerator()
        result = gen.full_pipeline(mesh, n_plates=1)
        d = result.to_dict()
        assert "n_plates" in d
        assert "plates" in d
        assert "assembly_valid" in d
        assert "positions_analyzed" in d

    def test_pipeline_with_mold_shells(self):
        mesh = _make_box([30, 20, 15])
        builder = MoldBuilder(MoldConfig(wall_thickness=4.0))
        direction = np.array([0.0, 0.0, 1.0])
        mold_result = builder.build_two_part_mold(mesh, direction)
        shells = [s.mesh for s in mold_result.shells]

        gen = InsertGenerator()
        result = gen.full_pipeline(mesh, mold_shells=shells, n_plates=1)
        assert len(result.plates) == 1
        assert result.plates[0].locating_slots is not None
