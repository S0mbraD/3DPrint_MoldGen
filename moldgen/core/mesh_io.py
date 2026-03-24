"""多格式模型 IO — 支持 STL/OBJ/FBX/3MF/PLY/STEP/glTF/AMF 等"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import trimesh

from moldgen.core.mesh_data import MeshData

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SUPPORTED_IMPORT = {
    ".stl", ".obj", ".fbx", ".3mf", ".ply",
    ".step", ".stp", ".gltf", ".glb",
    ".amf", ".dae", ".off",
}

SUPPORTED_EXPORT = {".stl", ".obj", ".3mf", ".ply", ".glb", ".off"}


class MeshIO:
    """多格式 3D 模型导入/导出"""

    @staticmethod
    def load(filepath: str | Path, unit: str = "mm") -> MeshData:
        filepath = Path(filepath)
        suffix = filepath.suffix.lower()
        if suffix not in SUPPORTED_IMPORT:
            raise ValueError(f"Unsupported format: {suffix}. Supported: {SUPPORTED_IMPORT}")

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        logger.info("Loading %s (%s)", filepath.name, suffix)

        if suffix in (".step", ".stp"):
            return MeshIO._load_step(filepath, unit)
        if suffix in (".fbx", ".dae"):
            return MeshIO._load_assimp(filepath, unit)

        return MeshIO._load_trimesh(filepath, unit)

    @staticmethod
    def _load_trimesh(filepath: Path, unit: str) -> MeshData:
        scene_or_mesh = trimesh.load(str(filepath), force=None)

        if isinstance(scene_or_mesh, trimesh.Scene):
            meshes = [g for g in scene_or_mesh.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                raise ValueError(f"No mesh geometry found in {filepath.name}")
            if len(meshes) == 1:
                mesh = meshes[0]
            else:
                mesh = trimesh.util.concatenate(meshes)
                logger.info("Merged %d meshes from scene", len(meshes))
        elif isinstance(scene_or_mesh, trimesh.Trimesh):
            mesh = scene_or_mesh
        else:
            raise ValueError(f"Unexpected type from trimesh: {type(scene_or_mesh)}")

        result = MeshData.from_trimesh(
            mesh,
            source_path=str(filepath),
            source_format=filepath.suffix.lower(),
        )
        result.unit = unit
        logger.info(
            "Loaded: %d vertices, %d faces, watertight=%s",
            result.vertex_count, result.face_count, result.is_watertight,
        )
        return result

    @staticmethod
    def _load_step(filepath: Path, unit: str) -> MeshData:
        """Load STEP files via cadquery/OCP or fallback to gmsh tessellation."""
        try:
            import OCP  # noqa: F401
            from OCP.BRep import BRep_Tool
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.STEPControl import STEPControl_Reader
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopLoc import TopLoc_Location

            reader = STEPControl_Reader()
            status = reader.ReadFile(str(filepath))
            if status != 1:
                raise RuntimeError(f"STEP read failed with status {status}")
            reader.TransferRoots()
            shape = reader.OneShape()

            BRepMesh_IncrementalMesh(shape, 0.1)

            all_verts = []
            all_faces = []
            offset = 0

            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            while explorer.More():
                face = explorer.Current()
                loc = TopLoc_Location()
                triangulation = BRep_Tool.Triangulation_s(face, loc)
                if triangulation is not None:
                    n_nodes = triangulation.NbNodes()
                    n_tris = triangulation.NbTriangles()
                    verts = np.array([
                        [triangulation.Node(i + 1).X(), triangulation.Node(i + 1).Y(), triangulation.Node(i + 1).Z()]
                        for i in range(n_nodes)
                    ])
                    faces = np.array([
                        [triangulation.Triangle(i + 1).Value(1) - 1 + offset,
                         triangulation.Triangle(i + 1).Value(2) - 1 + offset,
                         triangulation.Triangle(i + 1).Value(3) - 1 + offset]
                        for i in range(n_tris)
                    ])
                    all_verts.append(verts)
                    all_faces.append(faces)
                    offset += n_nodes
                explorer.Next()

            if not all_verts:
                raise RuntimeError("No tessellation data from STEP")

            mesh = trimesh.Trimesh(
                vertices=np.vstack(all_verts),
                faces=np.vstack(all_faces),
            )
            result = MeshData.from_trimesh(mesh, str(filepath), ".step")
            result.unit = unit
            return result

        except ImportError:
            logger.warning("OCP not available, trying trimesh for STEP (limited support)")
            return MeshIO._load_trimesh(filepath, unit)

    @staticmethod
    def _load_assimp(filepath: Path, unit: str) -> MeshData:
        """Load FBX/DAE via pyassimp."""
        try:
            import pyassimp
            scene = pyassimp.load(str(filepath))
            try:
                all_verts = []
                all_faces = []
                offset = 0
                for mesh in scene.meshes:
                    verts = np.array(mesh.vertices, dtype=np.float64)
                    faces = np.array([f for f in mesh.faces], dtype=np.int64) + offset
                    all_verts.append(verts)
                    all_faces.append(faces)
                    offset += len(verts)

                if not all_verts:
                    raise ValueError(f"No meshes found in {filepath.name}")

                combined = trimesh.Trimesh(
                    vertices=np.vstack(all_verts),
                    faces=np.vstack(all_faces),
                )
                result = MeshData.from_trimesh(combined, str(filepath), filepath.suffix.lower())
                result.unit = unit
                return result
            finally:
                pyassimp.release(scene)
        except ImportError:
            logger.warning("pyassimp not available, falling back to trimesh")
            return MeshIO._load_trimesh(filepath, unit)

    @staticmethod
    def export(mesh: MeshData, filepath: str | Path, file_format: str | None = None) -> Path:
        filepath = Path(filepath)
        if file_format:
            suffix = file_format if file_format.startswith(".") else f".{file_format}"
        else:
            suffix = filepath.suffix.lower()

        if suffix not in SUPPORTED_EXPORT:
            raise ValueError(f"Unsupported export format: {suffix}. Supported: {SUPPORTED_EXPORT}")

        filepath.parent.mkdir(parents=True, exist_ok=True)
        tm_mesh = mesh.to_trimesh()
        tm_mesh.export(str(filepath), file_type=suffix.lstrip("."))
        logger.info("Exported: %s (%d faces)", filepath.name, mesh.face_count)
        return filepath

    @staticmethod
    def export_multi(
        meshes: dict[str, MeshData],
        directory: str | Path,
        file_format: str = "stl",
    ) -> list[Path]:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        suffix = file_format if file_format.startswith(".") else f".{file_format}"
        for name, mesh in meshes.items():
            p = directory / f"{name}{suffix}"
            MeshIO.export(mesh, p)
            paths.append(p)
        return paths

    @staticmethod
    def to_glb(mesh: MeshData) -> bytes:
        return mesh.to_glb()
