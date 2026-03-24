import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, ChevronDown, Info, Layers, Droplets, Triangle, CheckCircle, AlertTriangle, Compass, Boxes, Pin, FlaskConical, Clock, Hash, Ruler, Eye, EyeOff, Box, ThermometerSun } from "lucide-react";
import { useAppStore, type WorkflowStep } from "../../stores/appStore";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useInsertStore } from "../../stores/insertStore";
import { useSimStore } from "../../stores/simStore";
import { useViewportStore } from "../../stores/viewportStore";
import { cn } from "../../lib/utils";

const STEP_TITLES: Record<WorkflowStep, string> = {
  import: "导入信息",
  repair: "编辑信息",
  orientation: "方向分析",
  mold: "模具信息",
  insert: "支撑板信息",
  gating: "浇注系统",
  simulation: "仿真结果",
  export: "导出信息",
};

/* ── Reusable primitives (defined first) ────────────────────────────── */

function InfoSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">
        {icon}
        {title}
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function Row({
  label,
  value,
  valueClass,
  icon,
}: {
  label: string;
  value: string;
  valueClass?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex justify-between items-center py-1 px-2 rounded bg-bg-secondary text-xs">
      <span className="text-text-muted">{label}</span>
      <span className={cn("flex items-center gap-1", valueClass || "text-text-primary")}>
        {icon}
        {value}
      </span>
    </div>
  );
}

/* ── Section components (defined before RightPanel uses them) ──────── */

function MoldInfoSection() {
  const { orientationResult, moldResult } = useMoldStore();

  if (!orientationResult && !moldResult) return null;

  return (
    <>
      {orientationResult && (
        <InfoSection title="方向分析" icon={<Compass size={12} />}>
          <Row
            label="最佳方向"
            value={orientationResult.best_direction.map((v) => v.toFixed(2)).join(", ")}
          />
          <Row
            label="评分"
            value={`${(orientationResult.best_score.total_score * 100).toFixed(1)}%`}
            valueClass="text-accent"
          />
          <Row
            label="最小拔模角"
            value={`${orientationResult.best_score.min_draft_angle.toFixed(1)}°`}
          />
          <Row
            label="候选数"
            value={String(orientationResult.top_candidates.length)}
          />
        </InfoSection>
      )}
      {moldResult && (
        <>
          <InfoSection title="模具壳体" icon={<Boxes size={12} />}>
            <Row label="壳体数" value={String(moldResult.n_shells)} valueClass="text-accent" />
            <Row label="型腔体积" value={`${moldResult.cavity_volume.toFixed(1)} mm³`} />
            {moldResult.shells.map((sh) => (
              <Row
                key={sh.shell_id}
                label={`壳#${sh.shell_id}`}
                value={`${sh.face_count.toLocaleString()} 面 | ${sh.is_printable ? "可打印" : `拔模${sh.min_draft_angle?.toFixed(1) ?? "0"}°`}`}
                valueClass={sh.is_printable ? "text-success" : "text-warning"}
              />
            ))}
          </InfoSection>
          {/* v3 pour/vent info */}
          <InfoSection title="浇注/排气" icon={<Droplets size={12} />}>
            {moldResult.pour_hole && typeof moldResult.pour_hole === "object" && !Array.isArray(moldResult.pour_hole) ? (
              <Row
                label="浇口评分"
                value={`${(((moldResult.pour_hole as { score?: number }).score ?? 0) * 100).toFixed(1)}%`}
                valueClass="text-accent"
              />
            ) : moldResult.pour_hole ? (
              <Row label="浇口" value="已放置" />
            ) : null}
            <Row label="排气口" value={`${moldResult.vent_holes.length} 个`} />
            {moldResult.alignment_features && (
              <Row
                label="定位销"
                value={`${moldResult.alignment_features.filter(f => f.type === "pin").length} 对`}
              />
            )}
          </InfoSection>
        </>
      )}
    </>
  );
}

function PartingInfoSection() {
  const { partingResult } = useMoldStore();
  if (!partingResult) return null;

  return (
    <InfoSection title="分型面" icon={<Hash size={12} />}>
      <Row label="分型线" value={`${partingResult.parting_lines.length} 条`} />
      <Row label="上模面" value={partingResult.n_upper_faces.toLocaleString()} />
      <Row label="下模面" value={partingResult.n_lower_faces.toLocaleString()} />
      {partingResult.parting_lines.map((pl, i) => (
        <Row key={i} label={`线#${i + 1}`}
          value={`${pl.vertex_count} 顶点 | ${pl.is_closed ? "闭合" : "开放"}`}
          valueClass={pl.is_closed ? "text-success" : "text-warning"} />
      ))}
    </InfoSection>
  );
}

function InsertInfoSection() {
  const { insertId, plates, assemblyValid } = useInsertStore();

  if (!insertId || plates.length === 0) return null;

  return (
    <InfoSection title="支撑板" icon={<Pin size={12} />}>
      <Row label="板数" value={String(plates.length)} valueClass="text-accent" />
      <Row
        label="装配"
        value={assemblyValid ? "通过" : "待验证"}
        valueClass={assemblyValid ? "text-success" : "text-text-muted"}
        icon={assemblyValid ? <CheckCircle size={10} className="text-success" /> : undefined}
      />
      {plates.map((p, i) => (
        <Row
          key={i}
          label={`板#${i + 1}`}
          value={`${p.face_count.toLocaleString()} 面 | ${p.anchor?.type ?? "无锚固"}`}
        />
      ))}
    </InfoSection>
  );
}

function GatingInfoSection() {
  const { gatingResult } = useSimStore();
  if (!gatingResult) return null;

  return (
    <InfoSection title="浇注系统" icon={<Droplets size={12} />}>
      <Row label="浇口评分" value={`${(gatingResult.gate.score * 100).toFixed(0)}%`} valueClass="text-accent" />
      <Row label="浇口直径" value={`${gatingResult.gate_diameter.toFixed(1)}mm`} />
      <Row label="浇道宽度" value={`${gatingResult.runner_width.toFixed(1)}mm`} />
      <Row label="排气孔" value={`${gatingResult.vents.length} 个`} />
      <Row label="型腔体积" value={`${gatingResult.cavity_volume.toFixed(0)} mm³`} />
      <Row label="预计充填" value={`${gatingResult.estimated_fill_time.toFixed(1)} s`} />
    </InfoSection>
  );
}

function SimInfoSection() {
  const { simResult, optimizationResult, visualizationData } = useSimStore();

  if (!simResult) return null;

  const analysis = simResult.analysis;

  return (
    <>
      <InfoSection title="仿真结果" icon={<FlaskConical size={12} />}>
        <Row
          label="充填率"
          value={`${(simResult.fill_fraction * 100).toFixed(1)}%`}
          valueClass={simResult.fill_fraction >= 0.99 ? "text-success" : "text-warning"}
        />
        <Row label="充填时间" value={`${simResult.fill_time_seconds.toFixed(1)} s`} />
        <Row label="最大压力" value={`${simResult.max_pressure.toFixed(0)} Pa`} />
        <Row label="缺陷数" value={`${simResult.defects.length}`}
          valueClass={simResult.defects.length === 0 ? "text-success" : "text-warning"} />
        {simResult.defects.length > 0 && simResult.defects.map((d, i) => (
          <Row key={i} label={d.type} value={`严重度 ${(d.severity * 100).toFixed(0)}%`}
            valueClass="text-warning" />
        ))}
      </InfoSection>

      {analysis && (
        <InfoSection title="质量分析" icon={<Clock size={12} />}>
          <Row
            label="质量评分"
            value={`${(analysis.fill_quality_score * 100).toFixed(1)}%`}
            valueClass={analysis.fill_quality_score >= 0.8 ? "text-success" : analysis.fill_quality_score >= 0.5 ? "text-accent" : "text-warning"}
          />
          <Row label="充填均匀" value={`${(analysis.fill_uniformity_index * 100).toFixed(0)}%`} />
          <Row label="压力均匀" value={`${(analysis.pressure_uniformity_index * 100).toFixed(0)}%`} />
          <Row label="充填平衡" value={`${(analysis.fill_balance_score * 100).toFixed(0)}%`} />
          <Row label="流长比" value={analysis.flow_length_ratio.toFixed(1)} />
          <Row label="浇口效率" value={`${(analysis.gate_efficiency * 100).toFixed(0)}%`} />
          <Row label="壁厚" value={`${analysis.min_thickness.toFixed(1)}~${analysis.max_thickness.toFixed(1)} mm`} />
          <Row label="滞流区" value={String(analysis.n_stagnation_zones)}
            valueClass={analysis.n_stagnation_zones > 3 ? "text-warning" : "text-success"} />
          {analysis.avg_temperature > 0 && (
            <Row label="平均温度" value={`${analysis.avg_temperature.toFixed(1)} °C`} />
          )}
          {analysis.avg_cure_progress > 0 && (
            <Row label="固化进度" value={`${(analysis.avg_cure_progress * 100).toFixed(1)}%`} />
          )}
        </InfoSection>
      )}

      {visualizationData && (
        <InfoSection title="可视化" icon={<Layers size={12} />}>
          <Row label="体素数" value={visualizationData.n_points.toLocaleString()} />
          <Row label="体素尺寸" value={`${visualizationData.voxel_pitch.toFixed(2)} mm`} />
          <Row label="缺陷标记" value={String(visualizationData.defect_positions.length)}
            valueClass={visualizationData.defect_positions.length > 0 ? "text-warning" : "text-success"} />
        </InfoSection>
      )}

      {optimizationResult && (
        <InfoSection title="优化结果" icon={<CheckCircle size={12} />}>
          <Row
            label="优化状态"
            value={optimizationResult.converged ? "已收敛" : "未收敛"}
            valueClass={optimizationResult.converged ? "text-success" : "text-warning"}
            icon={optimizationResult.converged ? <CheckCircle size={10} className="text-success" /> : undefined}
          />
          <Row label="迭代次数" value={String(optimizationResult.iterations)} />
          <Row label="充填改善"
            value={`${(optimizationResult.initial_fill_fraction * 100).toFixed(0)}% → ${(optimizationResult.final_fill_fraction * 100).toFixed(0)}%`}
            valueClass="text-accent" />
        </InfoSection>
      )}
    </>
  );
}

function WorkflowProgressSection() {
  const { currentStep } = useAppStore();
  const modelId = useModelStore((s) => s.modelId);
  const { orientationResult, moldResult } = useMoldStore();
  const { insertId } = useInsertStore();
  const { gatingResult, simResult, optimizationResult } = useSimStore();

  const steps = [
    { key: "import", label: "导入", done: !!modelId },
    { key: "repair", label: "编辑", done: !!modelId },
    { key: "orientation", label: "方向", done: !!orientationResult },
    { key: "mold", label: "模具", done: !!moldResult },
    { key: "insert", label: "支撑板", done: !!insertId },
    { key: "gating", label: "浇注", done: !!gatingResult },
    { key: "simulation", label: "仿真", done: !!simResult },
    { key: "export", label: "导出", done: !!optimizationResult },
  ];

  return (
    <InfoSection title="工作流进度" icon={<Clock size={12} />}>
      {steps.map((s) => (
        <Row
          key={s.key}
          label={s.label}
          value={s.done ? "✓ 完成" : s.key === currentStep ? "● 当前" : "—"}
          valueClass={s.done ? "text-success" : s.key === currentStep ? "text-accent" : "text-text-muted"}
        />
      ))}
    </InfoSection>
  );
}

/* ── Scene Manager (Blender-style outliner) ────────────────────────── */

function SceneItem({
  label,
  icon,
  visible,
  opacity,
  onToggle,
  onOpacityChange,
  indent = 0,
  showOpacity = true,
}: {
  label: string;
  icon?: React.ReactNode;
  visible: boolean;
  opacity: number;
  onToggle: () => void;
  onOpacityChange?: (v: number) => void;
  indent?: number;
  showOpacity?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] hover:bg-bg-hover/50 transition-colors group",
          !visible && "opacity-50",
        )}
        style={{ paddingLeft: `${6 + indent * 12}px` }}
      >
        <button
          onClick={onToggle}
          className="shrink-0 text-text-muted hover:text-text-primary"
        >
          {visible ? <Eye size={11} /> : <EyeOff size={11} />}
        </button>
        {icon && <span className="shrink-0">{icon}</span>}
        <span className="flex-1 text-text-secondary truncate">{label}</span>
        {showOpacity && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 opacity-0 group-hover:opacity-100 text-text-muted hover:text-text-primary transition-opacity"
          >
            <ChevronDown
              size={9}
              className={cn("transition-transform", expanded && "rotate-180")}
            />
          </button>
        )}
      </div>
      {expanded && showOpacity && onOpacityChange && (
        <div
          className="flex items-center gap-1 px-2 py-0.5"
          style={{ paddingLeft: `${18 + indent * 12}px` }}
        >
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => onOpacityChange(parseFloat(e.target.value))}
            className="flex-1 accent-accent h-1"
          />
          <span className="text-[9px] text-text-muted w-7 text-right">
            {Math.round(opacity * 100)}%
          </span>
        </div>
      )}
    </div>
  );
}

function SceneManager() {
  const hasModel = useModelStore((s) => !!s.modelId);
  const filename = useModelStore((s) => s.filename);
  const moldResult = useMoldStore((s) => s.moldResult);
  const hasVisualization = useSimStore((s) => !!s.visualizationData);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const setHeatmapVisible = useSimStore((s) => s.setHeatmapVisible);

  const {
    modelVisible, modelOpacity, moldVisible, moldOpacity, shellOverrides,
    insertVisible, insertOpacity,
    setModelVisible, setModelOpacity, setMoldVisible, setMoldOpacity, setShellOverride,
    setInsertVisible, setInsertOpacity,
  } = useViewportStore();
  const insertId = useInsertStore((s) => s.insertId);
  const insertPlates = useInsertStore((s) => s.plates);

  return (
    <div className="border-b border-border">
      <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wider">
        <Layers size={11} />
        场景
      </div>
      <div className="px-2 pb-2 space-y-0.5">
        {hasModel && (
          <SceneItem
            label={filename || "源模型"}
            icon={<Box size={11} className="text-blue-400" />}
            visible={modelVisible}
            opacity={modelOpacity}
            onToggle={() => setModelVisible(!modelVisible)}
            onOpacityChange={setModelOpacity}
          />
        )}

        {moldResult && (
          <>
            <SceneItem
              label={`模具壳体 (${moldResult.n_shells})`}
              icon={<Layers size={11} className="text-cyan-400" />}
              visible={moldVisible}
              opacity={moldOpacity}
              onToggle={() => setMoldVisible(!moldVisible)}
              onOpacityChange={setMoldOpacity}
            />
            {moldResult.shells.map((sh) => {
              const ov = shellOverrides[sh.shell_id];
              return (
                <SceneItem
                  key={sh.shell_id}
                  label={`壳体 #${sh.shell_id}`}
                  visible={ov?.visible ?? true}
                  opacity={ov?.opacity ?? moldOpacity}
                  onToggle={() =>
                    setShellOverride(sh.shell_id, {
                      visible: !(ov?.visible ?? true),
                    })
                  }
                  onOpacityChange={(v) =>
                    setShellOverride(sh.shell_id, { opacity: v })
                  }
                  indent={1}
                />
              );
            })}
          </>
        )}

        {insertId && insertPlates.length > 0 && (
          <SceneItem
            label={`支撑板 (${insertPlates.length})`}
            icon={<Pin size={11} className="text-green-400" />}
            visible={insertVisible}
            opacity={insertOpacity}
            onToggle={() => setInsertVisible(!insertVisible)}
            onOpacityChange={setInsertOpacity}
          />
        )}

        {hasVisualization && (
          <SceneItem
            label="仿真热力图"
            icon={<ThermometerSun size={11} className="text-orange-400" />}
            visible={heatmapVisible}
            opacity={1}
            onToggle={() => setHeatmapVisible(!heatmapVisible)}
            showOpacity={false}
          />
        )}

        {!hasModel && (
          <div className="text-[10px] text-text-muted/50 text-center py-2">
            暂无场景对象
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Main panel ────────────────────────────────────────────────────── */

export function RightPanel() {
  const { rightPanelOpen, toggleRightPanel, currentStep } = useAppStore();
  const { modelId, filename, meshInfo } = useModelStore();

  return (
    <AnimatePresence initial={false}>
      {rightPanelOpen && (
        <motion.div
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 260, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="h-full bg-bg-panel border-l border-border overflow-hidden flex flex-col"
        >
          <div className="flex items-center justify-between px-3 h-9 border-b border-border shrink-0">
            <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              {STEP_TITLES[currentStep] ?? "信息"}
            </span>
            <button onClick={toggleRightPanel} className="p-1 rounded hover:bg-bg-hover text-text-muted">
              <ChevronRight size={14} />
            </button>
          </div>

          <SceneManager />

          <div className="flex-1 overflow-y-auto p-3 space-y-4">
            {modelId && meshInfo ? (
              <>
                <InfoSection title="模型" icon={<Layers size={12} />}>
                  <Row label="文件名" value={filename || "—"} />
                  <Row label="格式" value={meshInfo.source_format} />
                </InfoSection>

                <InfoSection title="网格" icon={<Triangle size={12} />}>
                  <Row label="顶点" value={meshInfo.vertex_count.toLocaleString()} />
                  <Row label="面片" value={meshInfo.face_count.toLocaleString()} />
                  <Row
                    label="水密"
                    value={meshInfo.is_watertight ? "是" : "否"}
                    valueClass={meshInfo.is_watertight ? "text-success" : "text-warning"}
                    icon={meshInfo.is_watertight
                      ? <CheckCircle size={10} className="text-success" />
                      : <AlertTriangle size={10} className="text-warning" />
                    }
                  />
                </InfoSection>

                <InfoSection title="包围盒" icon={<Ruler size={12} />}>
                  <Row label="X" value={`${meshInfo.extents[0].toFixed(2)} ${meshInfo.unit}`} />
                  <Row label="Y" value={`${meshInfo.extents[1].toFixed(2)} ${meshInfo.unit}`} />
                  <Row label="Z" value={`${meshInfo.extents[2].toFixed(2)} ${meshInfo.unit}`} />
                </InfoSection>

                {meshInfo.volume !== null && (
                  <InfoSection title="物理量" icon={<Droplets size={12} />}>
                    <Row label="体积" value={`${meshInfo.volume.toFixed(2)} ${meshInfo.unit}³`} />
                    <Row label="表面积" value={`${meshInfo.surface_area.toFixed(2)} ${meshInfo.unit}²`} />
                  </InfoSection>
                )}
              </>
            ) : (
              <div className="text-center text-text-muted text-xs py-8">
                <Info size={24} className="mx-auto mb-2 opacity-40" />
                导入模型后显示信息
              </div>
            )}

            <MoldInfoSection />
            <PartingInfoSection />
            <InsertInfoSection />
            <GatingInfoSection />
            <SimInfoSection />
            <WorkflowProgressSection />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
