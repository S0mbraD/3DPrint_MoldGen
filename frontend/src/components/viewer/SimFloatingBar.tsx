import { motion, AnimatePresence } from "framer-motion";
import { useSimStore, type HeatmapField, type SimColorPalette } from "../../stores/simStore";
import { useAppStore } from "../../stores/appStore";
import { cn } from "../../lib/utils";
import {
  Play, Pause, RotateCcw, Eye, EyeOff, Timer, Gauge,
  Activity, Zap, ThermometerSun, Layers, Slice, Wind,
  Palette, GaugeCircle, SlidersHorizontal, ListTree, Cpu,
  Sparkles,
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

const PALETTE_OPTIONS: { value: SimColorPalette; label: string }[] = [
  { value: "jet", label: "Jet" },
  { value: "coolwarm", label: "冷暖" },
  { value: "viridis", label: "Viridis" },
  { value: "turbo", label: "Turbo" },
  { value: "rainbow", label: "彩虹" },
];

const FEA_FIELDS = [
  { v: "von_mises" as const, label: "应力" },
  { v: "displacement" as const, label: "位移" },
  { v: "safety_factor" as const, label: "安全" },
  { v: "strain_energy" as const, label: "应变" },
];

function SectionDivider() {
  return <div className="w-px h-6 bg-border/50 shrink-0" />;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9px] uppercase tracking-wider text-text-muted/70 font-semibold px-0.5 shrink-0">
      {children}
    </span>
  );
}

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
  const colorPalette = useSimStore((s) => s.colorPalette);
  const setColorPalette = useSimStore((s) => s.setColorPalette);
  const showVelocityArrows = useSimStore((s) => s.showVelocityArrows);
  const setShowVelocityArrows = useSimStore((s) => s.setShowVelocityArrows);
  const showColorLegend = useSimStore((s) => s.showColorLegend);
  const setShowColorLegend = useSimStore((s) => s.setShowColorLegend);
  const showFlowParticles = useSimStore((s) => s.showFlowParticles);
  const setShowFlowParticles = useSimStore((s) => s.setShowFlowParticles);
  const showFlowFront = useSimStore((s) => s.showFlowFront);
  const setShowFlowFront = useSimStore((s) => s.setShowFlowFront);
  const showAnimatedStreamlines = useSimStore((s) => s.showAnimatedStreamlines);
  const setShowAnimatedStreamlines = useSimStore((s) => s.setShowAnimatedStreamlines);
  const flowParticleSpeed = useSimStore((s) => s.flowParticleSpeed);
  const setFlowParticleSpeed = useSimStore((s) => s.setFlowParticleSpeed);
  const feaVisible = useSimStore((s) => s.feaVisible);
  const setFEAVisible = useSimStore((s) => s.setFEAVisible);
  const feaField = useSimStore((s) => s.feaField);
  const setFEAField = useSimStore((s) => s.setFEAField);

  const hasVelocityVectors = !!visData?.velocity_vectors?.length;

  const showFlowBar = step === "simulation" && !!visData;
  const showFEABar = step === "simulation" && !!feaVisData;

  if (!showFlowBar && !showFEABar) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 20, opacity: 0 }}
        className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30 flex flex-col gap-2 items-center max-w-[98vw]"
      >
        {showFlowBar && (
          <div
            className={cn(
              "flex flex-wrap items-center gap-x-1 gap-y-1.5 px-2.5 py-2 rounded-2xl",
              "bg-bg-primary/92 backdrop-blur-md border border-border/55 shadow-2xl",
            )}
          >
            <div className="flex items-center gap-1 pr-1 border-r border-border/40">
              <SlidersHorizontal size={12} className="text-accent/90 shrink-0" />
              <SectionLabel>流动仿真</SectionLabel>
            </div>

            {/* Display toggles */}
            <div className="flex items-center gap-0.5 flex-wrap">
              <SectionLabel>显示</SectionLabel>
              <BarBtn active={heatmapVisible} onClick={() => setHeatmapVisible(!heatmapVisible)}
                tip="体素热力图">
                {heatmapVisible ? <Eye size={12} /> : <EyeOff size={12} />}
              </BarBtn>
              <BarBtn active={streamlinesVisible} onClick={() => setStreamlinesVisible(!streamlinesVisible)}
                tip="流线">
                <Activity size={11} />
              </BarBtn>
              {surfaceMapData && (
                <BarBtn active={surfaceMapVisible} onClick={() => setSurfaceMapVisible(!surfaceMapVisible)}
                  tip="表面场叠加">
                  <Layers size={11} />
                </BarBtn>
              )}
              <BarBtn
                active={showVelocityArrows}
                onClick={() => setShowVelocityArrows(!showVelocityArrows)}
                tip={hasVelocityVectors ? "速度矢量箭头" : "无可用的速度矢量数据"}
                disabled={!hasVelocityVectors}
              >
                <Wind size={11} />
              </BarBtn>
              <BarBtn active={showColorLegend} onClick={() => setShowColorLegend(!showColorLegend)}
                tip="色谱条图例">
                <ListTree size={11} />
              </BarBtn>
            </div>

            <SectionDivider />

            {/* Scalar field */}
            <div className="flex items-center gap-0.5 flex-wrap max-w-[52vw]">
              <SectionLabel>场</SectionLabel>
              {FIELD_OPTIONS.map((opt) => (
                <BarBtn key={opt.value}
                  active={heatmapField === opt.value}
                  onClick={() => setHeatmapField(opt.value)}
                  tip={opt.label}>
                  {opt.icon}
                  <span className="text-[11px]">{opt.label}</span>
                </BarBtn>
              ))}
            </div>

            <SectionDivider />

            {/* Palette & sampling */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <Palette size={11} className="text-text-muted shrink-0" />
              <select
                value={colorPalette}
                onChange={(e) => setColorPalette(e.target.value as SimColorPalette)}
                title="色彩映射"
                className={cn(
                  "text-[11px] rounded-lg bg-bg-secondary border border-border/60",
                  "text-text-primary px-1.5 py-1 max-w-[5.5rem]",
                  "focus:outline-none focus:ring-1 focus:ring-accent/40",
                )}
              >
                {PALETTE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>

              <div className="flex items-center gap-0.5">
                <span className="text-[10px] text-text-muted whitespace-nowrap">密度</span>
                {[1, 2, 3].map((d) => (
                  <BarBtn key={d} active={particleDensity === d} onClick={() => setParticleDensity(d)}
                    tip={`${d}× 粒子密度`}>
                    <span className="text-[11px] font-bold">{d}×</span>
                  </BarBtn>
                ))}
              </div>

              <div className="flex items-center gap-1" title="粒子大小">
                <GaugeCircle size={11} className="text-text-muted shrink-0" />
                <input
                  type="range"
                  min={1}
                  max={8}
                  step={0.5}
                  value={pointSize}
                  onChange={(e) => setPointSize(parseFloat(e.target.value))}
                  className="w-14 h-3 accent-accent"
                />
              </div>
            </div>

            <SectionDivider />

            <div className="flex items-center gap-0.5 flex-wrap">
              <Sparkles size={11} className="text-accent/80 shrink-0" />
              <SectionLabel>动态效果</SectionLabel>
              <BarBtn
                active={showFlowParticles}
                onClick={() => setShowFlowParticles(!showFlowParticles)}
                tip="流动粒子"
              >
                <span className="text-[11px]">粒子</span>
              </BarBtn>
              <BarBtn
                active={showFlowFront}
                onClick={() => setShowFlowFront(!showFlowFront)}
                tip="充填前沿"
              >
                <span className="text-[11px]">前沿</span>
              </BarBtn>
              <BarBtn
                active={showAnimatedStreamlines}
                onClick={() => setShowAnimatedStreamlines(!showAnimatedStreamlines)}
                tip="动态流线"
              >
                <span className="text-[11px]">流线</span>
              </BarBtn>
              <div className="flex items-center gap-1 px-1 rounded-lg bg-bg-secondary/80 border border-border/40">
                <span className="text-[10px] text-text-muted whitespace-nowrap">粒子速度</span>
                <input
                  type="range"
                  min={0.5}
                  max={3}
                  step={0.05}
                  value={flowParticleSpeed}
                  onChange={(e) => setFlowParticleSpeed(parseFloat(e.target.value))}
                  className="w-16 h-3 accent-accent"
                  title="粒子流动速度"
                />
                <span className="text-[11px] text-accent font-medium tabular-nums w-8 text-right">
                  {flowParticleSpeed.toFixed(1)}×
                </span>
              </div>
            </div>

            <SectionDivider />

            {/* Animation */}
            <div className="flex items-center gap-1 flex-wrap">
              <BarBtn active={false} onClick={() => { setAnimProgress(0); setAnimPlaying(true); }} tip="重播">
                <RotateCcw size={11} />
              </BarBtn>
              <BarBtn active={animPlaying} onClick={() => setAnimPlaying(!animPlaying)} tip="播放 / 暂停">
                {animPlaying ? <Pause size={11} /> : <Play size={11} />}
              </BarBtn>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={animProgress}
                onChange={(e) => {
                  setAnimProgress(parseFloat(e.target.value));
                  setAnimPlaying(false);
                }}
                className="w-20 h-3 accent-accent"
                title="充填进度"
              />
              <span className="text-[11px] text-text-muted w-9 tabular-nums">
                {(animProgress * 100).toFixed(0)}%
              </span>

              <div className="flex items-center gap-1.5 px-1 rounded-lg bg-bg-secondary/80 border border-border/40">
                <span className="text-[10px] text-text-muted whitespace-nowrap">速度</span>
                <input
                  type="range"
                  min={0.5}
                  max={3}
                  step={0.05}
                  value={animSpeed}
                  onChange={(e) => setAnimSpeed(parseFloat(e.target.value))}
                  className="w-20 h-3 accent-accent"
                  title="动画播放速度"
                />
                <span className="text-[11px] text-accent font-medium tabular-nums w-9 text-right">
                  {animSpeed.toFixed(1)}×
                </span>
              </div>
            </div>
          </div>
        )}

        {showFEABar && (
          <div className="flex items-center gap-1 px-2.5 py-2 rounded-2xl bg-bg-primary/92 backdrop-blur-md border border-border/55 shadow-2xl">
            <Cpu size={12} className="text-accent shrink-0" />
            <SectionLabel>FEA</SectionLabel>
            <SectionDivider />
            <BarBtn active={feaVisible} onClick={() => setFEAVisible(!feaVisible)} tip="FEA 云图">
              {feaVisible ? <Eye size={12} /> : <EyeOff size={12} />}
            </BarBtn>
            {FEA_FIELDS.map((opt) => (
              <BarBtn key={opt.v} active={feaField === opt.v} onClick={() => setFEAField(opt.v)} tip={opt.label}>
                <span className="text-[11px]">{opt.label}</span>
              </BarBtn>
            ))}
            <SectionDivider />
            <div className="flex items-center gap-0.5">
              <div className="w-16 h-2 rounded-full border border-border/40" style={{
                background: "linear-gradient(to right, #0066ff, #00ccaa, #00ff33, #ffcc00, #ff4400)",
              }} />
              <span className="text-[11px] text-text-muted">低→高</span>
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

function BarBtn({
  active, onClick, tip, children, disabled,
}: {
  active: boolean;
  onClick: () => void;
  tip: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={tip}
      className={cn(
        "flex items-center gap-0.5 px-1.5 py-1 rounded-lg text-[12px] transition-all",
        disabled && "opacity-35 cursor-not-allowed",
        !disabled && active
          ? "bg-accent/25 text-accent ring-1 ring-accent/30"
          : !disabled && "text-text-muted hover:bg-bg-hover hover:text-text-primary",
      )}
    >
      {children}
    </button>
  );
}
