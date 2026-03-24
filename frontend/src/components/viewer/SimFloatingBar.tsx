import { motion, AnimatePresence } from "framer-motion";
import { useSimStore, type HeatmapField } from "../../stores/simStore";
import { useAppStore } from "../../stores/appStore";
import { cn } from "../../lib/utils";
import {
  Play, Pause, RotateCcw, Eye, EyeOff, Timer, Gauge,
  Activity, Zap, ThermometerSun, Layers, Slice,
} from "lucide-react";

const FIELD_OPTIONS: { value: HeatmapField; label: string; icon: React.ReactNode }[] = [
  { value: "fill_time", label: "充填", icon: <Timer size={10} /> },
  { value: "pressure", label: "压力", icon: <Gauge size={10} /> },
  { value: "velocity", label: "流速", icon: <Activity size={10} /> },
  { value: "shear_rate", label: "剪切", icon: <Zap size={10} /> },
  { value: "temperature", label: "温度", icon: <ThermometerSun size={10} /> },
  { value: "cure_progress", label: "固化", icon: <Layers size={10} /> },
  { value: "thickness", label: "壁厚", icon: <Slice size={10} /> },
];

const FEA_FIELDS = [
  { v: "von_mises" as const, label: "应力" },
  { v: "displacement" as const, label: "位移" },
  { v: "safety_factor" as const, label: "安全" },
  { v: "strain_energy" as const, label: "应变" },
];

export function SimFloatingBar() {
  const step = useAppStore((s) => s.currentStep);
  const visData = useSimStore((s) => s.visualizationData);
  const feaVisData = useSimStore((s) => s.feaVisualizationData);
  const heatmapField = useSimStore((s) => s.heatmapField);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const setHeatmapField = useSimStore((s) => s.setHeatmapField);
  const setHeatmapVisible = useSimStore((s) => s.setHeatmapVisible);
  const streamlinesVisible = useSimStore((s) => s.streamlinesVisible);
  const setStreamlinesVisible = useSimStore((s) => s.setStreamlinesVisible);
  const surfaceMapVisible = useSimStore((s) => s.surfaceMapVisible);
  const setSurfaceMapVisible = useSimStore((s) => s.setSurfaceMapVisible);
  const surfaceMapData = useSimStore((s) => s.surfaceMapData);
  const particleDensity = useSimStore((s) => s.particleDensity);
  const setParticleDensity = useSimStore((s) => s.setParticleDensity);
  const pointSize = useSimStore((s) => s.pointSize);
  const setPointSize = useSimStore((s) => s.setPointSize);
  const animPlaying = useSimStore((s) => s.animationPlaying);
  const animProgress = useSimStore((s) => s.animationProgress);
  const setAnimPlaying = useSimStore((s) => s.setAnimationPlaying);
  const setAnimProgress = useSimStore((s) => s.setAnimationProgress);
  const animSpeed = useSimStore((s) => s.animationSpeed);
  const setAnimSpeed = useSimStore((s) => s.setAnimationSpeed);
  const feaVisible = useSimStore((s) => s.feaVisible);
  const setFEAVisible = useSimStore((s) => s.setFEAVisible);
  const feaField = useSimStore((s) => s.feaField);
  const setFEAField = useSimStore((s) => s.setFEAField);

  const showFlowBar = step === "simulation" && !!visData;
  const showFEABar = step === "simulation" && !!feaVisData;

  if (!showFlowBar && !showFEABar) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 20, opacity: 0 }}
        className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30 flex flex-col gap-1.5 items-center"
      >
        {/* Flow Simulation Controls */}
        {showFlowBar && (
          <div className="flex items-center gap-1 px-2 py-1.5 rounded-xl bg-bg-primary/90 backdrop-blur-md border border-border/50 shadow-xl">
            {/* Heatmap toggle */}
            <BarBtn active={heatmapVisible} onClick={() => setHeatmapVisible(!heatmapVisible)}
              tip="热力图">
              {heatmapVisible ? <Eye size={12} /> : <EyeOff size={12} />}
            </BarBtn>

            <div className="w-px h-5 bg-border/50 mx-0.5" />

            {/* Field selector */}
            {FIELD_OPTIONS.map((opt) => (
              <BarBtn key={opt.value}
                active={heatmapField === opt.value}
                onClick={() => setHeatmapField(opt.value)}
                tip={opt.label}>
                {opt.icon}
                <span className="text-[8px]">{opt.label}</span>
              </BarBtn>
            ))}

            <div className="w-px h-5 bg-border/50 mx-0.5" />

            {/* Streamlines */}
            <BarBtn active={streamlinesVisible} onClick={() => setStreamlinesVisible(!streamlinesVisible)}
              tip="流线">
              <Activity size={11} />
              <span className="text-[8px]">流线</span>
            </BarBtn>

            {/* Surface overlay */}
            {surfaceMapData && (
              <BarBtn active={surfaceMapVisible} onClick={() => setSurfaceMapVisible(!surfaceMapVisible)}
                tip="表面叠加">
                <Layers size={11} />
                <span className="text-[8px]">表面</span>
              </BarBtn>
            )}

            <div className="w-px h-5 bg-border/50 mx-0.5" />

            {/* Density */}
            {[1, 2, 3].map((d) => (
              <BarBtn key={d} active={particleDensity === d} onClick={() => setParticleDensity(d)}
                tip={`${d}x 密度`}>
                <span className="text-[9px] font-bold">{d}×</span>
              </BarBtn>
            ))}

            {/* Point size */}
            <input type="range" min={1} max={8} step={0.5} value={pointSize}
              onChange={(e) => setPointSize(parseFloat(e.target.value))}
              className="w-12 h-3 accent-accent" title="点大小" />

            <div className="w-px h-5 bg-border/50 mx-0.5" />

            {/* Animation */}
            <BarBtn active={false} onClick={() => { setAnimProgress(0); setAnimPlaying(true); }} tip="重播">
              <RotateCcw size={11} />
            </BarBtn>
            <BarBtn active={animPlaying} onClick={() => setAnimPlaying(!animPlaying)} tip="播放/暂停">
              {animPlaying ? <Pause size={11} /> : <Play size={11} />}
            </BarBtn>
            <input type="range" min={0} max={1} step={0.01} value={animProgress}
              onChange={(e) => { setAnimProgress(parseFloat(e.target.value)); setAnimPlaying(false); }}
              className="w-16 h-3 accent-accent" />
            <span className="text-[9px] text-text-muted w-8 tabular-nums">
              {(animProgress * 100).toFixed(0)}%
            </span>
            {[0.5, 1, 2].map((s) => (
              <BarBtn key={s} active={animSpeed === s} onClick={() => setAnimSpeed(s)}
                tip={`${s}x 速度`}>
                <span className="text-[8px]">{s}×</span>
              </BarBtn>
            ))}
          </div>
        )}

        {/* FEA Controls */}
        {showFEABar && (
          <div className="flex items-center gap-1 px-2 py-1.5 rounded-xl bg-bg-primary/90 backdrop-blur-md border border-border/50 shadow-xl">
            <BarBtn active={feaVisible} onClick={() => setFEAVisible(!feaVisible)} tip="FEA 可视化">
              {feaVisible ? <Eye size={12} /> : <EyeOff size={12} />}
            </BarBtn>
            <div className="w-px h-5 bg-border/50 mx-0.5" />
            {FEA_FIELDS.map((opt) => (
              <BarBtn key={opt.v} active={feaField === opt.v} onClick={() => setFEAField(opt.v)} tip={opt.label}>
                <span className="text-[9px]">{opt.label}</span>
              </BarBtn>
            ))}
            <div className="w-px h-5 bg-border/50 mx-0.5" />
            <div className="flex items-center gap-0.5">
              <div className="w-16 h-2 rounded-full" style={{
                background: "linear-gradient(to right, #0066ff, #00ccaa, #00ff33, #ffcc00, #ff4400)",
              }} />
              <span className="text-[8px] text-text-muted">低→高</span>
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

function BarBtn({ active, onClick, tip, children }: {
  active: boolean; onClick: () => void; tip: string; children: React.ReactNode;
}) {
  return (
    <button onClick={onClick} title={tip}
      className={cn(
        "flex items-center gap-0.5 px-1.5 py-1 rounded-lg text-[10px] transition-all",
        active
          ? "bg-accent/25 text-accent ring-1 ring-accent/30"
          : "text-text-muted hover:bg-bg-hover hover:text-text-primary",
      )}>
      {children}
    </button>
  );
}
