"""自动优化器 — 基于仿真缺陷的参数自动调整（改进版：自适应步长 + 多准则收敛）"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from moldgen.core.flow_sim import FlowDefect, FlowSimulator, SimConfig, SimulationResult
from moldgen.core.gating import GatingConfig, GatingResult, GatingSystem
from moldgen.core.material import MaterialProperties
from moldgen.core.mesh_data import MeshData
from moldgen.core.mold_builder import MoldResult

logger = logging.getLogger(__name__)


@dataclass
class OptimizationConfig:
    max_iterations: int = 8
    target_fill_fraction: float = 0.99
    target_max_defect_severity: float = 0.15
    improvement_threshold: float = 0.003
    sim_level: int = 1
    adaptive_step: bool = True
    initial_step_scale: float = 1.0
    step_decay: float = 0.7
    max_gate_diameter: float = 30.0
    max_runner_width: float = 15.0
    max_vents: int = 16


@dataclass
class OptimizationStep:
    iteration: int
    action: str
    fill_fraction: float
    n_defects: int
    max_severity: float
    parameter_changes: dict
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "action": self.action,
            "fill_fraction": round(float(self.fill_fraction), 4),
            "n_defects": self.n_defects,
            "max_severity": round(float(self.max_severity), 3),
            "parameter_changes": self.parameter_changes,
            "score": round(float(self.score), 4),
        }


@dataclass
class OptimizationResult:
    converged: bool = False
    iterations: int = 0
    initial_fill_fraction: float = 0.0
    final_fill_fraction: float = 0.0
    initial_defects: int = 0
    final_defects: int = 0
    initial_score: float = 0.0
    final_score: float = 0.0
    steps: list[OptimizationStep] = field(default_factory=list)
    final_gating: GatingResult | None = None
    final_simulation: SimulationResult | None = None

    def to_dict(self) -> dict:
        return {
            "converged": self.converged,
            "iterations": self.iterations,
            "initial_fill_fraction": round(float(self.initial_fill_fraction), 4),
            "final_fill_fraction": round(float(self.final_fill_fraction), 4),
            "initial_defects": self.initial_defects,
            "final_defects": self.final_defects,
            "initial_score": round(float(self.initial_score), 4),
            "final_score": round(float(self.final_score), 4),
            "steps": [s.to_dict() for s in self.steps],
            "final_simulation": self.final_simulation.to_dict() if self.final_simulation else None,
        }


class AutoOptimizer:
    """Rule-based auto-optimizer with adaptive step sizes and multi-criteria convergence."""

    def __init__(self, config: OptimizationConfig | None = None):
        self.config = config or OptimizationConfig()

    def optimize(
        self,
        model: MeshData,
        mold: MoldResult,
        material: MaterialProperties,
        initial_gating: GatingResult,
    ) -> OptimizationResult:
        logger.info("Starting auto-optimization (max %d iterations)", self.config.max_iterations)

        sim_config = SimConfig(level=self.config.sim_level, voxel_resolution=48)
        simulator = FlowSimulator(sim_config)

        gating_config = GatingConfig(
            gate_diameter=initial_gating.gate_diameter,
            runner_width=initial_gating.runner_width,
        )

        current_gating = initial_gating
        result = OptimizationResult()

        # Initial simulation
        sim = simulator.simulate(model, current_gating, material)
        result.initial_fill_fraction = sim.fill_fraction
        result.initial_defects = len(sim.defects)
        result.initial_score = self._compute_score(sim)

        prev_score = result.initial_score
        step_scale = self.config.initial_step_scale
        no_improve_count = 0

        for i in range(self.config.max_iterations):
            score = self._compute_score(sim)

            # Check convergence
            if self._is_converged(sim):
                logger.info("Converged at iteration %d (score=%.3f)", i, score)
                result.converged = True
                break

            # Apply rule-based adjustments with adaptive step
            action, changes = self._apply_rules(sim.defects, gating_config, material, step_scale)

            step = OptimizationStep(
                iteration=i + 1,
                action=action,
                fill_fraction=sim.fill_fraction,
                n_defects=len(sim.defects),
                max_severity=max((d.severity for d in sim.defects), default=0.0),
                parameter_changes=changes,
                score=score,
            )
            result.steps.append(step)

            # Rebuild gating
            gating_system = GatingSystem(gating_config)
            current_gating = gating_system.design(mold, model, material)

            # Re-simulate
            sim = simulator.simulate(model, current_gating, material)
            new_score = self._compute_score(sim)

            improvement = new_score - prev_score
            if improvement < self.config.improvement_threshold:
                no_improve_count += 1
                if self.config.adaptive_step:
                    step_scale *= self.config.step_decay
                    logger.info("Reducing step scale to %.2f", step_scale)
            else:
                no_improve_count = 0
                if self.config.adaptive_step:
                    step_scale = min(step_scale * 1.1, self.config.initial_step_scale)

            # Early stop if stuck
            if no_improve_count >= 3:
                logger.info("No improvement for 3 iterations, stopping")
                break

            prev_score = new_score

        result.iterations = len(result.steps)
        result.final_fill_fraction = sim.fill_fraction
        result.final_defects = len(sim.defects)
        result.final_score = self._compute_score(sim)
        result.final_gating = current_gating
        result.final_simulation = sim

        if not result.converged:
            result.converged = self._is_converged(sim)

        logger.info(
            "Optimization done: %d iters, fill %.1f%%→%.1f%%, defects %d→%d, score %.3f→%.3f",
            result.iterations,
            result.initial_fill_fraction * 100, result.final_fill_fraction * 100,
            result.initial_defects, result.final_defects,
            result.initial_score, result.final_score,
        )
        return result

    def _compute_score(self, sim: SimulationResult) -> float:
        """Composite quality score (0-1, higher is better)."""
        fill_score = min(sim.fill_fraction / self.config.target_fill_fraction, 1.0)

        if sim.defects:
            max_sev = max(d.severity for d in sim.defects)
            defect_penalty = max_sev * 0.5 + len(sim.defects) * 0.05
        else:
            defect_penalty = 0.0

        return max(0.0, 0.7 * fill_score + 0.3 * (1.0 - min(defect_penalty, 1.0)))

    def _is_converged(self, sim: SimulationResult) -> bool:
        if sim.fill_fraction < self.config.target_fill_fraction:
            return False
        if not sim.defects:
            return True
        max_sev = max(d.severity for d in sim.defects)
        return max_sev <= self.config.target_max_defect_severity

    def _apply_rules(
        self, defects: list[FlowDefect],
        gating_config: GatingConfig,
        material: MaterialProperties,
        step_scale: float,
    ) -> tuple[str, dict]:
        """Apply heuristic rules with adaptive step sizes."""
        changes: dict = {}
        actions: list[str] = []

        # Sort defects by severity
        sorted_defects = sorted(defects, key=lambda d: d.severity, reverse=True)

        for defect in sorted_defects:
            scale = step_scale * (0.5 + 0.5 * defect.severity)

            if defect.defect_type == "short_shot":
                old = gating_config.gate_diameter
                increase = max(1.0, old * 0.2 * scale)
                gating_config.gate_diameter = min(old + increase, self.config.max_gate_diameter)
                changes["gate_diameter"] = f"{old:.1f} → {gating_config.gate_diameter:.1f}"
                actions.append("增大浇口")

            elif defect.defect_type == "air_trap":
                old = gating_config.n_vents
                add_vents = max(1, int(2 * scale))
                gating_config.n_vents = min(old + add_vents, self.config.max_vents)
                changes["n_vents"] = f"{old} → {gating_config.n_vents}"
                actions.append("增加排气孔")

            elif defect.defect_type == "weld_line":
                old = gating_config.runner_width
                increase = max(0.5, old * 0.15 * scale)
                gating_config.runner_width = min(old + increase, self.config.max_runner_width)
                changes["runner_width"] = f"{old:.1f} → {gating_config.runner_width:.1f}"
                actions.append("加宽流道")

            elif defect.defect_type == "slow_fill":
                old_gate = gating_config.gate_diameter
                increase = max(0.5, old_gate * 0.1 * scale)
                gating_config.gate_diameter = min(old_gate + increase, self.config.max_gate_diameter)
                changes["gate_diameter_slow"] = f"{old_gate:.1f} → {gating_config.gate_diameter:.1f}"
                actions.append("微调浇口")

        action_str = " + ".join(dict.fromkeys(actions)) if actions else "无调整"
        return action_str, changes
