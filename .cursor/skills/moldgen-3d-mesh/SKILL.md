---
name: moldgen-3d-mesh
description: >-
  Work with 3D mesh processing in MoldGen. Use when implementing geometry algorithms,
  mesh operations, mold building, orientation analysis, parting surfaces, or GPU kernels.
---

# MoldGen 3D Mesh Processing

## Core Libraries

- **trimesh**: Primary mesh representation. `trimesh.Trimesh` for vertices/faces.
- **manifold3d**: Fast boolean operations (union, difference, intersection).
- **scipy.spatial**: KD-trees, convex hull, spatial transforms.
- **scikit-image**: Marching cubes for SDF→mesh conversion.
- **numpy**: All geometry math operates on numpy arrays.
- **numba**: CUDA JIT for GPU-accelerated voxelization and ray casting.

## Key Modules

```
moldgen/core/
├── mesh_io.py           # Load/save (STL, OBJ, PLY, FBX, STEP, 3MF)
├── mesh_repair.py       # Hole filling, normal fixing, degenerate removal
├── mesh_editor.py       # Boolean ops, transform, simplify, subdivide
├── mesh_data.py         # MeshData dataclass, quality metrics
├── orientation.py       # Fibonacci sampling, undercut scoring, GPU ray casting
├── parting.py           # Parting line/surface generation
├── mold_builder.py      # Shell construction, alignment pins, bolt holes
├── gating.py            # Pour hole, vent placement
├── insert_generator.py  # Support plate: cross-section, conformal, anchor patterns
├── flow_sim.py          # L1 heuristic + L2 Darcy flow simulation
├── fea.py               # Finite element analysis
├── material.py          # Material database (silicone, PU, epoxy)
└── optimizer.py         # Gate position and parameter optimization

moldgen/gpu/
├── device.py            # GPU detection (CUDA, Numba, CuPy)
├── sdf.py               # SDF voxelization (numba CUDA)
├── ray_cast.py          # GPU ray casting for orientation
├── flow_kernel.py       # GPU Darcy flow solver
└── fallback.py          # CPU fallback implementations
```

## Patterns

- Functions take `trimesh.Trimesh` or numpy arrays as input
- Return structured results (dataclasses or dicts)
- GPU functions check `GPUDevice().info.available` and fall back to CPU
- Voxel grids: numpy 3D arrays, resolution typically 64-256
- Coordinate system: Z-up, millimeters
- Mesh quality: always check watertight before boolean operations
