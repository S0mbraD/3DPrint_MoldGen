import { motion } from "framer-motion";
import { useAppStore, STEP_ORDER } from "../../stores/appStore";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useInsertStore } from "../../stores/insertStore";
import { useSimStore } from "../../stores/simStore";
import { cn } from "../../lib/utils";
import {
  Upload, Scissors, Compass, Box, Layers, Droplets, Zap, Download,
  Check,
} from "lucide-react";

type LucideIcon = React.ComponentType<{ size?: number; className?: string }>;

const STEP_META: Record<string, { icon: LucideIcon; label: string; shortLabel: string; desc: string; num: number }> = {
  import:      { icon: Upload,   label: "导入模型", shortLabel: "导入", desc: "加载 3D 网格文件", num: 1 },
  repair:      { icon: Scissors, label: "编辑修复", shortLabel: "编辑", desc: "网格修复与模型分析", num: 2 },
  orientation: { icon: Compass,  label: "方向分析", shortLabel: "方向", desc: "脱模方向自动优化", num: 3 },
  mold:        { icon: Box,      label: "模具设计", shortLabel: "模具", desc: "壳体生成与分型面", num: 4 },
  insert:      { icon: Layers,   label: "内骨骼",   shortLabel: "骨骼", desc: "支撑板与晶格结构", num: 5 },
  gating:      { icon: Droplets, label: "浇注系统", shortLabel: "浇注", desc: "浇口与排气设计", num: 6 },
  simulation:  { icon: Zap,      label: "仿真分析", shortLabel: "仿真", desc: "充模仿真与 FEA", num: 7 },
  export:      { icon: Download, label: "导出",     shortLabel: "导出", desc: "STL / 3MF / BOM 导出", num: 8 },
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
      dataLabel = meshInfo ? `${(meshInfo.face_count / 1000).toFixed(0)}k` : undefined;
    }
    if (step === "repair" && modelId) {
      status = step === currentStep ? "active" : "done";
    }
    if (step === "orientation" && orientationResult) {
      status = step === currentStep ? "active" : "done";
      dataLabel = `${orientationResult.best_score?.min_draft_angle?.toFixed(0) ?? "?"}°`;
    }
    if (step === "mold" && moldId) {
      status = step === currentStep ? "active" : "done";
      dataLabel = moldResult ? `${moldResult.n_shells}壳` : undefined;
    }
    if (step === "insert" && insertId) {
      status = step === currentStep ? "active" : "done";
      dataLabel = plates.length > 0 ? `${plates.length}板` : undefined;
    }
    if (step === "gating" && gatingId) {
      status = step === currentStep ? "active" : "done";
    }
    if (step === "simulation" && simResult) {
      status = step === currentStep ? "active" : "done";
      dataLabel = simResult.fill_fraction != null ? `${(simResult.fill_fraction * 100).toFixed(0)}%` : undefined;
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
    <div className="w-full h-9 flex items-center px-2 bg-bg-secondary border-b border-border overflow-x-auto shrink-0 relative">
      {/* Progress background bar */}
      <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-border-subtle/30">
        <motion.div
          className="h-full bg-gradient-to-r from-accent/60 to-accent/30"
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
          const isDone = st === "done";

          return (
            <div key={step} className="flex items-center">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => setStep(step as typeof currentStep)}
                className={cn(
                  "relative flex items-center gap-1.5 px-2.5 h-7 rounded-md transition-all group",
                  isActive
                    ? "bg-accent/12 border border-accent/25"
                    : isDone
                      ? "hover:bg-success/8"
                      : "hover:bg-bg-hover/60",
                )}
              >
                {/* Step number / icon */}
                <div className={cn(
                  "w-[18px] h-[18px] rounded-[4px] flex items-center justify-center transition-all shrink-0 text-[10px] font-semibold",
                  isActive
                    ? "bg-accent text-white shadow-[0_0_8px_rgba(99,102,241,0.3)]"
                    : isDone
                      ? "bg-success/15 text-success"
                      : "bg-bg-hover text-text-muted/60",
                )}>
                  {isDone && !isActive ? (
                    <Check size={11} strokeWidth={2.5} />
                  ) : (
                    <Icon size={11} />
                  )}
                </div>

                {/* Label */}
                <div className="flex flex-col items-start leading-none">
                  <span className={cn(
                    "text-[11px] font-medium whitespace-nowrap",
                    isActive ? "text-accent" : isDone ? "text-success/70" : "text-text-muted/70",
                  )}>
                    {meta.shortLabel}
                  </span>
                  {dataLabel && isDone && !isActive && (
                    <span className="text-[8px] text-success/50 whitespace-nowrap mt-0.5">
                      {dataLabel}
                    </span>
                  )}
                </div>

                {/* Active pulse dot */}
                {isActive && (
                  <motion.div
                    className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-accent"
                    animate={{ scale: [1, 1.4, 1], opacity: [1, 0.4, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  />
                )}

                {/* Tooltip */}
                <div className="absolute top-full mt-1.5 left-1/2 -translate-x-1/2 hidden group-hover:block z-50 whitespace-nowrap pointer-events-none tooltip-anim">
                  <div className="bg-bg-primary/95 backdrop-blur border border-border rounded-md px-2.5 py-1.5 shadow-xl">
                    <div className="text-[11px] font-medium text-text-primary">{meta.label}</div>
                    <div className="text-[10px] text-text-muted">{meta.desc}</div>
                  </div>
                </div>
              </motion.button>

              {/* Connector */}
              {i < STEP_ORDER.length - 1 && (
                <div className="flex items-center px-0.5">
                  <div className={cn(
                    "w-4 h-[1.5px] rounded-full transition-colors",
                    isDone ? "bg-success/30" : "bg-border/30",
                  )} />
                </div>
              )}
            </div>
          );
        })}

        {/* Overall count */}
        <div className="ml-3 pl-3 border-l border-border/20 flex items-center gap-1.5">
          <span className={cn("text-[12px] font-bold tabular-nums",
            completedCount === STEP_ORDER.length ? "text-success" : "text-text-muted/60")}>
            {completedCount}/{STEP_ORDER.length}
          </span>
          <span className="text-[10px] text-text-muted/30">完成</span>
        </div>
      </div>
    </div>
  );
}
