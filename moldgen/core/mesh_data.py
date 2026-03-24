"""内部统一网格数据结构"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import trimesh


@dataclass
class MeshData:
    """MoldGen 内部统一网格表示。
    所有模块之间传递网格数据均使用此结构。
    """

    vertices: np.ndarray  # (N, 3) float64
    faces: np.ndarray  # (M, 3) int64
    face_normals: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))
    vertex_normals: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))

    unit: str = "mm"
    source_path: str = ""
    source_format: str = ""

    _edges: np.ndarray | None = field(default=None, repr=False)
    _face_adjacency: np.ndarray | None = field(default=None, repr=False)

    @property
    def face_count(self) -> int:
        return len(self.faces)

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def bounds(self) -> np.ndarray:
        return np.array([self.vertices.min(axis=0), self.vertices.max(axis=0)])

    @property
    def extents(self) -> np.ndarray:
        b = self.bounds
        return b[1] - b[0]

    @property
    def center(self) -> np.ndarray:
        b = self.bounds
        return (b[0] + b[1]) / 2.0

    @property
    def volume(self) -> float:
        return float(self.to_trimesh().volume)

    @property
    def surface_area(self) -> float:
        return float(self.to_trimesh().area)

    @property
    def is_watertight(self) -> bool:
        return bool(self.to_trimesh().is_watertight)

    @property
    def edges(self) -> np.ndarray:
        if self._edges is None:
            self._edges = self.to_trimesh().edges_unique
        return self._edges

    @property
    def face_adjacency(self) -> np.ndarray:
        if self._face_adjacency is None:
            self._face_adjacency = self.to_trimesh().face_adjacency
        return self._face_adjacency

    def to_trimesh(self) -> trimesh.Trimesh:
        import trimesh as tm

        mesh = tm.Trimesh(
            vertices=self.vertices.copy(),
            faces=self.faces.copy(),
            process=False,
        )
        if len(self.face_normals) == len(self.faces):
            mesh.face_normals = self.face_normals
        if len(self.vertex_normals) == len(self.vertices):
            mesh.vertex_normals = self.vertex_normals
        return mesh

    @staticmethod
    def from_trimesh(mesh: trimesh.Trimesh, source_path: str = "", source_format: str = "") -> MeshData:
        return MeshData(
            vertices=np.asarray(mesh.vertices, dtype=np.float64),
            faces=np.asarray(mesh.faces, dtype=np.int64),
            face_normals=np.asarray(mesh.face_normals, dtype=np.float64),
            vertex_normals=np.asarray(mesh.vertex_normals, dtype=np.float64),
            source_path=source_path,
            source_format=source_format,
        )

    def to_glb(self) -> bytes:
        return self.to_trimesh().export(file_type="glb")

    def info(self) -> dict:
        return {
            "vertex_count": self.vertex_count,
            "face_count": self.face_count,
            "bounds_min": self.bounds[0].tolist(),
            "bounds_max": self.bounds[1].tolist(),
            "extents": self.extents.tolist(),
            "center": self.center.tolist(),
            "is_watertight": self.is_watertight,
            "volume": self.volume if self.is_watertight else None,
            "surface_area": self.surface_area,
            "unit": self.unit,
            "source_format": self.source_format,
        }

    def copy(self) -> MeshData:
        return MeshData(
            vertices=self.vertices.copy(),
            faces=self.faces.copy(),
            face_normals=self.face_normals.copy() if len(self.face_normals) else np.empty((0, 3)),
            vertex_normals=self.vertex_normals.copy() if len(self.vertex_normals) else np.empty((0, 3)),
            unit=self.unit,
            source_path=self.source_path,
            source_format=self.source_format,
        )
