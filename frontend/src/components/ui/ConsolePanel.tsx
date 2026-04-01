import { useEffect, useRef, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X, RefreshCw, AlertTriangle, Trash2, Server, Monitor,
  ChevronDown, ChevronRight, Clock, Search,
} from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { useLogStore, type LogEntry, type LogLevel } from "../../stores/logStore";
import { cn } from "../../lib/utils";

const API = "/api/v1/system";

type TabId = "frontend" | "backend" | "errors";

const LEVEL_STYLE: Record<LogLevel, { color: string; bg: string; label: string }> = {
  debug: { color: "text-gray-400", bg: "bg-gray-500/10", label: "DBG" },
  info: { color: "text-blue-300", bg: "bg-blue-500/10", label: "INF" },
  success: { color: "text-green-400", bg: "bg-green-500/10", label: "OK" },
  warn: { color: "text-yellow-400", bg: "bg-yellow-500/10", label: "WRN" },
  error: { color: "text-red-400", bg: "bg-red-500/10", label: "ERR" },
};

function formatTs(ts: number) {
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function FrontendLogLine({ entry }: { entry: LogEntry }) {
  const style = LEVEL_STYLE[entry.level];
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn("group px-1.5 py-0.5 hover:bg-white/[0.03] rounded-sm transition-colors", expanded && "bg-white/[0.02]")}
    >
      <div className="flex items-start gap-1.5 min-w-0">
        <span className="text-text-muted/40 shrink-0 tabular-nums w-[52px] text-right">{formatTs(entry.timestamp)}</span>
        <span className={cn("shrink-0 w-6 text-center rounded text-[8px] font-bold leading-4", style.color, style.bg)}>
          {style.label}
        </span>
        <span className="text-accent/60 shrink-0 text-[9px] font-medium min-w-[48px]">[{entry.source}]</span>
        <span className={cn("flex-1 min-w-0 break-words", style.color)}>{entry.message}</span>
        {entry.duration != null && (
          <span className="shrink-0 text-text-muted/30 flex items-center gap-0.5">
            <Clock size={8} />
            {entry.duration < 1000 ? `${entry.duration}ms` : `${(entry.duration / 1000).toFixed(1)}s`}
          </span>
        )}
        {entry.detail && (
          <button onClick={() => setExpanded(!expanded)} className="shrink-0 text-text-muted/30 hover:text-text-muted p-0.5">
            {expanded ? <ChevronDown size={9} /> : <ChevronRight size={9} />}
          </button>
        )}
      </div>
      {expanded && entry.detail && (
        <div className="ml-[85px] mt-0.5 text-text-muted/50 text-[9px] whitespace-pre-wrap break-all bg-black/20 rounded px-2 py-1">
          {entry.detail}
        </div>
      )}
    </div>
  );
}

function BackendLogLine({ line }: { line: string }) {
  const levelColor = (l: string) => {
    if (l.includes("| ERROR")) return "text-red-400";
    if (l.includes("| WARNING")) return "text-yellow-400";
    if (l.includes("| INFO")) return "text-blue-300";
    if (l.includes("| DEBUG")) return "text-gray-400";
    return "text-text-muted/60";
  };

  return (
    <div className={cn("whitespace-pre-wrap break-all px-1.5 py-[1px] hover:bg-white/[0.03] rounded-sm", levelColor(line))}>
      {line}
    </div>
  );
}

export function ConsolePanel() {
  const toggleConsole = useAppStore((s) => s.toggleConsole);
  const [tab, setTab] = useState<TabId>("frontend");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const frontendEntries = useLogStore((s) => s.entries);
  const clearFrontendLogs = useLogStore((s) => s.clear);

  const { data: backendLogs, refetch: refetchBackend } = useQuery<{ lines: string[] }>({
    queryKey: ["logs-all"],
    queryFn: () => fetch(`${API}/logs?n=300`).then((r) => r.json()),
    refetchInterval: 3000,
  });

  const { data: errLogs, refetch: refetchErr } = useQuery<{ lines: string[] }>({
    queryKey: ["logs-errors"],
    queryFn: () => fetch(`${API}/logs/errors?n=200`).then((r) => r.json()),
    refetchInterval: 5000,
  });

  const errorCount = (errLogs?.lines?.length ?? 0);
  const frontendErrorCount = frontendEntries.filter((e) => e.level === "error").length;

  const filteredFrontend = useMemo(() => {
    if (!searchQuery) return frontendEntries;
    const q = searchQuery.toLowerCase();
    return frontendEntries.filter(
      (e) => e.message.toLowerCase().includes(q) || e.source.toLowerCase().includes(q) || (e.detail?.toLowerCase().includes(q) ?? false),
    );
  }, [frontendEntries, searchQuery]);

  const filteredBackend = useMemo(() => {
    const lines = backendLogs?.lines ?? [];
    if (!searchQuery) return lines;
    const q = searchQuery.toLowerCase();
    return lines.filter((l) => l.toLowerCase().includes(q));
  }, [backendLogs, searchQuery]);

  const filteredErrors = useMemo(() => {
    const lines = errLogs?.lines ?? [];
    if (!searchQuery) return lines;
    const q = searchQuery.toLowerCase();
    return lines.filter((l) => l.toLowerCase().includes(q));
  }, [errLogs, searchQuery]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [frontendEntries.length, backendLogs?.lines?.length]);

  return (
    <div className="h-52 border-t border-border bg-[#12121e] flex flex-col shrink-0">
      {/* Header */}
      <div className="flex items-center h-7 px-2 bg-bg-secondary/80 border-b border-border/50 text-[10px] gap-1 shrink-0">
        <span className="font-bold text-text-primary mr-1">控制台</span>

        {/* Tabs */}
        <button
          onClick={() => setTab("frontend")}
          className={cn("px-1.5 py-0.5 rounded flex items-center gap-1",
            tab === "frontend" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-primary")}
        >
          <Monitor size={9} /> 前端
          {frontendEntries.length > 0 && (
            <span className="text-[8px] text-text-muted/50">{frontendEntries.length}</span>
          )}
        </button>
        <button
          onClick={() => setTab("backend")}
          className={cn("px-1.5 py-0.5 rounded flex items-center gap-1",
            tab === "backend" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-primary")}
        >
          <Server size={9} /> 后端
        </button>
        <button
          onClick={() => setTab("errors")}
          className={cn("px-1.5 py-0.5 rounded flex items-center gap-1",
            tab === "errors" ? "bg-red-500/20 text-red-400" : "text-text-muted hover:text-text-primary")}
        >
          <AlertTriangle size={9} /> 错误
          {(errorCount + frontendErrorCount) > 0 && (
            <span className="bg-red-500/30 text-red-300 px-1 rounded-full text-[8px]">
              {errorCount + frontendErrorCount}
            </span>
          )}
        </button>

        <div className="flex-1" />

        {/* Search */}
        {searchOpen ? (
          <div className="flex items-center gap-1 bg-bg-primary/60 rounded px-1.5 py-0.5 border border-border/40">
            <Search size={9} className="text-text-muted/40" />
            <input
              autoFocus
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && (setSearchOpen(false), setSearchQuery(""))}
              placeholder="搜索日志..."
              className="bg-transparent text-[10px] text-text-primary outline-none w-28 placeholder:text-text-muted/30"
            />
            <button onClick={() => { setSearchOpen(false); setSearchQuery(""); }} className="text-text-muted/40 hover:text-text-muted">
              <X size={8} />
            </button>
          </div>
        ) : (
          <button onClick={() => setSearchOpen(true)} className="p-0.5 rounded hover:bg-bg-hover text-text-muted/50" title="搜索 (Ctrl+F)">
            <Search size={10} />
          </button>
        )}

        <button
          onClick={() => { refetchBackend(); refetchErr(); }}
          className="p-0.5 rounded hover:bg-bg-hover text-text-muted/50" title="刷新后端日志"
        >
          <RefreshCw size={10} />
        </button>
        <button
          onClick={() => { clearFrontendLogs(); }}
          className="p-0.5 rounded hover:bg-bg-hover text-text-muted/50" title="清空前端日志"
        >
          <Trash2 size={10} />
        </button>
        <button onClick={toggleConsole} className="p-0.5 rounded hover:bg-bg-hover text-text-muted/50">
          <X size={10} />
        </button>
      </div>

      {/* Log Content */}
      <div className="flex-1 overflow-y-auto py-1 font-mono text-[10px] leading-[14px]">
        {tab === "frontend" && (
          filteredFrontend.length === 0 ? (
            <div className="text-text-muted/30 italic py-4 text-center">
              {searchQuery ? "无匹配日志" : "前端操作日志将在此显示"}
            </div>
          ) : (
            [...filteredFrontend].reverse().map((entry) => (
              <FrontendLogLine key={entry.id} entry={entry} />
            ))
          )
        )}

        {tab === "backend" && (
          filteredBackend.length === 0 ? (
            <div className="text-text-muted/30 italic py-4 text-center">
              {searchQuery ? "无匹配日志" : "后端日志拉取中..."}
            </div>
          ) : (
            filteredBackend.map((line, i) => <BackendLogLine key={i} line={line} />)
          )
        )}

        {tab === "errors" && (
          <>
            {/* Frontend errors */}
            {frontendEntries.filter((e) => e.level === "error").map((entry) => (
              <FrontendLogLine key={entry.id} entry={entry} />
            ))}
            {/* Backend errors */}
            {filteredErrors.length === 0 && frontendErrorCount === 0 ? (
              <div className="text-text-muted/30 italic py-4 text-center flex flex-col items-center gap-1">
                <AlertTriangle size={16} className="text-text-muted/20" />
                <span>{searchQuery ? "无匹配错误" : "暂无错误 — 一切正常"}</span>
              </div>
            ) : (
              filteredErrors.map((line, i) => <BackendLogLine key={`be-${i}`} line={line} />)
            )}
          </>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
