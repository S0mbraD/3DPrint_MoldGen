import { useState, useCallback, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Eye, EyeOff, ChevronRight, ChevronDown,
  Box, Layers, Pin, ThermometerSun, Droplets,
  Lock, Unlock, Focus, Trash2, Copy,
  ChevronsUpDown, Search, SlidersHorizontal,
  Grid3x3, Blend,
} from "lucide-react";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useInsertStore } from "../../stores/insertStore";
import { useSimStore } from "../../stores/simStore";
import { useViewportStore } from "../../stores/viewportStore";
import { cn } from "../../lib/utils";

type SceneNodeType = "model" | "mold" | "shell" | "insert" | "gating" | "sim" | "group" | "analysis";

interface SceneNodeData {
  id: string;
  type: SceneNodeType;
  label: string;
  icon: ReactNode;
  color: string;
  visible: boolean;
  locked: boolean;
  opacity: number;
  children?: SceneNodeData[];
  onToggleVisible: () => void;
  onOpacityChange?: (v: number) => void;
  meta?: Record<string, string>;
}

const TYPE_ICONS: Record<SceneNodeType, string> = {
  model: "bg-obj-model/20 text-obj-model",
  mold: "bg-obj-mold/20 text-obj-mold",
  shell: "bg-obj-shell/20 text-obj-shell",
  insert: "bg-obj-insert/20 text-obj-insert",
  gating: "bg-obj-gating/20 text-obj-gating",
  sim: "bg-obj-sim/20 text-obj-sim",
  group: "bg-bg-hover text-text-muted",
  analysis: "bg-info/20 text-info",
};

function SceneNode({
  node,
  depth = 0,
  selectedId,
  onSelect,
}: {
  node: SceneNodeData;
  depth?: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const [showSlider, setShowSlider] = useState(false);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = selectedId === node.id;

  return (
    <div>
      {/* Node row */}
      <div
        className={cn(
          "flex items-center gap-1 h-[26px] pr-1.5 rounded-[3px] cursor-pointer transition-all group",
          "hover:bg-bg-hover/60",
          isSelected && "bg-accent/10 ring-1 ring-accent/30",
          !node.visible && "opacity-40",
        )}
        style={{ paddingLeft: `${4 + depth * 16}px` }}
        onClick={() => onSelect(node.id)}
        onDoubleClick={() => hasChildren && setExpanded(!expanded)}
      >
        {/* Expand arrow */}
        {hasChildren ? (
          <button
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            className="shrink-0 w-3.5 h-3.5 flex items-center justify-center text-text-muted hover:text-text-primary"
          >
            {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
        ) : (
          <span className="w-3.5 shrink-0" />
        )}

        {/* Visibility toggle */}
        <button
          onClick={(e) => { e.stopPropagation(); node.onToggleVisible(); }}
          className={cn(
            "shrink-0 w-4 h-4 flex items-center justify-center rounded transition-colors",
            node.visible ? "text-text-muted hover:text-text-primary" : "text-text-muted/30 hover:text-text-muted",
          )}
        >
          {node.visible ? <Eye size={11} /> : <EyeOff size={11} />}
        </button>

        {/* Type icon badge */}
        <div className={cn(
          "shrink-0 w-4 h-4 rounded flex items-center justify-center",
          TYPE_ICONS[node.type],
        )}>
          {node.icon}
        </div>

        {/* Label */}
        <span className={cn(
          "flex-1 text-[11px] truncate",
          isSelected ? "text-text-primary font-medium" : "text-text-secondary",
        )}>
          {node.label}
        </span>

        {/* Meta badge */}
        {node.meta && Object.entries(node.meta).slice(0, 1).map(([, val]) => (
          <span key={val} className="text-[11px] text-text-muted/60 tabular-nums shrink-0">
            {val}
          </span>
        ))}

        {/* Opacity slider toggle */}
        {node.onOpacityChange && (
          <button
            onClick={(e) => { e.stopPropagation(); setShowSlider(!showSlider); }}
            className={cn(
              "shrink-0 w-4 h-4 flex items-center justify-center rounded transition-all",
              showSlider
                ? "text-accent"
                : "opacity-0 group-hover:opacity-100 text-text-muted hover:text-text-primary",
            )}
          >
            <SlidersHorizontal size={9} />
          </button>
        )}
      </div>

      {/* Opacity slider row */}
      <AnimatePresence>
        {showSlider && node.onOpacityChange && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div
              className="flex items-center gap-2 h-5 pr-2"
              style={{ paddingLeft: `${22 + depth * 16}px` }}
            >
              <Blend size={9} className="text-text-muted shrink-0" />
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={node.opacity}
                onChange={(e) => node.onOpacityChange?.(parseFloat(e.target.value))}
                className="flex-1 h-[3px]"
                onClick={(e) => e.stopPropagation()}
              />
              <span className="text-[11px] text-text-muted w-6 text-right tabular-nums">
                {Math.round(node.opacity * 100)}%
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Children */}
      <AnimatePresence>
        {expanded && hasChildren && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.12 }}
          >
            {node.children!.map((child) => (
              <SceneNode
                key={child.id}
                node={child}
                depth={depth + 1}
                selectedId={selectedId}
                onSelect={onSelect}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function PropertiesInspector({ node }: { node: SceneNodeData | null }) {
  if (!node) return null;

  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      className="border-t border-border-subtle"
    >
      <div className="px-3 py-1.5">
        <div className="flex items-center gap-1.5 mb-1.5">
          <div className={cn("w-3.5 h-3.5 rounded flex items-center justify-center", TYPE_ICONS[node.type])}>
            {node.icon}
          </div>
          <span className="text-[11px] font-medium text-text-primary truncate">{node.label}</span>
        </div>

        {node.meta && Object.keys(node.meta).length > 0 && (
          <div className="space-y-0.5">
            {Object.entries(node.meta).map(([key, val]) => (
              <div key={key} className="flex justify-between items-center py-[2px] px-1.5 rounded bg-bg-inset text-[12px]">
                <span className="text-text-muted">{key}</span>
                <span className="text-text-secondary tabular-nums">{val}</span>
              </div>
            ))}
          </div>
        )}

        {node.onOpacityChange && (
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[12px] text-text-muted w-12">不透明度</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={node.opacity}
              onChange={(e) => node.onOpacityChange?.(parseFloat(e.target.value))}
              className="flex-1 h-[3px]"
            />
            <span className="text-[12px] text-text-muted w-8 text-right tabular-nums">
              {Math.round(node.opacity * 100)}%
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

export function SceneManager() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");
  const [showSearch, setShowSearch] = useState(false);

  const hasModel = useModelStore((s) => !!s.modelId);
  const filename = useModelStore((s) => s.filename);
  const meshInfo = useModelStore((s) => s.meshInfo);
  const moldResult = useMoldStore((s) => s.moldResult);
  const hasUndercutHeatmap = useMoldStore((s) => !!s.undercutHeatmap);
  const undercutHeatmapVisible = useMoldStore((s) => s.undercutHeatmapVisible);
  const setUndercutHeatmapVisible = useMoldStore((s) => s.setUndercutHeatmapVisible);
  const gatingResult = useSimStore((s) => s.gatingResult);
  const hasVisualization = useSimStore((s) => !!s.visualizationData);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const setHeatmapVisible = useSimStore((s) => s.setHeatmapVisible);
  const insertId = useInsertStore((s) => s.insertId);
  const insertPlates = useInsertStore((s) => s.plates);

  const {
    modelVisible, modelOpacity, moldVisible, moldOpacity, shellOverrides,
    insertVisible, insertOpacity,
    setModelVisible, setModelOpacity, setMoldVisible, setMoldOpacity, setShellOverride,
    setInsertVisible, setInsertOpacity,
  } = useViewportStore();

  const nodes: SceneNodeData[] = [];

  if (hasModel) {
    nodes.push({
      id: "model",
      type: "model",
      label: filename || "源模型",
      icon: <Box size={10} />,
      color: "obj-model",
      visible: modelVisible,
      locked: false,
      opacity: modelOpacity,
      onToggleVisible: () => setModelVisible(!modelVisible),
      onOpacityChange: setModelOpacity,
      meta: meshInfo ? {
        "面数": meshInfo.face_count.toLocaleString(),
        "顶点": meshInfo.vertex_count.toLocaleString(),
        "水密": meshInfo.is_watertight ? "是" : "否",
        "尺寸": `${meshInfo.extents[0].toFixed(1)}×${meshInfo.extents[1].toFixed(1)}×${meshInfo.extents[2].toFixed(1)} ${meshInfo.unit}`,
      } : undefined,
    });
  }

  if (moldResult) {
    const shellChildren: SceneNodeData[] = moldResult.shells.map((sh) => {
      const ov = shellOverrides[sh.shell_id];
      return {
        id: `shell-${sh.shell_id}`,
        type: "shell" as SceneNodeType,
        label: `壳体 #${sh.shell_id}`,
        icon: <Layers size={9} />,
        color: "obj-shell",
        visible: ov?.visible ?? true,
        locked: false,
        opacity: ov?.opacity ?? moldOpacity,
        onToggleVisible: () => setShellOverride(sh.shell_id, { visible: !(ov?.visible ?? true) }),
        onOpacityChange: (v: number) => setShellOverride(sh.shell_id, { opacity: v }),
        meta: {
          "面数": sh.face_count.toLocaleString(),
          "可打印": sh.is_printable ? "是" : "否",
          "拔模角": `${sh.min_draft_angle?.toFixed(1) ?? "—"}°`,
        },
      };
    });

    nodes.push({
      id: "mold",
      type: "mold",
      label: `模具壳体`,
      icon: <Grid3x3 size={10} />,
      color: "obj-mold",
      visible: moldVisible,
      locked: false,
      opacity: moldOpacity,
      children: shellChildren,
      onToggleVisible: () => setMoldVisible(!moldVisible),
      onOpacityChange: setMoldOpacity,
      meta: {
        "壳数": String(moldResult.n_shells),
        "腔体": `${moldResult.cavity_volume.toFixed(0)} mm³`,
      },
    });
  }

  if (insertId && insertPlates.length > 0) {
    nodes.push({
      id: "insert",
      type: "insert",
      label: `支撑板 (${insertPlates.length})`,
      icon: <Pin size={10} />,
      color: "obj-insert",
      visible: insertVisible,
      locked: false,
      opacity: insertOpacity,
      onToggleVisible: () => setInsertVisible(!insertVisible),
      onOpacityChange: setInsertOpacity,
      meta: { "板数": String(insertPlates.length) },
    });
  }

  if (gatingResult) {
    nodes.push({
      id: "gating",
      type: "gating",
      label: "浇注系统",
      icon: <Droplets size={10} />,
      color: "obj-gating",
      visible: true,
      locked: false,
      opacity: 1,
      onToggleVisible: () => {},
      meta: {
        "浇口": `Ø${gatingResult.gate_diameter.toFixed(1)}mm`,
        "排气": `${gatingResult.vents.length} 个`,
      },
    });
  }

  if (hasVisualization) {
    nodes.push({
      id: "sim-heatmap",
      type: "sim",
      label: "仿真热力图",
      icon: <ThermometerSun size={10} />,
      color: "obj-sim",
      visible: heatmapVisible,
      locked: false,
      opacity: 1,
      onToggleVisible: () => setHeatmapVisible(!heatmapVisible),
    });
  }

  if (hasUndercutHeatmap) {
    nodes.push({
      id: "undercut-heatmap",
      type: "analysis",
      label: "Undercut 热力图",
      icon: <Blend size={10} />,
      color: "info",
      visible: undercutHeatmapVisible,
      locked: false,
      opacity: 1,
      onToggleVisible: () => setUndercutHeatmapVisible(!undercutHeatmapVisible),
    });
  }

  const filteredNodes = filterText
    ? nodes.filter((n) => n.label.toLowerCase().includes(filterText.toLowerCase()))
    : nodes;

  const selectedNode = findNode(filteredNodes, selectedId);

  const totalObjects = countNodes(nodes);

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 h-7 border-b border-border-subtle shrink-0">
        <div className="flex items-center gap-1.5">
          <Layers size={12} className="text-text-muted" />
          <span className="text-[12px] font-semibold text-text-muted uppercase tracking-wider">
            场景大纲
          </span>
          {totalObjects > 0 && (
            <span className="text-[11px] text-text-muted/50 tabular-nums">{totalObjects}</span>
          )}
        </div>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => setShowSearch(!showSearch)}
            className={cn(
              "p-0.5 rounded hover:bg-bg-hover transition-colors",
              showSearch ? "text-accent" : "text-text-muted",
            )}
            title="搜索"
          >
            <Search size={11} />
          </button>
          <button
            onClick={() => {
              const allVisible = nodes.every((n) => n.visible);
              nodes.forEach((n) => n.onToggleVisible());
            }}
            className="p-0.5 rounded hover:bg-bg-hover text-text-muted transition-colors"
            title="切换全部可见性"
          >
            <ChevronsUpDown size={11} />
          </button>
        </div>
      </div>

      {/* Search bar */}
      <AnimatePresence>
        {showSearch && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-b border-border-subtle"
          >
            <div className="px-2 py-1">
              <div className="flex items-center gap-1 px-2 h-6 rounded bg-bg-inset border border-border-subtle">
                <Search size={10} className="text-text-muted shrink-0" />
                <input
                  type="text"
                  placeholder="筛选对象..."
                  value={filterText}
                  onChange={(e) => setFilterText(e.target.value)}
                  className="flex-1 bg-transparent text-[12px] text-text-primary placeholder:text-text-muted/40 outline-none"
                  autoFocus
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tree */}
      <div className="px-1 py-1 max-h-[280px] overflow-y-auto">
        {filteredNodes.length > 0 ? (
          filteredNodes.map((node) => (
            <SceneNode
              key={node.id}
              node={node}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          ))
        ) : (
          <div className="flex flex-col items-center py-6 gap-1.5">
            <Layers size={20} className="text-text-muted/20" />
            <span className="text-[12px] text-text-muted/40">
              {filterText ? "无匹配对象" : "暂无场景对象"}
            </span>
            {!filterText && (
              <span className="text-[11px] text-text-muted/30">导入模型以开始</span>
            )}
          </div>
        )}
      </div>

      {/* Properties inspector */}
      <AnimatePresence>
        {selectedNode && <PropertiesInspector node={selectedNode} />}
      </AnimatePresence>
    </div>
  );
}

function findNode(nodes: SceneNodeData[], id: string | null): SceneNodeData | null {
  if (!id) return null;
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children) {
      const found = findNode(n.children, id);
      if (found) return found;
    }
  }
  return null;
}

function countNodes(nodes: SceneNodeData[]): number {
  let count = 0;
  for (const n of nodes) {
    count++;
    if (n.children) count += countNodes(n.children);
  }
  return count;
}
