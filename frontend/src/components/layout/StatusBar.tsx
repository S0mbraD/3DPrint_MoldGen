import { Cpu, HardDrive, Triangle, Box, Layers, FlaskConical } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useInsertStore } from "../../stores/insertStore";
import { useSimStore } from "../../stores/simStore";

export function StatusBar() {
  const gpu = useAppStore((s) => s.gpu);
  const { filename, meshInfo } = useModelStore();
  const moldResult = useMoldStore((s) => s.moldResult);
  const insertPlates = useInsertStore((s) => s.plates);
  const simResult = useSimStore((s) => s.simResult);

  return (
    <div className="flex items-center justify-between h-7 px-3 bg-bg-secondary border-t border-border text-[11px] text-text-muted">
      <div className="flex items-center gap-4">
        {gpu?.available ? (
          <span className="flex items-center gap-1">
            <Cpu size={11} className="text-success" />
            {gpu.device_name}
          </span>
        ) : (
          <span className="flex items-center gap-1">
            <Cpu size={11} className="text-warning" />
            CPU Mode
          </span>
        )}

        {gpu?.available && (
          <span className="flex items-center gap-1">
            <HardDrive size={11} />
            VRAM: {gpu.vram_used_mb}/{gpu.vram_total_mb} MB
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        {filename && meshInfo && (
          <>
            <span className="text-text-secondary">{filename}</span>
            <span className="flex items-center gap-1">
              <Triangle size={10} />
              {meshInfo.face_count.toLocaleString()}
            </span>
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
          <span className={`flex items-center gap-1 ${simResult.fill_fraction >= 0.99 ? "text-success" : "text-warning"}`}>
            <FlaskConical size={10} />
            {(simResult.fill_fraction * 100).toFixed(0)}%
          </span>
        )}

        <span className="text-text-muted/60">v0.1.0</span>
      </div>
    </div>
  );
}
