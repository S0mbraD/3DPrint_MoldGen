import { motion } from "framer-motion";
import {
  Upload,
  Wrench,
  Compass,
  Box,
  Layers,
  Droplets,
  FlaskConical,
  Download,
  Settings,
  Lock,
  Check,
} from "lucide-react";
import type { WorkflowStep } from "../../stores/appStore";
import { useAppStore } from "../../stores/appStore";
import { cn } from "../../lib/utils";
import { toastInfo } from "../../stores/toastStore";

const STEPS: { key: WorkflowStep; label: string; icon: typeof Upload }[] = [
  { key: "import", label: "导入", icon: Upload },
  { key: "repair", label: "编辑", icon: Wrench },
  { key: "orientation", label: "方向", icon: Compass },
  { key: "mold", label: "模具", icon: Box },
  { key: "insert", label: "支撑板", icon: Layers },
  { key: "gating", label: "浇注", icon: Droplets },
  { key: "simulation", label: "仿真", icon: FlaskConical },
  { key: "export", label: "导出", icon: Download },
];

export function Toolbar() {
  const { currentStep, setStep, toggleSettings, canNavigateTo, completedSteps } = useAppStore();

  const handleStepClick = (key: WorkflowStep) => {
    if (canNavigateTo(key)) {
      setStep(key);
    } else {
      toastInfo("请先导入模型", "需要加载3D模型后才能进入此步骤");
    }
  };

  return (
    <div className="flex items-center gap-1 px-4 h-11 bg-bg-secondary border-b border-border">
      {STEPS.map((step, i) => {
        const Icon = step.icon;
        const active = currentStep === step.key;
        const stepIndex = STEPS.findIndex((s) => s.key === currentStep);
        const completed = completedSteps.has(step.key);
        const locked = !canNavigateTo(step.key);

        return (
          <div key={step.key} className="flex items-center">
            {i > 0 && (
              <div
                className={cn(
                  "w-6 h-px mx-1",
                  completed ? "bg-accent" : i < stepIndex ? "bg-accent/40" : "bg-border",
                )}
              />
            )}
            <motion.button
              whileHover={locked ? {} : { scale: 1.05 }}
              whileTap={locked ? {} : { scale: 0.95 }}
              onClick={() => handleStepClick(step.key)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors relative",
                locked
                  ? "text-text-muted/40 cursor-not-allowed"
                  : active
                    ? "bg-accent/20 text-accent"
                    : completed
                      ? "bg-success/10 text-success"
                      : "text-text-secondary hover:bg-bg-hover hover:text-text-primary",
              )}
            >
              {completed && !active ? (
                <Check size={12} className="text-success" />
              ) : locked ? (
                <Lock size={12} />
              ) : (
                <Icon size={14} />
              )}
              {step.label}
            </motion.button>
          </div>
        );
      })}

      <div className="flex-1" />
      <motion.button
        whileHover={{ scale: 1.1, rotate: 45 }}
        whileTap={{ scale: 0.9 }}
        onClick={toggleSettings}
        className="p-1.5 rounded-md text-text-muted hover:bg-bg-hover hover:text-text-primary transition-colors"
        title="设置 (Ctrl+,)"
      >
        <Settings size={15} />
      </motion.button>
    </div>
  );
}
