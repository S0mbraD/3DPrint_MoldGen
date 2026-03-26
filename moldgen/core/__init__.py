from moldgen.core.analysis import (
    BOMEntry,
    CurvatureResult,
    DraftAnalysisResult,
    OverhangResult,
    SymmetryResult,
    ThicknessResult,
    compute_bom,
    compute_curvature,
    compute_draft_analysis,
    compute_overhang,
    compute_symmetry,
    compute_thickness,
)
from moldgen.core.fea import FEAConfig, FEAResult, FEASolver
from moldgen.core.flow_sim import FlowSimulator, SimConfig, SimulationResult
from moldgen.core.gating import GatingConfig, GatingResult, GatingSystem
from moldgen.core.insert_generator import (
    AnchorType,
    InsertConfig,
    InsertGenerator,
    InsertPlate,
    InsertResult,
    OrganType,
)
from moldgen.core.material import MATERIAL_PRESETS, MaterialProperties
from moldgen.core.mesh_data import MeshData
from moldgen.core.mesh_editor import MeshEditor
from moldgen.core.mesh_io import MeshIO
from moldgen.core.mesh_repair import MeshRepair, QualityReport, RepairResult
from moldgen.core.mold_builder import MoldBuilder, MoldConfig, MoldResult, MoldShell
from moldgen.core.optimizer import AutoOptimizer, OptimizationConfig, OptimizationResult
from moldgen.core.orientation import OrientationAnalyzer, OrientationConfig, OrientationResult
from moldgen.core.parting import PartingConfig, PartingGenerator, PartingResult
from moldgen.core.tpms import (
    TPMS_REGISTRY,
    TPMSFieldResult,
    apply_field_modulation,
    evaluate_field_2d,
    extract_hole_centres,
    generate_tpms_holes,
)
from moldgen.core.distance_field import (
    SDFGrid,
    mesh_to_sdf,
    mesh_to_sdf_shared,
    smooth_union,
    smooth_intersection,
    smooth_difference,
    field_offset,
    field_shell,
    field_variable_shell,
    field_blend,
    field_remap,
    field_gaussian_blur,
    extract_isosurface,
    field_driven_shell,
)
from moldgen.core.topology_opt import (
    TOConfig2D,
    TOConfig3D,
    TOResult2D,
    TOResult3D,
    topology_opt_2d,
    topology_opt_3d,
    density_to_mesh,
)
from moldgen.core.lattice import (
    LatticeConfig,
    LatticeResult,
    generate_graph_lattice,
    generate_tpms_lattice,
    generate_voronoi_foam,
    generate_lattice,
)
from moldgen.core.interference import (
    ClearanceResult,
    AssemblyCheckResult,
    compute_clearance,
    validate_assembly,
)
from moldgen.core.analysis import MeshQualityResult, compute_mesh_quality

__all__ = [
    # Analysis
    "BOMEntry",
    "CurvatureResult",
    "DraftAnalysisResult",
    "FEAConfig",
    "FEAResult",
    "FEASolver",
    "MeshQualityResult",
    "OverhangResult",
    "SymmetryResult",
    "ThicknessResult",
    "compute_bom",
    "compute_curvature",
    "compute_draft_analysis",
    "compute_mesh_quality",
    "compute_overhang",
    "compute_symmetry",
    "compute_thickness",
    # Core
    "AnchorType",
    "AutoOptimizer",
    "FlowSimulator",
    "GatingConfig",
    "GatingResult",
    "GatingSystem",
    "InsertConfig",
    "InsertGenerator",
    "InsertPlate",
    "InsertResult",
    "MATERIAL_PRESETS",
    "MaterialProperties",
    "MeshData",
    "MeshEditor",
    "MeshIO",
    "MeshRepair",
    "MoldBuilder",
    "MoldConfig",
    "MoldResult",
    "MoldShell",
    "OptimizationConfig",
    "OptimizationResult",
    "OrganType",
    "OrientationAnalyzer",
    "OrientationConfig",
    "OrientationResult",
    "PartingConfig",
    "PartingGenerator",
    "PartingResult",
    "QualityReport",
    "RepairResult",
    "SimConfig",
    "SimulationResult",
    # TPMS
    "TPMS_REGISTRY",
    "TPMSFieldResult",
    "apply_field_modulation",
    "evaluate_field_2d",
    "extract_hole_centres",
    "generate_tpms_holes",
    # Distance Field / SDF
    "SDFGrid",
    "mesh_to_sdf",
    "smooth_union",
    "smooth_intersection",
    "smooth_difference",
    "field_offset",
    "field_shell",
    "field_variable_shell",
    "field_blend",
    "field_remap",
    "field_gaussian_blur",
    "extract_isosurface",
    "field_driven_shell",
    # Topology Optimisation
    "TOConfig2D",
    "TOConfig3D",
    "TOResult2D",
    "TOResult3D",
    "topology_opt_2d",
    "topology_opt_3d",
    "density_to_mesh",
    # Lattice
    "LatticeConfig",
    "LatticeResult",
    "generate_graph_lattice",
    "generate_tpms_lattice",
    "generate_voronoi_foam",
    "generate_lattice",
    # Interference
    "ClearanceResult",
    "AssemblyCheckResult",
    "compute_clearance",
    "validate_assembly",
]
