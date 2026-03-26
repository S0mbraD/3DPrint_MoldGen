import { motion } from "framer-motion";
import { useAppStore, STEP_ORDER } from "../../stores/appStore";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useInsertStore } from "../../stores/insertStore";
import { useSimStore } from "../../stores/simStore";
import { cn } from "../../lib/utils";
import {
  Upload, Scissors, Compass, Box, Layers, Droplets, Zap, Download,
} from "lucide-react";

type LucideIcon = React.ComponentType<{ size?: number; className?: string }>;

const STEP_META: Record<string, { icon: LucideIcon; label: string; shortLabel: string; desc: string }> = {
  import: { icon: Upload, label: "导入模型", shortLabel: "导入", desc: "加载 3D 网格" },
  repair: { icon: Scissors, label: "编辑修复", shortLabel: "修复", desc: "网格修复与分析" },
  orientation: { icon: Compass, label: "方向分析", shortLabel: "方向", desc: "脱模方向优化" },
  mold: { icon: Box, label: "模具设计", shortLabel: "模具", desc: "壳体与冷却通道" },
  insert: { icon: Layers, label: "内骨骼", shortLabel: "骨骼", desc: "TPMS 晶格结构" },
  gating: { icon: Droplets, label: "浇注系统", shortLabel: "浇注", desc: "浇道与浇口" },
  simulation: { icon: Zap, label: "仿真分析", shortLabel: "仿真", desc: "充模与 FEA" },
  export: { icon: Download, label: "导出", shortLabel: "导出", desc: "STL / 3MF / BOM" },
};

interface StepStatusInfo {
  status: "idle" | "active" | "done" | "error";
  dataLabel?: string;
}

function useStepStatus(): Record<string, StepStatusInfo> {
  const currentStep = useAppStore((s) => s.currentStep);
  const modelId = useModelStore((s) => s.modelId);
  const meshInfo = useModelStore((s) => s.meshInfo);
  const orientationResult = useMoldStore((s) => s.orientationResult);
  const moldId = useMoldStore((s) => s.moldId);
  const moldResult = useMoldStore((s) => s.moldResult);
  const insertId = useInsertStore((s) => s.insertId);
  const plates = useInsertStore((s) => s.plates);
  const gatingId = useSimStore((s) => s.gatingId);
  const simResult = useSimStore((s) => s.simResult);

  const out: Record<string, StepStatusInfo> = {};
  for (const step of STEP_ORDER) {
    let status: StepStatusInfo["status"] = "idle";
    let dataLabel: string | undefined;

    if (step === currentStep) status = "active";

    if (step === "import" && modelId) {
      status = step === currentStep ? "active" : "done";
      dataLabel = meshInfo ? `${(meshInfo.face_count / 1000).toFixed(0)}k 面` : undefined;
    }
    if (step === "repair" && modelId) {
      status = step === currentStep ? "active" : "done";
    }
    if (step === "orientation" && orientationResult) {
      status = step === currentStep ? "active" : "done";
      dataLabel = `${orientationResult.best_score?.min_draft_angle?.toFixed(0) ?? "?"}° 拔模`;
    }
    if (step === "mold" && moldId) {
      status = step === currentStep ? "active" : "done";
      dataLabel = moldResult ? `${moldResult.n_shells} 壳` : undefined;
    }
    if (step === "insert" && insertId) {
      status = step === currentStep ? "active" : "done";
      dataLabel = plates.length > 0 ? `${plates.length} 板` : undefined;
    }
    if (step === "gating" && gatingId) {
      status = step === currentStep ? "active" : "done";
    }
    if (step === "simulation" && simResult) {
      status = step === currentStep ? "active" : "done";
      dataLabel = simResult.fill_fraction != null ? `${(simResult.fill_fraction * 100).toFixed(0)}% 充填` : undefined;
    }

    out[step] = { status, dataLabel };
  }
  return out;
}

export function WorkflowPipeline() {
  const { currentStep, setStep } = useAppStore();
  const statuses = useStepStatus();
  const completedCount = Object.values(statuses).filter(s => s.status === "done").length;

  return (
    <div className="w-full h-8 flex items-center px-2 bg-bg-panel border-b border-border overflow-x-auto shrink-0">
      {/* Thin progress bar */}
      <div className="absolute left-0 right-0 top-0 h-[2px] bg-bg-hover overflow-hidden pointer-events-none">
        <motion.div
          className="h-full bg-accent/50"
          animate={{ width: `${(completedCount / STEP_ORDER.length) * 100}%` }}
          transition={{ type: "spring", stiffness: 200, damping: 30 }}
        />
      </div>

      <div className="flex items-center gap-0 flex-1 min-w-max">
        {STEP_ORDER.map((step, i) => {
          const meta = STEP_META[step];
          const Icon = meta.icon;
          const { status: st, dataLabel } = statuses[step];
          const isActive = step === currentStep;

          return (
            <div key={step} className="flex items-center">
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setStep(step as typeof currentStep)}
                className={cn(
                  "relative flex items-center gap-1.5 px-2.5 h-6 rounded-md transition-all group",
                  isActive
                    ? "bg-accent/15 ring-1 ring-accent/40"
                    : st === "done"
                      ? "bg-success/8 hover:bg-success/12"
                      : "hover:bg-bg-hover",
                )}
              >
                <div className={cn(
                  "w-4 h-4 rounded flex items-center justify-center transition-colors shrink-0",
                  isActive
                    ? "bg-accent text-white"
                    : st === "done"
                      ? "bg-success/20 text-success"
                      : "bg-bg-hover text-text-muted",
                )}>
                  {st === "done" && !isActive ? (
                    <span className="text-[10px] font-bold leading-none">✓</span>
                  ) : (
                    <Icon size={11} />
                  )}
                </div>

                <span className={cn(
                  "text-[11px] font-medium leading-none whitespace-nowrap",
                  isActive ? "text-accent" : st === "done" ? "text-success/80" : "text-text-muted",
                )}>
                  {meta.shortLabel}
                </span>

                {dataLabel && st === "done" && !isActive && (
                  <span className="text-[9px] text-success/60 leading-none whitespace-nowrap">
                    {dataLabel}
                  </span>
                )}

                {/* Tooltip */}
                <div className="absolute top-full mt-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-50 whitespace-nowrap pointer-events-none">
                  <div className="bg-bg-primary border border-border rounded px-2 py-1 text-[10px] text-text-muted shadow-lg">
                    {meta.label} — {meta.desc}
                  </div>
                </div>

                {isActive && (
                  <motion.div
                    className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-accent"
                    animate={{ scale: [1, 1.3, 1], opacity: [1, 0.5, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  />
                )}
              </motion.button>

              {i < STEP_ORDER.length - 1 && (
                <div className="flex items-center px-0.5 relative">
                  <div className={cn(
                    "w-3 h-[1.5px] rounded-full transition-colors",
                    st === "done" ? "bg-success/40" : "bg-border/40",
                  )} />
                  <div className={cn(
                    "w-0 h-0 border-t-[2px] border-t-transparent border-b-[2px] border-b-transparent transition-colors",
                    st === "done" ? "border-l-[2.5px] border-l-success/40" : "border-l-[2.5px] border-l-border/40",
                  )} />
                </div>
              )}
            </div>
          );
        })}

        {/* Overall progress */}
        <div className="ml-2 pl-2 border-l border-border/30 flex items-center gap-1">
          <span className={cn("text-[11px] font-bold tabular-nums",
            completedCount === STEP_ORDER.length ? "text-success" : "text-text-muted")}>
            {completedCount}/{STEP_ORDER.length}
          </span>
          <span className="text-[10px] text-text-muted/50">完成</span>
        </div>
      </div>
    </div>
  );
}
