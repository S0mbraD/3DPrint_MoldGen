import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  History, X, Trash2, Upload, Scissors, Compass, Box, Layers,
  Droplets, Zap, Download, ChevronDown, SplitSquareVertical,
} from "lucide-react";
import { useHistoryStore, type HistoryRecord } from "../../stores/historyStore";
import { cn } from "../../lib/utils";

const TYPE_ICON: Record<string, React.ReactNode> = {
  import: <Upload size={11} />,
  repair: <Scissors size={11} />,
  simplify: <Scissors size={11} />,
  orientation: <Compass size={11} />,
  parting: <SplitSquareVertical size={11} />,
  mold: <Box size={11} />,
  insert: <Layers size={11} />,
  gating: <Droplets size={11} />,
  simulation: <Zap size={11} />,
  export: <Download size={11} />,
};

const TYPE_COLOR: Record<string, string> = {
  import: "text-blue-400",
  repair: "text-amber-400",
  simplify: "text-amber-400",
  orientation: "text-cyan-400",
  parting: "text-purple-400",
  mold: "text-accent",
  insert: "text-emerald-400",
  gating: "text-orange-400",
  simulation: "text-pink-400",
  export: "text-green-400",
};

function formatTime(ts: number) {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - ts;
  if (diffMs < 60_000) return "刚刚";
  if (diffMs < 3600_000) return `${Math.floor(diffMs / 60_000)}分钟前`;
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function RecordItem({ rec }: { rec: HistoryRecord }) {
  const remove = useHistoryStore((s) => s.remove);
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0 }}
      className="flex items-center gap-2 px-2 py-1.5 hover:bg-bg-hover rounded group"
    >
      <span className={cn("shrink-0", TYPE_COLOR[rec.type] ?? "text-text-muted")}>
        {TYPE_ICON[rec.type] ?? <History size={11} />}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[12px] text-text-primary truncate">{rec.label}</div>
        {rec.detail && (
          <div className="text-[11px] text-text-muted/60 truncate">{rec.detail}</div>
        )}
      </div>
      <span className="text-[11px] text-text-muted/40 shrink-0">{formatTime(rec.timestamp)}</span>
      <button
        onClick={() => remove(rec.id)}
        className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-bg-secondary text-text-muted/40 hover:text-danger transition-all"
      >
        <X size={9} />
      </button>
    </motion.div>
  );
}

export function HistoryPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const records = useHistoryStore((s) => s.records);
  const clear = useHistoryStore((s) => s.clear);
  const [filterType, setFilterType] = useState<string | null>(null);

  const filtered = filterType ? records.filter((r) => r.type === filterType) : records;
  const types = [...new Set(records.map((r) => r.type))];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          className="fixed bottom-8 right-4 z-50 w-80 max-h-[60vh] bg-bg-panel border border-border rounded-lg shadow-2xl flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-border/50 shrink-0">
            <div className="flex items-center gap-1.5">
              <History size={13} className="text-accent" />
              <span className="text-xs font-semibold text-text-primary">操作历史</span>
              <span className="text-[11px] text-text-muted/50 ml-1">{records.length} 条</span>
            </div>
            <div className="flex items-center gap-1">
              {records.length > 0 && (
                <button onClick={clear} className="p-1 rounded hover:bg-bg-hover text-text-muted/50 hover:text-danger" title="清空历史">
                  <Trash2 size={11} />
                </button>
              )}
              <button onClick={onClose} className="p-1 rounded hover:bg-bg-hover text-text-muted">
                <X size={13} />
              </button>
            </div>
          </div>

          {/* Type filter chips */}
          {types.length > 1 && (
            <div className="flex items-center gap-1 px-2 py-1.5 border-b border-border/30 overflow-x-auto shrink-0">
              <button
                onClick={() => setFilterType(null)}
                className={cn(
                  "px-1.5 py-0.5 rounded text-[11px] shrink-0 transition-colors",
                  !filterType ? "bg-accent/20 text-accent" : "text-text-muted hover:bg-bg-hover",
                )}
              >
                全部
              </button>
              {types.map((t) => (
                <button
                  key={t}
                  onClick={() => setFilterType(filterType === t ? null : t)}
                  className={cn(
                    "px-1.5 py-0.5 rounded text-[11px] shrink-0 transition-colors flex items-center gap-0.5",
                    filterType === t ? "bg-accent/20 text-accent" : "text-text-muted hover:bg-bg-hover",
                  )}
                >
                  {TYPE_ICON[t]}
                  {t}
                </button>
              ))}
            </div>
          )}

          {/* Records */}
          <div className="flex-1 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-8 text-text-muted/40">
                <History size={24} />
                <span className="text-xs">暂无操作记录</span>
              </div>
            ) : (
              <AnimatePresence mode="popLayout">
                {filtered.map((rec) => (
                  <RecordItem key={rec.id} rec={rec} />
                ))}
              </AnimatePresence>
            )}
          </div>

          {/* Footer with summary */}
          {records.length > 0 && (
            <div className="flex items-center justify-between px-3 py-1.5 border-t border-border/30 text-[11px] text-text-muted/40 shrink-0">
              <span>最早: {formatTime(records[records.length - 1].timestamp)}</span>
              <span>
                <ChevronDown size={9} className="inline" /> 持久化存储
              </span>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
