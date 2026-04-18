import { motion } from "framer-motion";
import {
  Upload, FolderOpen, RotateCcw, Scissors, Maximize2, Ruler, FlipVertical,
  Grid3x3, ArrowUpDown, Compass, RefreshCw, SplitSquareVertical, Box,
  LayoutGrid, Droplets, Pin, Eye, Layers, Wrench, FlaskConical, Zap,
  BarChart3, Download, FileArchive, FileBox, Package, Scan, Move,
  RotateCw, ZoomIn, ZoomOut, Copy, Trash2,
} from "lucide-react";
import type { ReactNode } from "react";
import type { WorkflowStep } from "../../stores/appStore";
import { useAppStore } from "../../stores/appStore";
import { cn } from "../../lib/utils";

interface ToolItem {
  id: string;
  icon: ReactNode;
  label: string;
  shortcut?: string;
  divider?: boolean;
}

const STEP_TOOLS: Record<WorkflowStep, ToolItem[]> = {
  import: [
    { id: "open", icon: <FolderOpen size={13} />, label: "打开文件", shortcut: "O" },
    { id: "upload", icon: <Upload size={13} />, label: "上传模型", shortcut: "U" },
    { id: "d_scan", divider: true, icon: <Scan size={13} />, label: "扫描导入" },
    { id: "recent", icon: <Copy size={13} />, label: "最近文件" },
  ],
  repair: [
    { id: "auto_repair", icon: <RotateCcw size={13} />, label: "自动修复", shortcut: "R" },
    { id: "simplify", icon: <Scissors size={13} />, label: "简化", shortcut: "S" },
    { id: "subdivide", icon: <Grid3x3 size={13} />, label: "细分" },
    { id: "d_transform", divider: true, icon: <Move size={13} />, label: "移动" },
    { id: "rotate", icon: <RotateCw size={13} />, label: "旋转" },
    { id: "scale_up", icon: <ZoomIn size={13} />, label: "放大" },
    { id: "scale_down", icon: <ZoomOut size={13} />, label: "缩小" },
    { id: "center", icon: <Maximize2 size={13} />, label: "居中" },
    { id: "d_measure", divider: true, icon: <Ruler size={13} />, label: "测量" },
    { id: "flip", icon: <FlipVertical size={13} />, label: "翻转" },
    { id: "mirror", icon: <ArrowUpDown size={13} />, label: "镜像" },
    { id: "d_del", divider: true, icon: <Trash2 size={13} />, label: "删除选区" },
  ],
  orientation: [
    { id: "analyze", icon: <Compass size={13} />, label: "分析方向", shortcut: "A" },
    { id: "refresh", icon: <RefreshCw size={13} />, label: "刷新分析" },
    { id: "d_manual", divider: true, icon: <RotateCw size={13} />, label: "手动调整" },
    { id: "preview", icon: <Eye size={13} />, label: "预览脱模" },
  ],
  mold: [
    { id: "parting", icon: <SplitSquareVertical size={13} />, label: "分型面", shortcut: "P" },
    { id: "build_shell", icon: <Box size={13} />, label: "生成壳体", shortcut: "G" },
    { id: "d_edit", divider: true, icon: <Wrench size={13} />, label: "编辑壳体" },
    { id: "multi_part", icon: <LayoutGrid size={13} />, label: "多片壳体" },
    { id: "add_pin", icon: <Pin size={13} />, label: "定位销" },
    { id: "add_pour", icon: <Droplets size={13} />, label: "浇注口" },
    { id: "d_preview", divider: true, icon: <Eye size={13} />, label: "预览装配" },
  ],
  insert: [
    { id: "analyze_pos", icon: <Scan size={13} />, label: "分析位置", shortcut: "A" },
    { id: "gen_plate", icon: <Layers size={13} />, label: "生成支撑板", shortcut: "G" },
    { id: "d_edit", divider: true, icon: <Wrench size={13} />, label: "编辑板形" },
    { id: "add_anchor", icon: <Pin size={13} />, label: "添加锚固" },
    { id: "validate", icon: <Eye size={13} />, label: "校验装配" },
  ],
  gating: [
    { id: "design", icon: <Droplets size={13} />, label: "设计浇注系统", shortcut: "D" },
    { id: "d_edit", divider: true, icon: <Wrench size={13} />, label: "编辑浇道" },
    { id: "add_vent", icon: <Pin size={13} />, label: "添加排气" },
    { id: "preview", icon: <Eye size={13} />, label: "预览" },
  ],
  simulation: [
    { id: "run_sim", icon: <FlaskConical size={13} />, label: "运行仿真", shortcut: "F5" },
    { id: "optimize", icon: <Zap size={13} />, label: "自动优化", shortcut: "F6" },
    { id: "d_vis", divider: true, icon: <BarChart3 size={13} />, label: "结果分析" },
    { id: "heatmap", icon: <Eye size={13} />, label: "热力图" },
    { id: "defects", icon: <Scan size={13} />, label: "缺陷检查" },
  ],
  export: [
    { id: "export_model", icon: <Download size={13} />, label: "导出模型", shortcut: "E" },
    { id: "export_mold", icon: <FileBox size={13} />, label: "导出模具" },
    { id: "export_insert", icon: <Layers size={13} />, label: "导出支撑板" },
    { id: "d_all", divider: true, icon: <FileArchive size={13} />, label: "全部打包" },
    { id: "export_all", icon: <Package size={13} />, label: "一键导出" },
  ],
};

export function StepToolbar() {
  const step = useAppStore((s) => s.currentStep);
  const tools = STEP_TOOLS[step] ?? [];

  if (tools.length === 0) return null;

  return (
    <div className="flex items-center gap-0 px-1.5 py-0.5 border-b border-border-subtle bg-bg-secondary/60 backdrop-blur-sm flex-wrap min-h-[28px] shrink-0">
      {tools.map((tool) => (
        <div key={tool.id} className="flex items-center">
          {tool.divider && <div className="w-px h-3.5 bg-border/30 mx-1" />}
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => {
              window.dispatchEvent(new CustomEvent("moldgen:toolbar-action", { detail: tool.id }));
            }}
            className={cn(
              "flex items-center gap-1 px-1.5 py-1 rounded-[3px] text-text-muted",
              "hover:bg-bg-hover/60 hover:text-text-primary transition-all",
              "group relative",
            )}
            title={`${tool.label}${tool.shortcut ? ` (${tool.shortcut})` : ""}`}
          >
            {tool.icon}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded-md bg-bg-primary/95 backdrop-blur border border-border text-text-secondary whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-xl z-10 tooltip-anim">
              <div className="text-[10px] font-medium">{tool.label}</div>
              {tool.shortcut && <div className="text-[9px] text-text-muted mt-0.5">{tool.shortcut}</div>}
            </div>
          </motion.button>
        </div>
      ))}
    </div>
  );
}
