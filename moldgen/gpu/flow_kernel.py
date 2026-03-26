"""流动仿真内核 — Darcy 流体求解

提供 GPU (CuPy) 和 CPU (SciPy) 两种求解器。
用于灌注仿真中的压力场、速度场计算。
"""

from __future__ import annotations

import logging
import numpy as np

logger = logging.getLogger(__name__)


def solve_pressure_field(
    sdf_grid: np.ndarray,
    gate_positions: list[np.ndarray],
    vent_positions: list[np.ndarray],
    grid_info: dict,
    viscosity: float = 5.0,
    permeability: float = 1e-10,
    use_gpu: bool | None = None,
) -> dict:
    """Solve Darcy flow pressure field on a voxel grid.

    Returns dict with pressure, velocity, fill_order arrays.
    """
    if use_gpu is None:
        from moldgen.gpu.device import GPUDevice
        use_gpu = GPUDevice().info.cupy_available

    res = sdf_grid.shape
    pitch = np.array(grid_info["pitch"])
    origin = np.array(grid_info["origin"])

    cavity_mask = sdf_grid < 0

    if use_gpu:
        try:
            return _solve_gpu(sdf_grid, cavity_mask, gate_positions, vent_positions,
                              origin, pitch, res, viscosity, permeability)
        except Exception as e:
            logger.warning("GPU flow solver failed, falling back to CPU: %s", e)

    return _solve_cpu(sdf_grid, cavity_mask, gate_positions, vent_positions,
                      origin, pitch, res, viscosity, permeability)


def _pos_to_voxel(pos: np.ndarray, origin: np.ndarray, pitch: np.ndarray, shape: tuple) -> tuple[int, ...]:
    idx = np.round((pos - origin) / pitch).astype(int)
    idx = np.clip(idx, 0, np.array(shape) - 1)
    return tuple(idx)


def _solve_cpu(
    sdf_grid, cavity_mask, gates, vents,
    origin, pitch, res, viscosity, permeability,
) -> dict:
    """Iterative Jacobi pressure solver on CPU (NumPy)."""
    pressure = np.zeros(res, dtype=np.float64)
    fill_order = np.full(res, -1, dtype=np.int32)

    p_gate = 1.0
    p_vent = 0.0

    gate_voxels = [_pos_to_voxel(np.asarray(g), origin, pitch, res) for g in gates]
    vent_voxels = [_pos_to_voxel(np.asarray(v), origin, pitch, res) for v in vents]

    for gv in gate_voxels:
        pressure[gv] = p_gate
    for vv in vent_voxels:
        pressure[vv] = p_vent

    max_iter = 500
    tol = 1e-4
    k = permeability / viscosity

    for iteration in range(max_iter):
        old = pressure.copy()

        pad = np.pad(pressure, 1, mode="edge")
        laplacian = (
            pad[2:, 1:-1, 1:-1] + pad[:-2, 1:-1, 1:-1]
            + pad[1:-1, 2:, 1:-1] + pad[1:-1, :-2, 1:-1]
            + pad[1:-1, 1:-1, 2:] + pad[1:-1, 1:-1, :-2]
            - 6 * pressure
        )

        pressure += 0.15 * laplacian * cavity_mask

        for gv in gate_voxels:
            pressure[gv] = p_gate
        for vv in vent_voxels:
            pressure[vv] = p_vent
        pressure[~cavity_mask] = 0

        diff = np.abs(pressure - old).max()
        if diff < tol:
            break

    grad_x = np.gradient(pressure, pitch[0], axis=0)
    grad_y = np.gradient(pressure, pitch[1], axis=1)
    grad_z = np.gradient(pressure, pitch[2], axis=2)
    velocity = np.stack([grad_x, grad_y, grad_z], axis=-1) * (-k)
    speed = np.linalg.norm(velocity, axis=-1)

    cavity_pressures = pressure[cavity_mask]
    if cavity_pressures.size > 0:
        sorted_vals = np.sort(cavity_pressures.ravel())[::-1]
        thresholds = np.linspace(sorted_vals[0], sorted_vals[-1], 100)
        for step, th in enumerate(thresholds):
            fill_order[(pressure >= th) & cavity_mask & (fill_order < 0)] = step

    return {
        "pressure": pressure,
        "velocity": velocity,
        "speed": speed,
        "fill_order": fill_order,
        "cavity_mask": cavity_mask,
        "iterations": iteration + 1 if 'iteration' in dir() else max_iter,
        "converged": diff < tol if 'diff' in dir() else False,
    }


def _solve_gpu(
    sdf_grid, cavity_mask, gates, vents,
    origin, pitch, res, viscosity, permeability,
) -> dict:
    """GPU-accelerated Jacobi solver using CuPy."""
    import cupy as cp

    pressure = cp.zeros(res, dtype=cp.float64)
    cavity_g = cp.asarray(cavity_mask)

    p_gate = 1.0
    p_vent = 0.0

    gate_voxels = [_pos_to_voxel(np.asarray(g), origin, pitch, res) for g in gates]
    vent_voxels = [_pos_to_voxel(np.asarray(v), origin, pitch, res) for v in vents]

    for gv in gate_voxels:
        pressure[gv] = p_gate
    for vv in vent_voxels:
        pressure[vv] = p_vent

    max_iter = 500
    tol = 1e-4
    k = permeability / viscosity

    for iteration in range(max_iter):
        old = pressure.copy()

        pad = cp.pad(pressure, 1, mode="edge")
        laplacian = (
            pad[2:, 1:-1, 1:-1] + pad[:-2, 1:-1, 1:-1]
            + pad[1:-1, 2:, 1:-1] + pad[1:-1, :-2, 1:-1]
            + pad[1:-1, 1:-1, 2:] + pad[1:-1, 1:-1, :-2]
            - 6 * pressure
        )

        pressure += 0.15 * laplacian * cavity_g

        for gv in gate_voxels:
            pressure[gv] = p_gate
        for vv in vent_voxels:
            pressure[vv] = p_vent
        pressure[~cavity_g] = 0

        diff = float(cp.abs(pressure - old).max())
        if diff < tol:
            break

    pressure_np = cp.asnumpy(pressure)
    pitch_np = np.array(pitch)
    grad_x = np.gradient(pressure_np, pitch_np[0], axis=0)
    grad_y = np.gradient(pressure_np, pitch_np[1], axis=1)
    grad_z = np.gradient(pressure_np, pitch_np[2], axis=2)
    velocity = np.stack([grad_x, grad_y, grad_z], axis=-1) * (-k)
    speed = np.linalg.norm(velocity, axis=-1)

    fill_order = np.full(res, -1, dtype=np.int32)
    cavity_mask_np = cp.asnumpy(cavity_g)
    cavity_pressures = pressure_np[cavity_mask_np]
    if cavity_pressures.size > 0:
        sorted_vals = np.sort(cavity_pressures.ravel())[::-1]
        thresholds = np.linspace(sorted_vals[0], sorted_vals[-1], 100)
        for step, th in enumerate(thresholds):
            fill_order[(pressure_np >= th) & cavity_mask_np & (fill_order < 0)] = step

    return {
        "pressure": pressure_np,
        "velocity": velocity,
        "speed": speed,
        "fill_order": fill_order,
        "cavity_mask": cavity_mask_np,
        "iterations": iteration + 1,
        "converged": diff < tol,
    }


def compute_fill_animation(
    fill_order: np.ndarray,
    n_frames: int = 50,
) -> list[np.ndarray]:
    """Generate animation frames from fill order field."""
    max_order = fill_order.max()
    if max_order <= 0:
        return [np.zeros_like(fill_order, dtype=np.float32)]

    frames = []
    for i in range(n_frames):
        threshold = int(max_order * (i + 1) / n_frames)
        frame = ((fill_order >= 0) & (fill_order <= threshold)).astype(np.float32)
        frames.append(frame)
    return frames
