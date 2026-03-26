"""Tests for nTopology-style advanced modules.

Covers: distance_field, topology_opt, lattice, interference, mesh quality.
"""

import math

import numpy as np
import pytest
import trimesh


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def box():
    return trimesh.creation.box(extents=[10, 10, 10])


@pytest.fixture
def sphere():
    return trimesh.creation.icosphere(subdivisions=2, radius=5.0)


@pytest.fixture
def small_box():
    return trimesh.creation.box(extents=[4, 4, 4])


@pytest.fixture
def offset_box():
    b = trimesh.creation.box(extents=[4, 4, 4])
    b.apply_translation([3, 3, 3])
    return b


# ══════════════════════════════════════════════════════════════════════
# Distance Field
# ══════════════════════════════════════════════════════════════════════

class TestDistanceField:
    def test_mesh_to_sdf_shape(self, box):
        from moldgen.core.distance_field import mesh_to_sdf
        sdf = mesh_to_sdf(box, resolution=16, pad=1.0)
        assert sdf.values.ndim == 3
        assert sdf.spacing > 0
        assert len(sdf.origin) == 3

    def test_sdf_sign_convention(self, box):
        from moldgen.core.distance_field import mesh_to_sdf
        sdf = mesh_to_sdf(box, resolution=16, pad=1.0)
        assert sdf.values.min() < 0, "Interior should have negative SDF"
        assert sdf.values.max() > 0, "Exterior should have positive SDF"

    def test_smooth_union(self):
        from moldgen.core.distance_field import smooth_union
        a = np.array([1.0, -1.0, 0.5])
        b = np.array([0.5, 0.3, -0.2])
        result = smooth_union(a, b, k=0.5)
        assert result.shape == a.shape
        assert np.all(result <= np.minimum(a, b) + 0.01)

    def test_smooth_difference(self):
        from moldgen.core.distance_field import smooth_difference
        a = np.array([-1.0, 0.5])
        b = np.array([-0.5, -0.3])
        result = smooth_difference(a, b, k=0.3)
        assert result.shape == a.shape

    def test_field_offset(self, box):
        from moldgen.core.distance_field import mesh_to_sdf, field_offset
        sdf = mesh_to_sdf(box, resolution=16, pad=2.0)
        grown = field_offset(sdf, 1.0)
        assert grown.values.min() < sdf.values.min()

    def test_field_shell(self, box):
        from moldgen.core.distance_field import mesh_to_sdf, field_shell
        sdf = mesh_to_sdf(box, resolution=16, pad=2.0)
        shell = field_shell(sdf, 1.0)
        assert shell.values.shape == sdf.values.shape

    def test_field_remap(self, box):
        from moldgen.core.distance_field import mesh_to_sdf, field_remap
        sdf = mesh_to_sdf(box, resolution=16, pad=1.0)
        remapped = field_remap(sdf, in_min=-5, in_max=5, out_min=0, out_max=1)
        assert remapped.values.min() >= -0.01
        assert remapped.values.max() <= 1.01

    def test_extract_isosurface(self, box):
        from moldgen.core.distance_field import mesh_to_sdf, extract_isosurface
        sdf = mesh_to_sdf(box, resolution=24, pad=1.0)
        mesh = extract_isosurface(sdf, iso=0.0)
        assert len(mesh.vertices) > 0
        assert len(mesh.faces) > 0

    def test_field_blend_union(self, box, small_box):
        from moldgen.core.distance_field import mesh_to_sdf, field_blend
        sdf_a = mesh_to_sdf(box, resolution=16, pad=2.0)
        sdf_b = mesh_to_sdf(small_box, resolution=16, pad=2.0)
        if sdf_a.shape == sdf_b.shape and np.allclose(sdf_a.origin, sdf_b.origin):
            result = field_blend(sdf_a, sdf_b, "union", 0.5)
            assert result.values.shape == sdf_a.values.shape


# ══════════════════════════════════════════════════════════════════════
# Topology Optimisation
# ══════════════════════════════════════════════════════════════════════

class TestTopologyOpt:
    def test_2d_cantilever(self):
        from moldgen.core.topology_opt import TOConfig2D, topology_opt_2d
        cfg = TOConfig2D(nelx=20, nely=10, volfrac=0.5, max_iter=15, bc_type="cantilever")
        result = topology_opt_2d(cfg)
        assert result.density.shape == (10, 20)
        assert result.iterations > 0
        assert result.final_compliance > 0
        assert 0 < result.final_volfrac < 1

    def test_2d_mbb(self):
        from moldgen.core.topology_opt import TOConfig2D, topology_opt_2d
        cfg = TOConfig2D(nelx=20, nely=10, volfrac=0.4, max_iter=10, bc_type="mbb")
        result = topology_opt_2d(cfg)
        assert result.density.shape == (10, 20)
        assert len(result.compliance_history) > 0

    def test_2d_compliance_decreasing(self):
        from moldgen.core.topology_opt import TOConfig2D, topology_opt_2d
        cfg = TOConfig2D(nelx=20, nely=10, volfrac=0.5, max_iter=20, bc_type="cantilever")
        result = topology_opt_2d(cfg)
        if len(result.compliance_history) > 3:
            assert result.compliance_history[-1] <= result.compliance_history[0] * 1.05

    def test_density_to_mesh(self):
        from moldgen.core.topology_opt import density_to_mesh
        density = np.random.rand(10, 15)
        mesh = density_to_mesh(density, threshold=0.5, spacing=1.0)
        assert len(mesh.vertices) > 0

    def test_3d_basic(self):
        from moldgen.core.topology_opt import TOConfig3D, topology_opt_3d
        cfg = TOConfig3D(nelx=6, nely=4, nelz=4, volfrac=0.4, max_iter=5)
        result = topology_opt_3d(cfg)
        assert result.density.shape == (4, 4, 6)
        assert result.iterations > 0


# ══════════════════════════════════════════════════════════════════════
# Lattice
# ══════════════════════════════════════════════════════════════════════

class TestLattice:
    def test_graph_bcc(self, box):
        from moldgen.core.lattice import LatticeConfig, generate_graph_lattice
        cfg = LatticeConfig(cell_type="bcc", cell_size=5.0, beam_radius=0.3, trim_to_mesh=False)
        result = generate_graph_lattice(box, cfg)
        assert result.beam_count > 0
        assert len(result.mesh.vertices) > 0

    def test_graph_fcc(self, box):
        from moldgen.core.lattice import LatticeConfig, generate_graph_lattice
        cfg = LatticeConfig(cell_type="fcc", cell_size=5.0, beam_radius=0.3, trim_to_mesh=False)
        result = generate_graph_lattice(box, cfg)
        assert result.beam_count > 0

    def test_tpms_gyroid(self, box):
        from moldgen.core.lattice import LatticeConfig, generate_tpms_lattice
        cfg = LatticeConfig(tpms_type="gyroid", cell_size=5.0, wall_thickness=0.5, resolution=24)
        result = generate_tpms_lattice(box, cfg)
        assert len(result.mesh.vertices) > 0
        assert result.lattice_type == "tpms_gyroid"

    def test_tpms_schwarz_p(self, box):
        from moldgen.core.lattice import LatticeConfig, generate_tpms_lattice
        cfg = LatticeConfig(tpms_type="schwarz_p", cell_size=5.0, wall_thickness=0.5, resolution=24)
        result = generate_tpms_lattice(box, cfg)
        assert len(result.mesh.faces) > 0

    def test_voronoi_foam(self, box):
        from moldgen.core.lattice import generate_voronoi_foam
        result = generate_voronoi_foam(box, n_cells=20, wall_thickness=0.3, resolution=20)
        assert result.cell_count > 0

    def test_generate_lattice_dispatcher(self, box):
        from moldgen.core.lattice import generate_lattice
        result = generate_lattice(box, lattice_type="tpms")
        assert result.lattice_type.startswith("tpms_")

    def test_variable_thickness(self, box):
        from moldgen.core.lattice import LatticeConfig, generate_graph_lattice
        cfg = LatticeConfig(
            cell_type="bcc", cell_size=5.0, beam_radius=0.5,
            variable_thickness=True, thickness_field="radial",
            thickness_min=0.2, thickness_max=0.8, trim_to_mesh=False,
        )
        result = generate_graph_lattice(box, cfg)
        assert result.beam_count > 0


# ══════════════════════════════════════════════════════════════════════
# Interference
# ══════════════════════════════════════════════════════════════════════

class TestInterference:
    def test_no_interference(self):
        from moldgen.core.interference import compute_clearance
        a = trimesh.creation.box(extents=[4, 4, 4])
        b = trimesh.creation.box(extents=[4, 4, 4])
        b.apply_translation([10, 0, 0])
        result = compute_clearance(a, b, sample_count=500)
        assert result.min_clearance > 0
        assert not result.interference_detected

    def test_overlap_detected(self):
        from moldgen.core.interference import compute_clearance
        a = trimesh.creation.box(extents=[6, 6, 6])
        b = trimesh.creation.box(extents=[6, 6, 6])
        b.apply_translation([3, 0, 0])
        result = compute_clearance(a, b, sample_count=500)
        assert result.interference_detected
        assert result.min_clearance < 0

    def test_histogram_structure(self):
        from moldgen.core.interference import compute_clearance
        a = trimesh.creation.box(extents=[4, 4, 4])
        b = trimesh.creation.box(extents=[4, 4, 4])
        b.apply_translation([6, 0, 0])
        result = compute_clearance(a, b, sample_count=300)
        assert len(result.clearance_histogram) > 0
        assert "bin_start" in result.clearance_histogram[0]

    def test_assembly_all_clear(self):
        from moldgen.core.interference import validate_assembly
        a = trimesh.creation.box(extents=[3, 3, 3])
        b = trimesh.creation.box(extents=[3, 3, 3])
        b.apply_translation([8, 0, 0])
        c = trimesh.creation.box(extents=[3, 3, 3])
        c.apply_translation([0, 8, 0])
        result = validate_assembly([("a", a), ("b", b), ("c", c)], min_clearance=0.5)
        assert result.all_clear
        assert len(result.checks) == 3

    def test_assembly_with_interference(self):
        from moldgen.core.interference import validate_assembly
        a = trimesh.creation.box(extents=[6, 6, 6])
        b = trimesh.creation.box(extents=[6, 6, 6])
        b.apply_translation([2, 0, 0])
        result = validate_assembly([("a", a), ("b", b)], min_clearance=0.5)
        assert not result.all_clear


# ══════════════════════════════════════════════════════════════════════
# Mesh Quality
# ══════════════════════════════════════════════════════════════════════

class TestMeshQuality:
    def test_box_quality(self, box):
        from moldgen.core.analysis import compute_mesh_quality
        result = compute_mesh_quality(box)
        assert result.n_vertices > 0
        assert result.n_faces > 0
        assert result.n_edges > 0
        assert result.aspect_ratio_mean >= 1.0
        assert result.is_watertight
        assert result.volume > 0

    def test_sphere_compactness(self, sphere):
        from moldgen.core.analysis import compute_mesh_quality
        result = compute_mesh_quality(sphere)
        assert result.compactness > 0.5, "Sphere should have high compactness"

    def test_euler_characteristic(self, box):
        from moldgen.core.analysis import compute_mesh_quality
        result = compute_mesh_quality(box)
        assert result.euler_characteristic == 2, "Closed genus-0 mesh should have χ=2"
        assert result.genus == 0

    def test_no_degenerate(self, box):
        from moldgen.core.analysis import compute_mesh_quality
        result = compute_mesh_quality(box)
        assert result.degenerate_face_count == 0

    def test_histograms(self, box):
        from moldgen.core.analysis import compute_mesh_quality
        result = compute_mesh_quality(box)
        assert len(result.aspect_ratio_histogram) > 0
        assert len(result.edge_length_histogram) > 0
        assert len(result.angle_histogram) > 0

    def test_edge_length_stats(self, box):
        from moldgen.core.analysis import compute_mesh_quality
        result = compute_mesh_quality(box)
        assert result.edge_length_min > 0
        assert result.edge_length_max >= result.edge_length_min
        assert result.edge_length_std >= 0
