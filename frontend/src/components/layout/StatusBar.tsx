import { useState } from "react";
import { Cpu, HardDrive, Triangle, Box, Layers, FlaskConical, Wifi, WifiOff, Bot, History } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useInsertStore } from "../../stores/insertStore";
import { useSimStore } from "../../stores/simStore";
import { useAIStore } from "../../stores/aiStore";
import { useHistoryStore } from "../../stores/historyStore";
import { STEP_ORDER } from "../../stores/appStore";
import { HistoryPanel } from "../ui/HistoryPanel";
import { cn } from "../../lib/utils";

export function StatusBar() {
  const gpu = useAppStore((s) => s.gpu);
  const backendStatus = useAppStore((s) => s.backendStatus);
  const currentStep = useAppStore((s) => s.currentStep);
  const completedSteps = useAppStore((s) => s.completedSteps);
  const { filename, meshInfo } = useModelStore();
  const moldResult = useMoldStore((s) => s.moldResult);
  const insertPlates = useInsertStore((s) => s.plates);
  const simResult = useSimStore((s) => s.simResult);
  const toggleAgentWorkstation = useAIStore((s) => s.toggleAgentWorkstation);
  const historyCount = useHistoryStore((s) => s.records.length);
  const [historyOpen, setHistoryOpen] = useState(false);

  const stepIdx = STEP_ORDER.indexOf(currentStep);

  return (
    <>
      <div className="flex items-center justify-between h-7 px-3 bg-bg-secondary border-t border-border text-[11px] text-text-muted shrink-0">
        {/* Left: system status */}
        <div className="flex items-center gap-3">
          <span className={cn("flex items-center gap-1", backendStatus === "online" ? "text-success" : backendStatus === "offline" ? "text-error" : "text-warning")}>
            {backendStatus === "online" ? <Wifi size={10} /> : <WifiOff size={10} />}
            {backendStatus === "online" ? "已连接" : backendStatus === "offline" ? "离线" : "检测中"}
          </span>

          {gpu?.available ? (
            <span className="flex items-center gap-1">
              <Cpu size={11} className="text-success" />
              {gpu.device_name}
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <Cpu size={11} className="text-warning" />
              CPU
            </span>
          )}

          {gpu?.available && (
            <span className="flex items-center gap-1">
              <HardDrive size={11} />
              {gpu.vram_used_mb}/{gpu.vram_total_mb} MB
            </span>
          )}

          <div className="flex items-center gap-0.5 ml-1">
            {STEP_ORDER.map((s, i) => (
              <div
                key={s}
                className={cn(
                  "w-1.5 h-1.5 rounded-full transition-colors",
                  i === stepIdx
                    ? "bg-accent"
                    : completedSteps.has(s)
                      ? "bg-success"
                      : "bg-border",
                )}
                title={s}
              />
            ))}
          </div>
        </div>

        {/* Right: data summary + action buttons */}
        <div className="flex items-center gap-3">
          {filename && meshInfo && (
            <>
              <span className="text-text-secondary">{filename}</span>
              <span className="flex items-center gap-1">
                <Triangle size={10} />
                {meshInfo.face_count.toLocaleString()}
              </span>
              {meshInfo.is_watertight && (
                <span className="text-success text-[10px]">水密</span>
              )}
            </>
          )}

          {moldResult && (
            <span className="flex items-center gap-1 text-accent">
              <Box size={10} />
              {moldResult.n_shells} 壳
            </span>
          )}

          {insertPlates.length > 0 && (
            <span className="flex items-center gap-1 text-accent">
              <Layers size={10} />
              {insertPlates.length} 板
            </span>
          )}

          {simResult && (
            <span className={cn("flex items-center gap-1", simResult.fill_fraction >= 0.99 ? "text-success" : "text-warning")}>
              <FlaskConical size={10} />
              {(simResult.fill_fraction * 100).toFixed(0)}%
            </span>
          )}

          <span className="text-text-muted/60">v0.1.0</span>

          {/* Divider */}
          <div className="w-px h-3.5 bg-border/40" />

          {/* History button */}
          <button
            onClick={() => setHistoryOpen((v) => !v)}
            className={cn(
              "flex items-center gap-1 px-1.5 h-5 rounded hover:bg-bg-hover transition-colors",
              historyOpen ? "text-accent bg-accent/10" : "text-text-muted",
            )}
            title="操作历史"
          >
            <History size={11} />
            {historyCount > 0 && (
              <span className="text-[9px] tabular-nums">{historyCount}</span>
            )}
          </button>

          {/* Agent button */}
          <button
            onClick={toggleAgentWorkstation}
            className="flex items-center gap-1 px-1.5 h-5 rounded bg-accent/10 hover:bg-accent/20 text-accent transition-colors"
            title="AI Agent 工作站"
          >
            <Bot size={11} />
            <span className="text-[10px] font-medium">Agent</span>
          </button>
        </div>
      </div>

      {/* History panel popup */}
      <HistoryPanel open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </>
  );
}
