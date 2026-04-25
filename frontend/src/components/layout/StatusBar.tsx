import { useState } from "react";
import {
  Cpu, HardDrive, Triangle, Box, Layers,
  Wifi, WifiOff, Bot, History, Gauge, Zap,
} from "lucide-react";
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
      <div className="flex items-center justify-between h-[26px] px-3 bg-bg-secondary border-t border-border text-[12px] text-text-muted shrink-0 select-none">
        {/* Left: system status */}
        <div className="flex items-center gap-3">
          {/* Connection */}
          <span className={cn(
            "flex items-center gap-1 font-medium",
            backendStatus === "online" ? "text-success" : backendStatus === "offline" ? "text-danger" : "text-warning",
          )}>
            {backendStatus === "online" ? <Wifi size={10} /> : <WifiOff size={10} />}
            {backendStatus === "online" ? "已连接" : backendStatus === "offline" ? "离线" : "检测中"}
          </span>

          <div className="w-px h-3 bg-border/30" />

          {/* GPU */}
          {gpu?.available ? (
            <span className="flex items-center gap-1">
              <Zap size={9} className="text-success" />
              <span className="text-text-secondary">{gpu.device_name}</span>
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <Cpu size={9} className="text-warning" />
              <span className="text-text-muted">CPU 模式</span>
            </span>
          )}

          {/* VRAM */}
          {gpu?.available && (
            <span className="flex items-center gap-1 text-text-muted/70">
              <HardDrive size={9} />
              <span className="tabular-nums">{gpu.vram_used_mb}/{gpu.vram_total_mb} MB</span>
            </span>
          )}

          <div className="w-px h-3 bg-border/30" />

          {/* Step dots */}
          <div className="flex items-center gap-[3px]">
            {STEP_ORDER.map((s, i) => (
              <div
                key={s}
                className={cn(
                  "w-[5px] h-[5px] rounded-full transition-all",
                  i === stepIdx
                    ? "bg-accent scale-125"
                    : completedSteps.has(s)
                      ? "bg-success/60"
                      : "bg-border/50",
                )}
                title={s}
              />
            ))}
          </div>
        </div>

        {/* Right: data summary + actions */}
        <div className="flex items-center gap-2.5">
          {/* Model info */}
          {filename && meshInfo && (
            <div className="flex items-center gap-2">
              <span className="text-text-secondary font-medium">{filename}</span>
              <span className="flex items-center gap-0.5 text-text-muted/70">
                <Triangle size={9} />
                <span className="tabular-nums">{meshInfo.face_count.toLocaleString()}</span>
              </span>
              {meshInfo.is_watertight && (
                <span className="text-success/60 text-[11px] font-medium">水密</span>
              )}
            </div>
          )}

          {/* Mold */}
          {moldResult && (
            <span className="flex items-center gap-0.5 text-obj-mold/70">
              <Box size={9} />
              <span className="tabular-nums">{moldResult.n_shells}壳</span>
            </span>
          )}

          {/* Insert */}
          {insertPlates.length > 0 && (
            <span className="flex items-center gap-0.5 text-obj-insert/70">
              <Layers size={9} />
              <span className="tabular-nums">{insertPlates.length}板</span>
            </span>
          )}

          {/* Sim */}
          {simResult && (
            <span className={cn(
              "flex items-center gap-0.5",
              simResult.fill_fraction >= 0.99 ? "text-success/70" : "text-warning/70",
            )}>
              <Gauge size={9} />
              <span className="tabular-nums">{(simResult.fill_fraction * 100).toFixed(0)}%</span>
            </span>
          )}

          <div className="w-px h-3 bg-border/30" />

          <span className="text-text-muted/30 tabular-nums">v0.1.0</span>

          {/* History */}
          <button
            onClick={() => setHistoryOpen((v) => !v)}
            className={cn(
              "flex items-center gap-1 px-1.5 h-[18px] rounded transition-colors",
              historyOpen ? "text-accent bg-accent/10" : "text-text-muted/50 hover:text-text-muted hover:bg-bg-hover/40",
            )}
            title="操作历史"
          >
            <History size={10} />
            {historyCount > 0 && (
              <span className="text-[11px] tabular-nums">{historyCount}</span>
            )}
          </button>

          {/* Agent */}
          <button
            onClick={toggleAgentWorkstation}
            className="flex items-center gap-1 px-1.5 h-[18px] rounded bg-accent/8 hover:bg-accent/15 text-accent/70 hover:text-accent transition-colors"
            title="AI Agent 工作站"
          >
            <Bot size={10} />
            <span className="text-[11px] font-medium">Agent</span>
          </button>
        </div>
      </div>

      <HistoryPanel open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </>
  );
}
