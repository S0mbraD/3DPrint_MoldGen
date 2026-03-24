"""Phase 3 测试 — 材料、浇注系统、流动仿真、自动优化"""

import numpy as np
import trimesh

from moldgen.core.flow_sim import FlowSimulator, SimConfig
from moldgen.core.gating import GatingConfig, GatingSystem
from moldgen.core.material import MATERIAL_PRESETS, MaterialProperties
from moldgen.core.mesh_data import MeshData
from moldgen.core.mold_builder import MoldBuilder, MoldConfig
from moldgen.core.optimizer import AutoOptimizer, OptimizationConfig


def _make_box(extents=(20, 30, 40)) -> MeshData:
    box = trimesh.primitives.Box(extents=extents)
    return MeshData.from_trimesh(box.to_mesh())


def _make_sphere(radius=15.0) -> MeshData:
    sphere = trimesh.primitives.Sphere(radius=radius, subdivisions=2)
    return MeshData.from_trimesh(sphere.to_mesh())


def _make_mold(model: MeshData):
    builder = MoldBuilder(MoldConfig(wall_thickness=3.0))
    return builder.build_two_part_mold(model, np.array([0, 0, 1]))


# ── MaterialProperties ───────────────────────────────────────────────

class TestMaterial:
    def test_presets_exist(self):
        assert len(MATERIAL_PRESETS) >= 7
        assert "silicone_a30" in MATERIAL_PRESETS
        assert "epoxy_resin" in MATERIAL_PRESETS

    def test_preset_values(self):
        mat = MATERIAL_PRESETS["silicone_a30"]
        assert mat.viscosity > 0
        assert mat.density > 0
        assert mat.cure_time > 0
        assert mat.shore_hardness == "A30"

    def test_to_dict(self):
        mat = MaterialProperties.silicone_shore_a30()
        d = mat.to_dict()
        assert "name" in d
        assert "viscosity" in d
        assert d["shore_hardness"] == "A30"

    def test_factory_methods(self):
        assert MaterialProperties.silicone_shore_a10().viscosity < MaterialProperties.silicone_shore_a50().viscosity
        assert MaterialProperties.abs_injection().temperature > 200
        assert MaterialProperties.pp_injection().density < 1.0


# ── GatingSystem ─────────────────────────────────────────────────────

class TestGatingSystem:
    def test_design_box(self):
        model = _make_box()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()

        gating = GatingSystem()
        result = gating.design(mold, model, mat)

        assert result.gate.position is not None
        assert result.gate.score > 0
        assert len(result.vents) > 0
        assert result.cavity_volume > 0
        assert result.estimated_fill_time > 0

    def test_design_sphere(self):
        model = _make_sphere()
        mold = _make_mold(model)
        mat = MaterialProperties.polyurethane()

        gating = GatingSystem(GatingConfig(gate_diameter=10.0, n_vents=6))
        result = gating.design(mold, model, mat)

        assert len(result.vents) == 6
        assert result.gate_diameter == 10.0

    def test_to_dict(self):
        model = _make_box()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()
        result = GatingSystem().design(mold, model, mat)
        d = result.to_dict()

        assert "gate" in d
        assert "vents" in d
        assert "estimated_fill_time" in d

    def test_vent_spacing(self):
        model = _make_sphere()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()
        result = GatingSystem(GatingConfig(n_vents=4)).design(mold, model, mat)

        positions = [v.position for v in result.vents]
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                dist = np.linalg.norm(positions[i] - positions[j])
                assert dist > 1.0, "Vents too close together"


# ── FlowSimulator ────────────────────────────────────────────────────

class TestFlowSimulator:
    def test_level1_box(self):
        model = _make_box()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()
        gating = GatingSystem().design(mold, model, mat)

        sim = FlowSimulator(SimConfig(level=1))
        result = sim.simulate(model, gating, mat)

        assert result.fill_fraction > 0
        assert result.fill_time_seconds > 0

    def test_level1_sphere(self):
        model = _make_sphere()
        mold = _make_mold(model)
        mat = MaterialProperties.polyurethane()
        gating = GatingSystem().design(mold, model, mat)

        sim = FlowSimulator(SimConfig(level=1))
        result = sim.simulate(model, gating, mat)
        assert result.fill_fraction > 0

    def test_level2_box(self):
        model = _make_box()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()
        gating = GatingSystem().design(mold, model, mat)

        sim = FlowSimulator(SimConfig(level=2, voxel_resolution=16))
        result = sim.simulate(model, gating, mat)

        assert result.fill_fraction >= 0
        assert result.to_dict()["has_fill_time_field"] is True

    def test_level2_sphere(self):
        model = _make_sphere()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()
        gating = GatingSystem().design(mold, model, mat)

        sim = FlowSimulator(SimConfig(level=2, voxel_resolution=16))
        result = sim.simulate(model, gating, mat)
        assert result.fill_fraction >= 0

    def test_to_dict(self):
        model = _make_box()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()
        gating = GatingSystem().design(mold, model, mat)

        sim = FlowSimulator(SimConfig(level=1))
        result = sim.simulate(model, gating, mat)
        d = result.to_dict()

        assert "fill_fraction" in d
        assert "fill_time_seconds" in d
        assert "defects" in d

    def test_defect_detection(self):
        model = _make_box()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()
        gating = GatingSystem().design(mold, model, mat)

        sim = FlowSimulator(SimConfig(level=1))
        result = sim.simulate(model, gating, mat)

        for defect in result.defects:
            d = defect.to_dict()
            assert "type" in d
            assert "severity" in d
            assert 0 <= d["severity"] <= 1


# ── AutoOptimizer ────────────────────────────────────────────────────

class TestAutoOptimizer:
    def test_optimize_box(self):
        model = _make_box()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()
        gating = GatingSystem().design(mold, model, mat)

        optimizer = AutoOptimizer(OptimizationConfig(max_iterations=3, sim_level=1))
        result = optimizer.optimize(model, mold, mat, gating)

        assert result.iterations >= 0
        assert result.final_fill_fraction > 0
        d = result.to_dict()
        assert "converged" in d
        assert "steps" in d

    def test_optimize_sphere(self):
        model = _make_sphere()
        mold = _make_mold(model)
        mat = MaterialProperties.polyurethane()
        gating = GatingSystem().design(mold, model, mat)

        optimizer = AutoOptimizer(OptimizationConfig(max_iterations=2, sim_level=1))
        result = optimizer.optimize(model, mold, mat, gating)

        assert result.final_fill_fraction > 0


# ── Integration Pipeline ─────────────────────────────────────────────

class TestSimPipeline:
    def test_full_pipeline(self):
        model = _make_box()
        mold = _make_mold(model)
        mat = MaterialProperties.silicone_shore_a30()

        # Gating design
        gating = GatingSystem().design(mold, model, mat)
        assert gating.cavity_volume > 0

        # L1 simulation
        sim = FlowSimulator(SimConfig(level=1))
        result = sim.simulate(model, gating, mat)
        assert result.fill_fraction > 0

        # Optimize
        optimizer = AutoOptimizer(OptimizationConfig(max_iterations=2, sim_level=1))
        opt_result = optimizer.optimize(model, mold, mat, gating)
        assert opt_result.final_fill_fraction > 0
