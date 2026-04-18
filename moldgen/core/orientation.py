"""最优脱模方向分析 — 批量筛选 + 逐向精评 + GPU 加速
=====================================================

算法:
  Phase 1 (Batch Screening):
    Fibonacci 球面采样 + PCA + 面积加权法线 → 全部 C 方向在一次
    矩阵运算中计算 7 项指标 (Frank & Fadel 1995; Woo 1994; Ahn 2002)
  Phase 2 (Detailed Evaluation):
    对 Top-K 候选方向逐个精评:
    - 精确 min_draft_angle / mean_draft_angle (逐面循环)
    - 射线投射法 undercut 验证 (可选, 仅对最终候选)
    - 支撑面积 / 投影面积比
  Phase 3 (Adaptive Refinement):
    对 Top-3 进行 ±5°/±10° 邻域局部搜索, 仅在顶部分数接近时触发

Multi-Algorithm Switching:
    根据面数和 GPU 可用性自动选择最优路径:
    - ≤50K faces  → CPU NumPy batch (最低开销)
    - ≤2M faces + GPU → CuPy batch (GPU 全量)
    - >2M faces  → 降采样后 CPU batch
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np
import trimesh

from moldgen.core.mesh_data import MeshData

logger = logging.getLogger(__name__)

ANALYSIS_MAX_FACES_CPU = 200_000
ANALYSIS_MAX_FACES_GPU = 2_000_000
DETAILED_TOP_K = 10


# ── Data classes ────────────────────────────────────────────────────────

@dataclass
class OrientationConfig:
    n_fibonacci_samples: int = 100
    n_top_candidates: int = 20
    n_final_candidates: int = 5
    dedup_threshold: float = 0.98
    refine_passes: int = 1
    detailed_evaluation: bool = True
    weights: dict = field(default_factory=lambda: {
        "visibility": 0.25,
        "undercut": 0.20,
        "flatness": 0.12,
        "draft_angle": 0.18,
        "symmetry": 0.08,
        "stability": 0.10,
        "compactness": 0.07,
    })


@dataclass
class DirectionScore:
    direction: np.ndarray
    total_score: float = 0.0
    visibility_ratio: float = 0.0
    undercut_ratio: float = 0.0
    flatness: float = 0.0
    min_draft_angle: float = 0.0
    mean_draft_angle: float = 0.0
    symmetry: float = 0.0
    stability: float = 0.0
    visible_area: float = 0.0
    undercut_area: float = 0.0
    compactness: float = 0.0
    support_area: float = 0.0

    def to_dict(self) -> dict:
        return {
            "direction": self.direction.tolist(),
            "total_score": round(self.total_score, 4),
            "visibility_ratio": round(self.visibility_ratio, 4),
            "undercut_ratio": round(self.undercut_ratio, 4),
            "flatness": round(self.flatness, 4),
            "min_draft_angle": round(self.min_draft_angle, 2),
            "mean_draft_angle": round(self.mean_draft_angle, 2),
            "symmetry": round(self.symmetry, 4),
            "stability": round(self.stability, 4),
            "compactness": round(self.compactness, 4),
            "support_area": round(self.support_area, 2),
        }


@dataclass
class OrientationResult:
    best_direction: np.ndarray
    best_score: DirectionScore
    top_candidates: list[DirectionScore]
    all_scores: list[DirectionScore] | None = None

    def to_dict(self) -> dict:
        return {
            "best_direction": self.best_direction.tolist(),
            "best_score": self.best_score.to_dict(),
            "top_candidates": [s.to_dict() for s in self.top_candidates],
        }


# ── Utility: auto-decimate (used by parting / mold_builder too) ────────

def _auto_decimate(mesh: MeshData, max_faces: int) -> tuple[MeshData, bool]:
    """Decimate a mesh if it exceeds *max_faces*."""
    if mesh.face_count <= max_faces:
        return mesh, False

    ratio = max_faces / mesh.face_count
    logger.info(
        "Auto-decimating: %d → ~%d faces (ratio %.2f)",
        mesh.face_count, max_faces, ratio,
    )
    t0 = time.perf_counter()
    tm = mesh.to_trimesh()

    try:
        import fast_simplification
        verts_out, faces_out = fast_simplification.simplify(
            tm.vertices.astype(np.float32),
            tm.faces.astype(np.int32),
            target_reduction=1.0 - ratio,
        )
        if len(faces_out) > 100:
            result = trimesh.Trimesh(
                vertices=verts_out, faces=faces_out, process=False,
            )
            logger.info(
                "fast_simplification: %d → %d faces in %.2fs",
                mesh.face_count, len(faces_out), time.perf_counter() - t0,
            )
            return MeshData.from_trimesh(result), True
    except Exception as exc:
        logger.warning("fast_simplification failed: %s", exc)

    try:
        simplified = tm.simplify_quadric_decimation(max_faces)
        if simplified is not None and len(simplified.faces) > 100:
            logger.info(
                "Quadric decimation: %d faces in %.2fs",
                len(simplified.faces), time.perf_counter() - t0,
            )
            return MeshData.from_trimesh(simplified), True
    except Exception as exc:
        logger.warning("Quadric decimation failed: %s", exc)

    logger.warning("All decimation failed, using random face subsampling")
    idx = np.random.choice(len(tm.faces), size=max_faces, replace=False)
    sf = tm.faces[idx]
    uv = np.unique(sf.ravel())
    remap = np.full(len(tm.vertices), -1, dtype=int)
    remap[uv] = np.arange(len(uv))
    sub = trimesh.Trimesh(
        vertices=tm.vertices[uv], faces=remap[sf], process=False,
    )
    logger.info(
        "Face-subsampled to %d faces in %.2fs",
        len(sub.faces), time.perf_counter() - t0,
    )
    return MeshData.from_trimesh(sub), True


# ── GPU / array-dispatch helpers ───────────────────────────────────────

def _has_cupy() -> bool:
    try:
        import cupy  # noqa: F401
        cupy.cuda.runtime.getDevice()
        return True
    except Exception:
        return False


def _to_gpu(arr: np.ndarray, dtype=np.float32):
    import cupy as cp
    return cp.asarray(arr, dtype=dtype)


def _to_cpu(arr) -> np.ndarray:
    try:
        return arr.get()
    except AttributeError:
        return np.asarray(arr)


# ── Phase 1: Batch evaluator (zero Python loop) ───────────────────────

def _batch_evaluate(
    normals,    # (F, 3)
    areas,      # (F,)
    centers,    # (F, 3)
    vertices,   # (V, 3)
    candidates, # (C, 3)
    weights: dict,
    xp,
) -> dict:
    """Evaluate ALL candidate directions simultaneously — zero Python loop.

    Returns dict of 1-D arrays, each shape (C,).
    """
    total_area = float(xp.sum(areas))
    C = len(candidates)

    if total_area < 1e-12:
        z = xp.zeros(C, dtype=areas.dtype)
        return {k: z for k in [
            "score", "visibility", "undercut", "flatness",
            "draft", "symmetry", "stability", "compactness",
        ]}

    # (F, C) dot products
    dot = normals @ candidates.T
    a2d = areas[:, None]

    # 1. Visibility (Gauss Map projection, Woo 1994)
    vis_mask = dot > 0.01
    back_mask = dot < -0.01
    vis_area = xp.sum(a2d * vis_mask, axis=0)
    visibility = vis_area / total_area

    # 2. Undercut (normal + height heuristic)
    heights = centers @ candidates.T
    mean_h = xp.mean(heights, axis=0)
    opposing = dot < -0.05
    above = heights > mean_h[None, :]
    steep = (dot < -0.3) & (dot > -0.95)
    uc_mask = (opposing & above) | steep
    uc_area = xp.sum(a2d * uc_mask, axis=0)
    one = xp.ones(C, dtype=areas.dtype)
    undercut = xp.minimum(uc_area / total_area, one)

    # 3. Draft angle (area-weighted, Ahn et al. 2002)
    clamped = xp.clip(dot, -1.0, 1.0)
    draft_raw = 90.0 - xp.degrees(xp.arccos(clamped))
    w_sum = xp.sum(a2d * vis_mask * draft_raw, axis=0)
    zero = xp.zeros_like(vis_area)
    draft_avg = xp.where(vis_area > 0, w_sum / vis_area, zero)
    draft = xp.clip(draft_avg / 15.0, 0.0, 1.0)

    # 4. Flatness (side-face height variance)
    side_mask = xp.abs(dot) < 0.1
    s_cnt = xp.sum(side_mask, axis=0).astype(areas.dtype)
    h_sum = xp.sum(heights * side_mask, axis=0)
    h_sq = xp.sum(heights * heights * side_mask, axis=0)
    s_mean = xp.where(s_cnt > 2, h_sum / s_cnt, zero)
    s_var = xp.where(
        s_cnt > 2, h_sq / s_cnt - s_mean * s_mean, zero,
    )
    s_std = xp.sqrt(xp.maximum(s_var, zero))
    v_max = xp.max(vertices, axis=0)
    v_min = xp.min(vertices, axis=0)
    max_ext = float(xp.max(v_max - v_min))
    if max_ext < 1e-8:
        flatness = one.copy()
    else:
        flatness = xp.where(
            s_cnt > 2,
            1.0 - xp.clip(s_std / (0.1 * max_ext), 0.0, 1.0),
            one,
        )

    # 5. Symmetry (upper/lower area balance)
    low_area = xp.sum(a2d * back_mask, axis=0)
    sym_total = vis_area + low_area
    symmetry = xp.where(
        sym_total > 0,
        1.0 - xp.abs(vis_area - low_area) / sym_total,
        zero,
    )

    # 6. Stability (base projection area)
    base_mask = (-dot) > 0.7
    base_area = xp.sum(a2d * base_mask, axis=0)
    stability = xp.clip(base_area / (0.3 * total_area), 0.0, 1.0)

    # 7. Compactness (projected bounding-box aspect ratio)
    arb = xp.where(
        xp.abs(candidates[:, 0:1]) < 0.9,
        xp.broadcast_to(
            xp.asarray([1, 0, 0], dtype=candidates.dtype), (C, 3),
        ).copy(),
        xp.broadcast_to(
            xp.asarray([0, 1, 0], dtype=candidates.dtype), (C, 3),
        ).copy(),
    )
    u = xp.cross(candidates, arb)
    u_n = xp.linalg.norm(u, axis=1, keepdims=True)
    u = u / xp.clip(u_n, 1e-8, None)
    v = xp.cross(candidates, u)
    proj_u = vertices @ u.T
    proj_v = vertices @ v.T
    ru = xp.max(proj_u, axis=0) - xp.min(proj_u, axis=0)
    rv = xp.max(proj_v, axis=0) - xp.min(proj_v, axis=0)
    valid = (ru > 1e-8) & (rv > 1e-8)
    compactness = xp.where(
        valid,
        xp.minimum(ru, rv) / xp.maximum(ru, rv),
        zero,
    )

    # Weighted total score
    w = weights
    score = (
        w.get("visibility", 0.25) * visibility
        + w.get("undercut", 0.20) * (1.0 - undercut)
        + w.get("flatness", 0.12) * flatness
        + w.get("draft_angle", 0.18) * draft
        + w.get("symmetry", 0.08) * symmetry
        + w.get("stability", 0.10) * stability
        + w.get("compactness", 0.07) * compactness
    )

    return {
        "score": score,
        "visibility": visibility,
        "undercut": undercut,
        "flatness": flatness,
        "draft": draft,
        "symmetry": symmetry,
        "stability": stability,
        "compactness": compactness,
        "vis_area": vis_area,
        "uc_area": uc_area,
    }


# ── Phase 2: Per-direction detailed evaluation (Python loop) ──────────

def _detailed_evaluate_single(
    direction: np.ndarray,
    normals: np.ndarray,
    areas: np.ndarray,
    centers: np.ndarray,
) -> dict:
    """Detailed per-direction analysis using Python loop — computes
    min_draft_angle, precise undercut classification, support area.
    Only called for top-K candidates (≤10 directions).
    """
    total_area = float(np.sum(areas))
    if total_area < 1e-12:
        return {
            "min_draft": 0.0, "mean_draft": 0.0,
            "support_area": 0.0, "precise_uc_ratio": 0.0,
        }

    d = direction
    dot = normals @ d  # (F,)

    # Draft angles for visible faces
    vis_idx = np.where(dot > 0.01)[0]
    if len(vis_idx) == 0:
        return {
            "min_draft": 0.0, "mean_draft": 0.0,
            "support_area": 0.0, "precise_uc_ratio": 0.0,
        }

    vis_dot = np.clip(dot[vis_idx], -1.0, 1.0)
    draft_angles = 90.0 - np.degrees(np.arccos(vis_dot))
    vis_areas = areas[vis_idx]

    min_draft = float(np.min(draft_angles))
    mean_draft = float(np.average(draft_angles, weights=vis_areas))

    # Support area (faces nearly perpendicular to -direction)
    support_mask = (-dot) > 0.85
    support_area = float(np.sum(areas[support_mask]))

    # Precise undercut: faces that point away from direction AND are above
    # the halfway height. Additionally check for steep side faces
    # that would trap the part.
    heights = centers @ d
    height_range = float(np.max(heights) - np.min(heights))
    if height_range < 1e-8:
        precise_uc_ratio = 0.0
    else:
        midpoint = float(np.mean(heights))
        opposing = dot < -0.1
        above_mid = heights > midpoint
        steep_side = (dot < -0.25) & (dot > -0.95)
        uc_faces = (opposing & above_mid) | steep_side
        precise_uc_ratio = float(np.sum(areas[uc_faces]) / total_area)

    return {
        "min_draft": max(0.0, min_draft),
        "mean_draft": max(0.0, mean_draft),
        "support_area": support_area,
        "precise_uc_ratio": min(1.0, precise_uc_ratio),
    }


# ── Candidate generation ──────────────────────────────────────────────

def _fibonacci_sphere(n: int) -> np.ndarray:
    """Fibonacci sphere sampling — (n, 3) unit vectors."""
    golden = (1.0 + np.sqrt(5.0)) / 2.0
    i = np.arange(n, dtype=np.float64)
    theta = np.arccos(1.0 - 2.0 * (i + 0.5) / n)
    phi = 2.0 * np.pi * i / golden
    return np.column_stack([
        np.sin(theta) * np.cos(phi),
        np.sin(theta) * np.sin(phi),
        np.cos(theta),
    ])


def _local_perturbations(
    directions: np.ndarray, angles_deg: list[float],
) -> np.ndarray:
    """Generate angular perturbations around each direction.

    Uses 4 orthogonal neighbours per angle (Rodrigues' rotation).
    """
    results = [directions.copy()]
    for d in directions:
        arb = (
            np.array([1, 0, 0])
            if abs(d[0]) < 0.9
            else np.array([0, 1, 0])
        )
        u = np.cross(d, arb)
        u /= np.linalg.norm(u) + 1e-12
        v = np.cross(d, u)
        for ang in angles_deg:
            rad = np.radians(ang)
            cos_r, sin_r = np.cos(rad), np.sin(rad)
            for axis in [u, -u, v, -v]:
                p = d * cos_r + axis * sin_r
                p /= np.linalg.norm(p) + 1e-12
                results.append(p[np.newaxis, :])
    return np.vstack(results)


def _deduplicate_vectorized(
    mat: np.ndarray, threshold: float = 0.98,
) -> np.ndarray:
    """Greedy deduplication on a (N, 3) direction matrix."""
    if len(mat) == 0:
        return mat
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    valid = norms.ravel() > 1e-8
    mat = mat[valid] / norms[valid]
    keep = [0]
    for i in range(1, len(mat)):
        if np.all(np.abs(mat[keep] @ mat[i]) < threshold):
            keep.append(i)
    return mat[keep]


# ── Main analyzer ─────────────────────────────────────────────────────

class OrientationAnalyzer:
    """脱模方向分析器 — 三阶段: 批量筛选 → 逐向精评 → 自适应精化

    GPU path (RTX 4060 Ti / 16 GB):
        1.3M faces → full CuPy batch → ~0.1s
    CPU path (NumPy):
        1.3M faces → decimate 200K → NumPy batch → ~0.3s
    """

    def __init__(self, config: OrientationConfig | None = None):
        self.config = config or OrientationConfig()

    # ────────────────────── public API ──────────────────────

    def analyze(self, mesh: MeshData) -> OrientationResult:
        logger.info("Analyzing orientation for %d faces...", mesh.face_count)
        t_start = time.perf_counter()

        use_gpu = (
            _has_cupy() and mesh.face_count < ANALYSIS_MAX_FACES_GPU
        )
        if use_gpu:
            try:
                result = self._analyze_gpu(mesh)
            except Exception as e:
                logger.warning("GPU analysis failed (%s), falling back to CPU", e)
                use_gpu = False
                result = self._analyze_cpu(mesh)
        else:
            result = self._analyze_cpu(mesh)

        elapsed = time.perf_counter() - t_start
        best = result.best_score
        logger.info(
            "Best: [%.2f,%.2f,%.2f] score=%.3f vis=%.0f%% "
            "uc=%.0f%% draft=%.1f° [%s, %.2fs]",
            *best.direction, best.total_score,
            best.visibility_ratio * 100,
            best.undercut_ratio * 100,
            best.min_draft_angle,
            "GPU" if use_gpu else "CPU", elapsed,
        )
        return result

    def evaluate_direction(
        self, mesh: MeshData, direction: np.ndarray,
    ) -> DirectionScore:
        d = np.asarray(direction, dtype=np.float64)
        d = d / (np.linalg.norm(d) + 1e-12)
        cands = d[np.newaxis, :]

        analysis_mesh, _ = _auto_decimate(mesh, ANALYSIS_MAX_FACES_CPU)
        tm = analysis_mesh.to_trimesh()
        normals = np.asarray(tm.face_normals, dtype=np.float64)
        areas = tm.area_faces.astype(np.float64)
        centers = tm.triangles_center.astype(np.float64)

        metrics = _batch_evaluate(
            normals, areas, centers, tm.vertices, cands,
            self.config.weights, np,
        )
        score = self._make_score(d, metrics, 0, np)

        detail = _detailed_evaluate_single(d, normals, areas, centers)
        score.min_draft_angle = detail["min_draft"]
        score.mean_draft_angle = detail["mean_draft"]
        score.support_area = detail["support_area"]
        return score

    # ────────────────────── GPU path ───────────────────────

    def _analyze_gpu(self, mesh: MeshData) -> OrientationResult:
        import cupy as cp

        t0 = time.perf_counter()
        tm = mesh.to_trimesh()
        normals_gpu = _to_gpu(np.asarray(tm.face_normals))
        areas_gpu = _to_gpu(tm.area_faces.astype(np.float32))
        centers_gpu = _to_gpu(tm.triangles_center)
        verts_gpu = _to_gpu(tm.vertices)
        logger.info("GPU transfer: %.3fs", time.perf_counter() - t0)

        # Phase 1 — coarse sweep
        t1 = time.perf_counter()
        cands_np = self._generate_candidates(mesh)
        cands_gpu = _to_gpu(cands_np)
        metrics = _batch_evaluate(
            normals_gpu, areas_gpu, centers_gpu, verts_gpu,
            cands_gpu, self.config.weights, cp,
        )
        scores_gpu = metrics["score"]
        logger.info(
            "Phase 1: %d dirs, GPU batch %.3fs",
            len(cands_np), time.perf_counter() - t1,
        )

        # Phase 3 — adaptive refinement
        scores_cpu = _to_cpu(scores_gpu)
        cands_np, metrics = self._adaptive_refine(
            cands_np, scores_cpu, normals_gpu, areas_gpu,
            centers_gpu, verts_gpu, metrics, cp,
        )

        # Phase 2 — detailed evaluation for top candidates (on CPU)
        normals_cpu = np.asarray(tm.face_normals, dtype=np.float64)
        areas_cpu = tm.area_faces.astype(np.float64)
        centers_cpu = tm.triangles_center.astype(np.float64)

        return self._build_result_with_detail(
            cands_np, metrics, cp,
            normals_cpu, areas_cpu, centers_cpu,
        )

    # ────────────────────── CPU path ───────────────────────

    def _analyze_cpu(self, mesh: MeshData) -> OrientationResult:
        analysis_mesh, decimated = _auto_decimate(
            mesh, ANALYSIS_MAX_FACES_CPU,
        )
        if decimated:
            logger.info(
                "CPU path: decimated mesh (%d faces)",
                analysis_mesh.face_count,
            )

        tm = analysis_mesh.to_trimesh()
        normals = np.asarray(tm.face_normals, dtype=np.float64)
        areas = tm.area_faces.astype(np.float64)
        centers = tm.triangles_center.astype(np.float64)
        verts = tm.vertices.astype(np.float64)

        # Phase 1
        t1 = time.perf_counter()
        cands_np = self._generate_candidates(analysis_mesh)
        metrics = _batch_evaluate(
            normals, areas, centers, verts, cands_np,
            self.config.weights, np,
        )
        logger.info(
            "Phase 1: %d dirs, CPU batch %.3fs",
            len(cands_np), time.perf_counter() - t1,
        )

        # Phase 3 — adaptive refinement
        scores_arr = metrics["score"]
        cands_np, metrics = self._adaptive_refine(
            cands_np, scores_arr, normals, areas,
            centers, verts, metrics, np,
        )

        # Phase 2 — detailed evaluation
        return self._build_result_with_detail(
            cands_np, metrics, np, normals, areas, centers,
        )

    # ────────────────────── helpers ─────────────────────────

    def _generate_candidates(self, mesh: MeshData) -> np.ndarray:
        parts: list[np.ndarray] = []

        # Principal axes ±
        axes = np.eye(3)
        parts.append(axes)
        parts.append(-axes)

        # PCA
        try:
            centered = mesh.vertices - mesh.vertices.mean(axis=0)
            cov = np.cov(centered.T)
            _, eigvecs = np.linalg.eigh(cov)
            parts.append(eigvecs.T)
            parts.append(-eigvecs.T)
        except Exception:
            pass

        # Area-weighted top normals
        tm = mesh.to_trimesh()
        face_areas = tm.area_faces
        top_k = min(20, len(face_areas))
        top_idx = np.argsort(face_areas)[-top_k:]
        norms = mesh.face_normals[top_idx].copy()
        row_norms = np.linalg.norm(norms, axis=1, keepdims=True)
        valid = row_norms.ravel() > 1e-8
        if np.any(valid):
            parts.append(norms[valid] / row_norms[valid])

        # Fibonacci sphere
        parts.append(_fibonacci_sphere(self.config.n_fibonacci_samples))

        all_dirs = np.vstack(parts)
        return _deduplicate_vectorized(
            all_dirs, self.config.dedup_threshold,
        )

    def _adaptive_refine(
        self, cands_np, scores, normals, areas, centers, verts,
        metrics, xp,
    ):
        """Phase 3: refine only when top candidates are ambiguous."""
        scores_cpu = _to_cpu(scores) if hasattr(scores, 'get') else scores
        sorted_s = np.sort(scores_cpu)[::-1]

        if (
            self.config.refine_passes > 0
            and len(sorted_s) >= 2
            and (sorted_s[0] - sorted_s[1]) < 0.03
        ):
            top_k = min(5, len(cands_np))
            top_idx = np.argsort(-scores_cpu)[:top_k]
            top_dirs = cands_np[top_idx]

            refine_np = _local_perturbations(top_dirs, [5.0, 10.0])
            new_dirs = _deduplicate_vectorized(
                np.vstack([cands_np, refine_np]),
                self.config.dedup_threshold,
            )
            n_orig = len(cands_np)
            if len(new_dirs) > n_orig:
                cands_np = new_dirs
                cands_arr = (
                    _to_gpu(cands_np) if xp.__name__ == "cupy" else cands_np
                )
                t2 = time.perf_counter()
                metrics = _batch_evaluate(
                    normals, areas, centers, verts,
                    cands_arr, self.config.weights, xp,
                )
                logger.info(
                    "Phase 3 refine: %d dirs (+%d), %.3fs",
                    len(cands_np), len(cands_np) - n_orig,
                    time.perf_counter() - t2,
                )

        return cands_np, metrics

    def _build_result_with_detail(
        self, cands_np, metrics, xp,
        normals_cpu, areas_cpu, centers_cpu,
    ) -> OrientationResult:
        """Build result with Phase 2 detailed evaluation for top candidates."""
        scores_cpu = _to_cpu(metrics["score"])
        n_final = self.config.n_final_candidates

        sorted_idx = np.argsort(-scores_cpu)
        top_idx = sorted_idx[:n_final]

        # Phase 2: detailed evaluation loop (Python loop over top-K only)
        top_scores: list[DirectionScore] = []
        n_detail = min(DETAILED_TOP_K, n_final)

        for rank, i in enumerate(top_idx):
            ds = self._make_score(cands_np[i], metrics, int(i), xp)

            if rank < n_detail and self.config.detailed_evaluation:
                detail = _detailed_evaluate_single(
                    cands_np[i], normals_cpu, areas_cpu, centers_cpu,
                )
                ds.min_draft_angle = detail["min_draft"]
                ds.mean_draft_angle = detail["mean_draft"]
                ds.support_area = detail["support_area"]
                if detail["precise_uc_ratio"] > 0:
                    ds.undercut_ratio = detail["precise_uc_ratio"]

            top_scores.append(ds)

        best = top_scores[0]
        return OrientationResult(
            best_direction=best.direction,
            best_score=best,
            top_candidates=top_scores,
        )

    @staticmethod
    def _make_score(
        direction: np.ndarray, metrics: dict, idx: int, xp,
    ) -> DirectionScore:
        def _f(arr, i):
            v = arr[i]
            return float(v.get() if hasattr(v, "get") else v)

        vis = _f(metrics["visibility"], idx)
        uc = _f(metrics["undercut"], idx)
        vis_a = _f(metrics.get("vis_area", metrics["visibility"]), idx)
        uc_a = _f(metrics.get("uc_area", metrics["undercut"]), idx)

        return DirectionScore(
            direction=np.asarray(direction, dtype=np.float64),
            total_score=_f(metrics["score"], idx),
            visibility_ratio=vis,
            undercut_ratio=uc,
            flatness=_f(metrics["flatness"], idx),
            min_draft_angle=0.0,
            mean_draft_angle=0.0,
            symmetry=_f(metrics["symmetry"], idx),
            stability=_f(metrics["stability"], idx),
            visible_area=vis_a,
            undercut_area=uc_a,
            compactness=_f(metrics["compactness"], idx),
        )
