"""网格编辑 — 细化/简化/变换/布尔运算/撤销重做"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np
import trimesh

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)


@dataclass
class EditOperation:
    op_type: str
    params: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    face_count_before: int = 0
    face_count_after: int = 0


class EditHistory:
    """Undo/redo stack for mesh editing."""

    def __init__(self, max_history: int = 50):
        self._max = max_history
        self._undo_stack: list[tuple[MeshData, EditOperation]] = []
        self._redo_stack: list[tuple[MeshData, EditOperation]] = []

    def push(self, mesh_before: MeshData, op: EditOperation) -> None:
        self._undo_stack.append((mesh_before.copy(), op))
        if len(self._undo_stack) > self._max:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> MeshData | None:
        if not self._undo_stack:
            return None
        mesh_before, op = self._undo_stack.pop()
        self._redo_stack.append((mesh_before, op))
        return mesh_before

    def redo(self) -> MeshData | None:
        if not self._redo_stack:
            return None
        mesh, op = self._redo_stack.pop()
        self._undo_stack.append((mesh, op))
        return None  # redo re-applies the operation, caller handles this

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def get_operations(self) -> list[EditOperation]:
        return [op for _, op in self._undo_stack]


class MeshEditor:
    """网格编辑器 — 支持细化/简化/变换/布尔运算及撤销重做"""

    def __init__(self) -> None:
        self.history = EditHistory(max_history=50)

    def _record(self, mesh_before: MeshData, op_type: str, params: dict, mesh_after: MeshData) -> MeshData:
        op = EditOperation(
            op_type=op_type,
            params=params,
            face_count_before=mesh_before.face_count,
            face_count_after=mesh_after.face_count,
        )
        self.history.push(mesh_before, op)
        logger.info(
            "%s: %d → %d faces",
            op_type, mesh_before.face_count, mesh_after.face_count,
        )
        return mesh_after

    def undo(self) -> MeshData | None:
        return self.history.undo()

    # ─── Subdivision ────────────────────────────────────

    def subdivide_loop(self, mesh: MeshData, iterations: int = 1) -> MeshData:
        tm = mesh.to_trimesh()
        for _ in range(iterations):
            v, f = trimesh.remesh.subdivide_to_size(
                tm.vertices, tm.faces,
                max_edge=np.median(tm.edges_unique_length),
            )
            tm = trimesh.Trimesh(vertices=v, faces=f)
        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "subdivide_loop", {"iterations": iterations}, result)

    def subdivide_to_size(self, mesh: MeshData, max_edge: float) -> MeshData:
        tm = mesh.to_trimesh()
        v, f = trimesh.remesh.subdivide_to_size(tm.vertices, tm.faces, max_edge=max_edge)
        tm_new = trimesh.Trimesh(vertices=v, faces=f)
        result = MeshData.from_trimesh(tm_new, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "subdivide_to_size", {"max_edge": max_edge}, result)

    # ─── Simplification ─────────────────────────────────

    def simplify_qem(self, mesh: MeshData, target_faces: int) -> MeshData:
        """QEM-based decimation with multiple fallback strategies."""
        result = None

        # Strategy 1: Open3D QEM (best quality)
        try:
            import open3d as o3d
            o3d_mesh = o3d.geometry.TriangleMesh()
            o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
            o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
            o3d_mesh.compute_vertex_normals()
            simplified = o3d_mesh.simplify_quadric_decimation(
                target_number_of_triangles=target_faces,
            )
            if len(simplified.triangles) >= 4:
                result = MeshData(
                    vertices=np.asarray(simplified.vertices, dtype=np.float64),
                    faces=np.asarray(simplified.triangles, dtype=np.int64),
                    unit=mesh.unit,
                    source_path=mesh.source_path,
                    source_format=mesh.source_format,
                )
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Open3D simplify failed: %s", exc)

        # Strategy 2: Trimesh QEM
        if result is None:
            try:
                tm = mesh.to_trimesh()
                simplified = tm.simplify_quadric_decimation(face_count=target_faces)
                if simplified is not None and len(simplified.faces) >= 4:
                    result = MeshData.from_trimesh(
                        simplified, mesh.source_path, mesh.source_format,
                    )
                    result.unit = mesh.unit
            except Exception as exc:
                logger.warning("Trimesh QEM simplify failed: %s", exc)

        # Strategy 3: Vertex clustering (fast, lower quality)
        if result is None:
            try:
                import open3d as o3d
                o3d_mesh = o3d.geometry.TriangleMesh()
                o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
                o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
                ratio = max(0.01, target_faces / max(mesh.face_count, 1))
                voxel_size = mesh.to_trimesh().bounding_box.extents.max() * (1.0 - ratio) * 0.02
                simplified = o3d_mesh.simplify_vertex_clustering(voxel_size)
                if len(simplified.triangles) >= 4:
                    result = MeshData(
                        vertices=np.asarray(simplified.vertices, dtype=np.float64),
                        faces=np.asarray(simplified.triangles, dtype=np.int64),
                        unit=mesh.unit,
                        source_path=mesh.source_path,
                        source_format=mesh.source_format,
                    )
            except Exception:
                pass

        # Strategy 4: Random face subset (last resort)
        if result is None:
            tm = mesh.to_trimesh()
            n = min(target_faces, len(tm.faces))
            indices = np.random.choice(len(tm.faces), n, replace=False)
            sub = tm.submesh([indices], append=True)
            result = MeshData.from_trimesh(sub, mesh.source_path, mesh.source_format)
            result.unit = mesh.unit
            logger.warning("Used random subset fallback for simplification")

        return self._record(mesh, "simplify_qem", {"target_faces": target_faces}, result)

    def simplify_ratio(self, mesh: MeshData, ratio: float) -> MeshData:
        target = max(4, int(mesh.face_count * ratio))
        return self.simplify_qem(mesh, target)

    def generate_lod(self, mesh: MeshData, levels: list[float] | None = None) -> list[MeshData]:
        if levels is None:
            levels = [1.0, 0.5, 0.25, 0.1]
        results = []
        for ratio in levels:
            if ratio >= 1.0:
                results.append(mesh.copy())
            else:
                target = max(4, int(mesh.face_count * ratio))
                tm = mesh.to_trimesh()
                simplified = tm.simplify_quadric_decimation(face_count=target)
                lod = MeshData.from_trimesh(simplified, mesh.source_path, mesh.source_format)
                lod.unit = mesh.unit
                results.append(lod)
        return results

    # ─── Transforms ──────────────────────────────────────

    def translate(self, mesh: MeshData, offset: np.ndarray | list) -> MeshData:
        offset = np.asarray(offset, dtype=np.float64)
        result = mesh.copy()
        result.vertices = result.vertices + offset
        return self._record(mesh, "translate", {"offset": offset.tolist()}, result)

    def rotate(self, mesh: MeshData, axis: np.ndarray | list, angle_deg: float) -> MeshData:
        axis = np.asarray(axis, dtype=np.float64)
        axis = axis / np.linalg.norm(axis)
        angle_rad = np.radians(angle_deg)
        tm = mesh.to_trimesh()
        mat = trimesh.transformations.rotation_matrix(angle_rad, axis)
        tm.apply_transform(mat)
        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "rotate", {"axis": axis.tolist(), "angle_deg": angle_deg}, result)

    def scale(self, mesh: MeshData, factor: float | np.ndarray | list) -> MeshData:
        result = mesh.copy()
        factor_arr = np.asarray(factor, dtype=np.float64)
        if factor_arr.ndim == 0:
            factor_arr = np.array([factor_arr, factor_arr, factor_arr])
        result.vertices = result.vertices * factor_arr
        return self._record(mesh, "scale", {"factor": factor_arr.tolist()}, result)

    def mirror(self, mesh: MeshData, plane_normal: np.ndarray | list, plane_point: np.ndarray | list | None = None) -> MeshData:
        normal = np.asarray(plane_normal, dtype=np.float64)
        normal = normal / np.linalg.norm(normal)
        point = np.asarray(plane_point, dtype=np.float64) if plane_point is not None else np.zeros(3)

        result = mesh.copy()
        d = np.dot(result.vertices - point, normal)
        result.vertices = result.vertices - 2.0 * np.outer(d, normal)
        # Flip face winding to preserve outward normals
        result.faces = result.faces[:, ::-1]
        return self._record(mesh, "mirror", {"plane_normal": normal.tolist()}, result)

    def center(self, mesh: MeshData) -> MeshData:
        offset = -mesh.center
        return self.translate(mesh, offset)

    def align_to_floor(self, mesh: MeshData) -> MeshData:
        z_min = mesh.bounds[0][2]
        return self.translate(mesh, [0, 0, -z_min])

    # ─── Boolean Operations ──────────────────────────────

    def boolean_union(self, a: MeshData, b: MeshData) -> MeshData:
        return self._boolean_op(a, b, "union")

    def boolean_difference(self, a: MeshData, b: MeshData) -> MeshData:
        return self._boolean_op(a, b, "difference")

    def boolean_intersection(self, a: MeshData, b: MeshData) -> MeshData:
        return self._boolean_op(a, b, "intersection")

    def _boolean_op(self, a: MeshData, b: MeshData, operation: str) -> MeshData:
        try:
            import manifold3d as mf
            m_a = mf.Manifold.of_trimesh(a.to_trimesh())
            m_b = mf.Manifold.of_trimesh(b.to_trimesh())
            if operation == "union":
                m_result = m_a + m_b
            elif operation == "difference":
                m_result = m_a - m_b
            elif operation == "intersection":
                m_result = m_a ^ m_b
            else:
                raise ValueError(f"Unknown boolean op: {operation}")
            tm_result = m_result.to_trimesh()
        except (ImportError, Exception) as e:
            logger.warning("Manifold3D failed (%s), trying trimesh boolean", e)
            tm_a = a.to_trimesh()
            tm_b = b.to_trimesh()
            tm_result = tm_a.boolean(tm_b, operation=operation)

        result = MeshData.from_trimesh(tm_result, a.source_path, a.source_format)
        result.unit = a.unit
        return self._record(a, f"boolean_{operation}", {}, result)

    # ─── Analysis ────────────────────────────────────────

    @staticmethod
    def compute_section(mesh: MeshData, plane_origin: np.ndarray | list, plane_normal: np.ndarray | list) -> np.ndarray | None:
        origin = np.asarray(plane_origin, dtype=np.float64)
        normal = np.asarray(plane_normal, dtype=np.float64)
        tm = mesh.to_trimesh()
        try:
            section = tm.section(plane_origin=origin, plane_normal=normal)
            if section is None:
                return None
            path2d = section.to_planar()[0]
            return np.array(path2d.vertices)
        except Exception as exc:
            logger.debug("Section computation failed: %s", exc)
            return None

    @staticmethod
    def compute_thickness(mesh: MeshData, ray_count: int = 1) -> np.ndarray:
        """Approximate wall thickness at each vertex by shooting rays inward."""
        tm = mesh.to_trimesh()
        normals = -tm.vertex_normals
        origins = tm.vertices + normals * 1e-4

        from trimesh.ray.ray_pyembree import RayMeshIntersector
        try:
            intersector = RayMeshIntersector(tm)
        except Exception as exc:
            logger.debug("pyembree unavailable, falling back to ray_triangle: %s", exc)
            from trimesh.ray.ray_triangle import RayMeshIntersector as RayFallback
            intersector = RayFallback(tm)

        locations, index_ray, _ = intersector.intersects_location(origins, normals)
        thickness = np.full(len(tm.vertices), np.inf)
        if len(locations) > 0:
            dists = np.linalg.norm(locations - origins[index_ray], axis=1)
            for i, d in zip(index_ray, dists, strict=False):
                if d < thickness[i]:
                    thickness[i] = d
        thickness[np.isinf(thickness)] = 0.0
        return thickness

    # ─── Topology Editing ────────────────────────────────

    def delete_faces(self, mesh: MeshData, face_indices: np.ndarray | list) -> MeshData:
        indices = np.asarray(face_indices)
        mask = np.ones(mesh.face_count, dtype=bool)
        mask[indices] = False
        tm = mesh.to_trimesh()
        tm.update_faces(mask)
        tm.remove_unreferenced_vertices()
        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "delete_faces", {"count": len(indices)}, result)

    def fill_holes(self, mesh: MeshData) -> MeshData:
        tm = mesh.to_trimesh()
        tm.fill_holes()
        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "fill_holes", {}, result)

    def shell(self, mesh: MeshData, thickness: float) -> MeshData:
        """Create a shell (hollow) mesh by offsetting inward."""
        tm_outer = mesh.to_trimesh()
        tm_inner = tm_outer.copy()
        tm_inner.vertices -= tm_inner.vertex_normals * thickness
        tm_inner.invert()
        combined = trimesh.util.concatenate([tm_outer, tm_inner])
        result = MeshData.from_trimesh(combined, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "shell", {"thickness": thickness}, result)

    # ── nTopology-inspired mesh operations ──────────────────────────

    def smooth_laplacian(
        self, mesh: MeshData, iterations: int = 3, lamb: float = 0.5,
    ) -> MeshData:
        """Laplacian smoothing — uniform neighbour averaging."""
        tm = mesh.to_trimesh()
        try:
            trimesh.smoothing.filter_laplacian(tm, iterations=iterations, lamb=lamb)
        except Exception as exc:
            logger.debug("trimesh Laplacian failed, using manual fallback: %s", exc)
            verts = np.asarray(tm.vertices, dtype=np.float64)
            faces = np.asarray(tm.faces, dtype=np.int64)
            for _ in range(iterations):
                new_v = verts.copy()
                for f in faces:
                    for idx in range(3):
                        n1, n2 = f[(idx + 1) % 3], f[(idx + 2) % 3]
                        new_v[f[idx]] += lamb * (verts[n1] + verts[n2] - 2 * verts[f[idx]]) / 6
                verts = new_v
            tm.vertices = verts
        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "smooth_laplacian", {"iterations": iterations, "lambda": lamb}, result)

    def smooth_taubin(
        self, mesh: MeshData, iterations: int = 5, lamb: float = 0.5, mu: float = -0.53,
    ) -> MeshData:
        """Taubin smoothing — alternating +lambda/-mu to reduce shrinkage."""
        tm = mesh.to_trimesh()
        try:
            trimesh.smoothing.filter_taubin(tm, iterations=iterations, lamb=lamb, mu=mu)
        except Exception as exc:
            logger.debug("Taubin not available, falling back to Laplacian: %s", exc)
            trimesh.smoothing.filter_laplacian(tm, iterations=iterations, lamb=lamb)
        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "smooth_taubin", {"iterations": iterations}, result)

    def smooth_humphrey(
        self, mesh: MeshData, iterations: int = 5, alpha: float = 0.1, beta: float = 0.5,
    ) -> MeshData:
        """HC (Humphrey's Classes) smoothing — volume-preserving."""
        tm = mesh.to_trimesh()
        try:
            trimesh.smoothing.filter_humphrey(tm, iterations=iterations, alpha=alpha, beta=beta)
        except Exception as exc:
            logger.debug("HC smoothing not available, falling back to Laplacian: %s", exc)
            trimesh.smoothing.filter_laplacian(tm, iterations=max(1, iterations // 2))
        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "smooth_humphrey", {"iterations": iterations}, result)

    def remesh_isotropic(
        self, mesh: MeshData, target_edge_length: float | None = None,
    ) -> MeshData:
        """Isotropic remeshing via subdivide → decimate cycle."""
        tm = mesh.to_trimesh()
        if target_edge_length is None:
            edges = tm.edges_unique_length
            target_edge_length = float(np.median(edges))

        n_faces = len(tm.faces)
        est_area = float(tm.area)
        target_faces = max(100, int(est_area / (target_edge_length ** 2 * 0.433)))
        target_faces = min(target_faces, 500_000)

        if n_faces < target_faces:
            tm = tm.subdivide()

        if len(tm.faces) > target_faces:
            try:
                import open3d as o3d
                o3d_mesh = o3d.geometry.TriangleMesh(
                    o3d.utility.Vector3dVector(tm.vertices),
                    o3d.utility.Vector3iVector(tm.faces),
                )
                o3d_mesh = o3d_mesh.simplify_quadric_decimation(target_faces)
                tm = trimesh.Trimesh(
                    vertices=np.asarray(o3d_mesh.vertices),
                    faces=np.asarray(o3d_mesh.triangles),
                )
            except ImportError:
                tm = tm.simplify_quadric_decimation(target_faces)

        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "remesh_isotropic", {"target_edge": target_edge_length}, result)

    def offset_surface(
        self, mesh: MeshData, distance: float,
    ) -> MeshData:
        """Offset surface along vertex normals (positive = outward)."""
        tm = mesh.to_trimesh()
        tm.vertices += tm.vertex_normals * distance
        result = MeshData.from_trimesh(tm, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "offset_surface", {"distance": distance}, result)

    def thicken(
        self, mesh: MeshData, thickness: float, direction: str = "both",
    ) -> MeshData:
        """Thicken a surface mesh into a solid.

        direction: "outward", "inward", or "both" (half each way).
        """
        tm = mesh.to_trimesh()
        if direction == "both":
            half = thickness / 2
            outer = tm.copy()
            outer.vertices += outer.vertex_normals * half
            inner = tm.copy()
            inner.vertices -= inner.vertex_normals * half
            inner.invert()
        elif direction == "outward":
            outer = tm.copy()
            outer.vertices += outer.vertex_normals * thickness
            inner = tm.copy()
            inner.invert()
        else:
            outer = tm.copy()
            inner = tm.copy()
            inner.vertices -= inner.vertex_normals * thickness
            inner.invert()
        combined = trimesh.util.concatenate([outer, inner])
        result = MeshData.from_trimesh(combined, mesh.source_path, mesh.source_format)
        result.unit = mesh.unit
        return self._record(mesh, "thicken", {"thickness": thickness, "direction": direction}, result)
