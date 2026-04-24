import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronRight, Info, Layers, Droplets, Triangle,
  CheckCircle, AlertTriangle, Compass, Boxes, Pin,
  FlaskConical, Clock, Hash, Ruler,
  Box, ThermometerSun, BarChart3, SlidersHorizontal,
  Activity, Gauge,
} from "lucide-react";
import { useAppStore, type WorkflowStep } from "../../stores/appStore";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useInsertStore } from "../../stores/insertStore";
import { useSimStore } from "../../stores/simStore";
import { SceneManager } from "./SceneManager";
import { cn } from "../../lib/utils";

/* ── Tab definitions ─────────────────────────────────────────────── */

type RightTab = "scene" | "properties" | "stats";

const TAB_META: { id: RightTab; label: string; icon: React.ReactNode }[] = [
  { id: "scene", label: "大纲", icon: <Layers size={12} /> },
  { id: "properties", label: "属性", icon: <SlidersHorizontal size={12} /> },
  { id: "stats", label: "统计", icon: <BarChart3 size={12} /> },
];

/* ── Reusable primitives ─────────────────────────────────────────── */

function SectionHeader({
  title,
  icon,
  badge,
  defaultOpen = true,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  badge?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="mb-1">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 w-full px-1 py-1 rounded hover:bg-bg-hover/40 transition-colors group"
      >
        <ChevronRight
          size={10}
          className={cn("text-text-muted transition-transform shrink-0", open && "rotate-90")}
        />
        <span className="flex items-center gap-1.5">
          {icon}
          <span className="text-[12px] font-semibold text-text-muted uppercase tracking-wider">
            {title}
          </span>
        </span>
        {badge && (
          <span className="ml-auto text-[11px] text-accent/70 tabular-nums">{badge}</span>
        )}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.12 }}
            className="overflow-hidden"
          >
            <div className="pl-3 pr-1 pb-1 space-y-[2px]">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function PropRow({
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
    <div className="flex justify-between items-center py-[3px] px-2 rounded bg-bg-inset text-[12px]">
      <span className="text-text-muted">{label}</span>
      <span className={cn("flex items-center gap-1 tabular-nums", valueClass || "text-text-secondary")}>
        {icon}
        {value}
      </span>
    </div>
  );
}

function StatBar({
  label,
  value,
  max,
  color = "accent",
}: {
  label: string;
  value: number;
  max: number;
  color?: string;
}) {
  const pct = max > 0 ? Math.min(value / max, 1) * 100 : 0;
  return (
    <div className="px-2 py-[3px]">
      <div className="flex justify-between text-[12px] mb-0.5">
        <span className="text-text-muted">{label}</span>
        <span className="text-text-secondary tabular-nums">{value.toLocaleString()}</span>
      </div>
      <div className="h-[3px] rounded-full bg-bg-hover overflow-hidden">
        <motion.div
          className={`h-full rounded-full bg-${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

/* ── Properties Tab ──────────────────────────────────────────────── */

function PropertiesTab() {
  const { modelId, filename, meshInfo } = useModelStore();
  const { orientationResult, moldResult, partingResult } = useMoldStore();
  const { insertId, plates, assemblyValid } = useInsertStore();
  const { gatingResult, simResult, optimizationResult, visualizationData } = useSimStore();

  if (!modelId) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-2">
        <Info size={28} className="text-text-muted/20" />
        <span className="text-[11px] text-text-muted/40">导入模型后显示属性</span>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {/* Model info */}
      {meshInfo && (
        <>
          <SectionHeader title="模型" icon={<Box size={11} className="text-obj-model" />}>
            <PropRow label="文件" value={filename || "—"} />
            <PropRow label="格式" value={meshInfo.source_format} />
            <PropRow label="单位" value={meshInfo.unit} />
          </SectionHeader>

          <SectionHeader title="网格" icon={<Triangle size={11} className="text-obj-model" />}>
            <PropRow label="顶点" value={meshInfo.vertex_count.toLocaleString()} />
            <PropRow label="面片" value={meshInfo.face_count.toLocaleString()} />
            <PropRow
              label="水密"
              value={meshInfo.is_watertight ? "是" : "否"}
              valueClass={meshInfo.is_watertight ? "text-success" : "text-warning"}
              icon={meshInfo.is_watertight
                ? <CheckCircle size={9} className="text-success" />
                : <AlertTriangle size={9} className="text-warning" />
              }
            />
          </SectionHeader>

          <SectionHeader title="尺寸" icon={<Ruler size={11} className="text-info" />}>
            <PropRow label="X" value={`${meshInfo.extents[0].toFixed(2)} ${meshInfo.unit}`} />
            <PropRow label="Y" value={`${meshInfo.extents[1].toFixed(2)} ${meshInfo.unit}`} />
            <PropRow label="Z" value={`${meshInfo.extents[2].toFixed(2)} ${meshInfo.unit}`} />
            {meshInfo.volume !== null && (
              <>
                <PropRow label="体积" value={`${meshInfo.volume.toFixed(2)} ${meshInfo.unit}³`} />
                <PropRow label="表面积" value={`${meshInfo.surface_area.toFixed(2)} ${meshInfo.unit}²`} />
              </>
            )}
          </SectionHeader>
        </>
      )}

      {/* Orientation */}
      {orientationResult && (
        <SectionHeader title="方向分析" icon={<Compass size={11} className="text-accent" />} badge={`${(orientationResult.best_score.total_score * 100).toFixed(0)}%`}>
          <PropRow
            label="最佳方向"
            value={orientationResult.best_direction.map((v) => v.toFixed(2)).join(", ")}
          />
          <PropRow label="最小拔模角" value={`${orientationResult.best_score.min_draft_angle.toFixed(1)}°`} />
          <PropRow label="候选数" value={String(orientationResult.top_candidates.length)} />
        </SectionHeader>
      )}

      {/* Parting */}
      {partingResult && (
        <SectionHeader title="分型面" icon={<Hash size={11} className="text-accent" />}>
          <PropRow label="分型线" value={`${partingResult.parting_lines.length} 条`} />
          <PropRow label="上模面" value={partingResult.n_upper_faces.toLocaleString()} />
          <PropRow label="下模面" value={partingResult.n_lower_faces.toLocaleString()} />
          {partingResult.surface_type_used && (
            <PropRow
              label="面型"
              value={({ flat: "平面", heightfield: "高度场", projected: "投影拉伸" } as Record<string, string>)[partingResult.surface_type_used] ?? "平面"}
            />
          )}
          {partingResult.undercut && (
            <>
              <PropRow
                label="倒扣严重度"
                value={({ none: "无", mild: "轻微", moderate: "中等", severe: "严重" })[partingResult.undercut.severity]}
                valueClass={partingResult.undercut.severity === "none" ? "text-success" : partingResult.undercut.severity === "severe" ? "text-danger" : "text-warning"}
              />
              <PropRow label="倒扣面" value={`${partingResult.undercut.n_undercut_faces} / ${partingResult.undercut.total_faces}`} />
              <PropRow label="最大深度" value={`${partingResult.undercut.max_depth.toFixed(2)} mm`} />
              {partingResult.undercut.total_volume > 0 && (
                <PropRow label="倒扣体积" value={`${partingResult.undercut.total_volume.toFixed(1)} mm³`} />
              )}
              {partingResult.undercut.side_pulls && partingResult.undercut.side_pulls.length > 0 && (
                <PropRow label="侧抽推荐" value={`${partingResult.undercut.side_pulls.length} 方向`} />
              )}
            </>
          )}
        </SectionHeader>
      )}

      {/* Mold shells */}
      {moldResult && (
        <>
          <SectionHeader title="模具壳体" icon={<Boxes size={11} className="text-obj-mold" />} badge={`${moldResult.n_shells} 壳`}>
            <PropRow label="型腔体积" value={`${moldResult.cavity_volume.toFixed(1)} mm³`} />
            {moldResult.parting_surface_type && (
              <PropRow label="分型面类型" value={({ flat: "平面", heightfield: "高度场", projected: "投影拉伸" } as Record<string, string>)[moldResult.parting_surface_type] ?? moldResult.parting_surface_type} />
            )}
            {moldResult.undercut_severity && moldResult.undercut_severity !== "none" && (
              <PropRow
                label="倒扣严重度"
                value={({ mild: "轻微", moderate: "中等", severe: "严重" } as Record<string, string>)[moldResult.undercut_severity] ?? moldResult.undercut_severity}
                valueClass={moldResult.undercut_severity === "severe" ? "text-danger" : "text-warning"}
              />
            )}
            {moldResult.shells.map((sh) => (
              <PropRow
                key={sh.shell_id}
                label={`壳 #${sh.shell_id}`}
                value={`${sh.face_count.toLocaleString()} 面`}
                valueClass={sh.is_printable ? "text-success" : "text-warning"}
              />
            ))}
          </SectionHeader>

          <SectionHeader title="浇注/排气" icon={<Droplets size={11} className="text-obj-gating" />}>
            {moldResult.pour_hole && typeof moldResult.pour_hole === "object" && !Array.isArray(moldResult.pour_hole) ? (
              <PropRow
                label="浇口评分"
                value={`${(((moldResult.pour_hole as { score?: number }).score ?? 0) * 100).toFixed(1)}%`}
                valueClass="text-accent"
              />
            ) : moldResult.pour_hole ? (
              <PropRow label="浇口" value="已放置" />
            ) : null}
            <PropRow label="排气口" value={`${moldResult.vent_holes.length} 个`} />
            {moldResult.alignment_features && (
              <PropRow
                label="定位销"
                value={`${moldResult.alignment_features.filter(f => f.type === "pin").length} 对`}
              />
            )}
          </SectionHeader>
        </>
      )}

      {/* Insert */}
      {insertId && plates.length > 0 && (
        <SectionHeader title="支撑板" icon={<Pin size={11} className="text-obj-insert" />} badge={`${plates.length} 板`}>
          <PropRow
            label="装配"
            value={assemblyValid ? "通过" : "待验证"}
            valueClass={assemblyValid ? "text-success" : "text-text-muted"}
            icon={assemblyValid ? <CheckCircle size={9} className="text-success" /> : undefined}
          />
          {plates.map((p, i) => (
            <PropRow
              key={i}
              label={`板 #${i + 1}`}
              value={`${p.face_count.toLocaleString()} 面`}
            />
          ))}
        </SectionHeader>
      )}

      {/* Gating */}
      {gatingResult && (
        <SectionHeader title="浇注系统" icon={<Droplets size={11} className="text-obj-gating" />} badge={`${(gatingResult.gate.score * 100).toFixed(0)}%`}>
          <PropRow label="浇口直径" value={`${gatingResult.gate_diameter.toFixed(1)} mm`} />
          <PropRow label="浇道宽度" value={`${gatingResult.runner_width.toFixed(1)} mm`} />
          <PropRow label="排气孔" value={`${gatingResult.vents.length} 个`} />
          <PropRow label="预计充填" value={`${gatingResult.estimated_fill_time.toFixed(1)} s`} />
        </SectionHeader>
      )}

      {/* Simulation */}
      {simResult && (
        <>
          <SectionHeader title="仿真结果" icon={<FlaskConical size={11} className="text-obj-sim" />} badge={`${(simResult.fill_fraction * 100).toFixed(0)}%`}>
            <PropRow
              label="充填率"
              value={`${(simResult.fill_fraction * 100).toFixed(1)}%`}
              valueClass={simResult.fill_fraction >= 0.99 ? "text-success" : "text-warning"}
            />
            <PropRow label="充填时间" value={`${simResult.fill_time_seconds.toFixed(1)} s`} />
            <PropRow label="最大压力" value={`${simResult.max_pressure.toFixed(0)} Pa`} />
            <PropRow
              label="缺陷"
              value={`${simResult.defects.length} 个`}
              valueClass={simResult.defects.length === 0 ? "text-success" : "text-warning"}
            />
          </SectionHeader>

          {simResult.analysis && (
            <SectionHeader title="质量分析" icon={<Gauge size={11} className="text-info" />}>
              <PropRow
                label="质量评分"
                value={`${(simResult.analysis.fill_quality_score * 100).toFixed(1)}%`}
                valueClass={simResult.analysis.fill_quality_score >= 0.8 ? "text-success" : "text-warning"}
              />
              <PropRow label="填充均匀" value={`${(simResult.analysis.fill_uniformity_index * 100).toFixed(0)}%`} />
              <PropRow label="压力均匀" value={`${(simResult.analysis.pressure_uniformity_index * 100).toFixed(0)}%`} />
              <PropRow label="浇口效率" value={`${(simResult.analysis.gate_efficiency * 100).toFixed(0)}%`} />
            </SectionHeader>
          )}
        </>
      )}

      {/* Optimization */}
      {optimizationResult && (
        <SectionHeader title="优化" icon={<Activity size={11} className="text-success" />}>
          <PropRow
            label="状态"
            value={optimizationResult.converged ? "已收敛" : "未收敛"}
            valueClass={optimizationResult.converged ? "text-success" : "text-warning"}
          />
          <PropRow label="迭代" value={String(optimizationResult.iterations)} />
          <PropRow
            label="充填改善"
            value={`${(optimizationResult.initial_fill_fraction * 100).toFixed(0)}% → ${(optimizationResult.final_fill_fraction * 100).toFixed(0)}%`}
            valueClass="text-accent"
          />
        </SectionHeader>
      )}
    </div>
  );
}

/* ── Statistics Tab ──────────────────────────────────────────────── */

function StatsTab() {
  const meshInfo = useModelStore((s) => s.meshInfo);
  const moldResult = useMoldStore((s) => s.moldResult);
  const { gatingResult, simResult, visualizationData } = useSimStore();
  const insertPlates = useInsertStore((s) => s.plates);
  const { currentStep } = useAppStore();

  const steps = [
    { key: "import", label: "导入" },
    { key: "repair", label: "编辑" },
    { key: "orientation", label: "方向" },
    { key: "mold", label: "模具" },
    { key: "insert", label: "支撑" },
    { key: "gating", label: "浇注" },
    { key: "simulation", label: "仿真" },
    { key: "export", label: "导出" },
  ];
  const modelId = useModelStore((s) => s.modelId);
  const { orientationResult } = useMoldStore();
  const { insertId } = useInsertStore();
  const { optimizationResult } = useSimStore();
  const stepDone: Record<string, boolean> = {
    import: !!modelId,
    repair: !!modelId,
    orientation: !!orientationResult,
    mold: !!moldResult,
    insert: !!insertId,
    gating: !!gatingResult,
    simulation: !!simResult,
    export: !!optimizationResult,
  };

  return (
    <div className="space-y-1">
      {/* Workflow progress */}
      <SectionHeader title="工作流" icon={<Clock size={11} className="text-accent" />}>
        <div className="space-y-1 pt-0.5">
          {steps.map((s) => {
            const done = stepDone[s.key];
            const active = s.key === currentStep;
            return (
              <div key={s.key} className="flex items-center gap-2 px-2 py-[2px]">
                <div className={cn(
                  "w-2 h-2 rounded-full shrink-0",
                  done ? "bg-success" : active ? "bg-accent" : "bg-border",
                )} />
                <span className={cn(
                  "text-[12px] flex-1",
                  done ? "text-success" : active ? "text-accent" : "text-text-muted/60",
                )}>
                  {s.label}
                </span>
                <span className={cn(
                  "text-[11px]",
                  done ? "text-success/60" : active ? "text-accent/60" : "text-text-muted/30",
                )}>
                  {done ? "✓" : active ? "●" : "—"}
                </span>
              </div>
            );
          })}
        </div>
      </SectionHeader>

      {/* Geometry stats */}
      {meshInfo && (
        <SectionHeader title="几何统计" icon={<Triangle size={11} className="text-obj-model" />}>
          <StatBar label="面片" value={meshInfo.face_count} max={500_000} color="obj-model" />
          <StatBar label="顶点" value={meshInfo.vertex_count} max={250_000} color="accent" />
          {moldResult && (
            <>
              <div className="h-px bg-border-subtle mx-2 my-1" />
              {moldResult.shells.map((sh) => (
                <StatBar
                  key={sh.shell_id}
                  label={`壳 #${sh.shell_id}`}
                  value={sh.face_count}
                  max={Math.max(...moldResult.shells.map(s => s.face_count))}
                  color="obj-mold"
                />
              ))}
            </>
          )}
        </SectionHeader>
      )}

      {/* Simulation summary */}
      {simResult && (
        <SectionHeader title="仿真摘要" icon={<FlaskConical size={11} className="text-obj-sim" />}>
          <StatBar label="充填率" value={Math.round(simResult.fill_fraction * 100)} max={100} color="success" />
          {simResult.analysis && (
            <>
              <StatBar label="质量评分" value={Math.round(simResult.analysis.fill_quality_score * 100)} max={100} color="accent" />
              <StatBar label="填充均匀" value={Math.round(simResult.analysis.fill_uniformity_index * 100)} max={100} color="info" />
            </>
          )}
        </SectionHeader>
      )}
    </div>
  );
}

/* ── Main panel ──────────────────────────────────────────────────── */

export function RightPanel() {
  const { rightPanelOpen, toggleRightPanel } = useAppStore();
  const [activeTab, setActiveTab] = useState<RightTab>("scene");

  return (
    <AnimatePresence initial={false}>
      {rightPanelOpen && (
        <motion.div
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 280, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="h-full bg-bg-panel border-l border-border overflow-hidden flex flex-col"
        >
          {/* Tab bar */}
          <div className="flex items-center h-8 border-b border-border shrink-0">
            <div className="flex items-center flex-1">
              {TAB_META.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex items-center gap-1 px-3 h-8 text-[11px] font-medium transition-all relative",
                    activeTab === tab.id
                      ? "text-text-primary"
                      : "text-text-muted hover:text-text-secondary",
                  )}
                >
                  {tab.icon}
                  {tab.label}
                  {activeTab === tab.id && (
                    <motion.div
                      layoutId="right-tab-indicator"
                      className="absolute bottom-0 left-2 right-2 h-[2px] bg-accent rounded-full"
                    />
                  )}
                </button>
              ))}
            </div>
            <button
              onClick={toggleRightPanel}
              className="p-1.5 mr-1 rounded hover:bg-bg-hover text-text-muted shrink-0"
              title="收起面板"
            >
              <ChevronRight size={13} />
            </button>
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto">
            {activeTab === "scene" && (
              <SceneManager />
            )}
            {activeTab === "properties" && (
              <div className="p-2">
                <PropertiesTab />
              </div>
            )}
            {activeTab === "stats" && (
              <div className="p-2">
                <StatsTab />
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
