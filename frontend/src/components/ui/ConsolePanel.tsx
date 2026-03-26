import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, RefreshCw, AlertTriangle } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

const API = "http://127.0.0.1:8000/api/v1/system";

type TabId = "all" | "errors";

export function ConsolePanel() {
  const toggleConsole = useAppStore((s) => s.toggleConsole);
  const [tab, setTab] = useState<TabId>("all");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: allLogs, refetch: refetchAll } = useQuery<{ lines: string[] }>({
    queryKey: ["logs-all"],
    queryFn: () => fetch(`${API}/logs?n=300`).then((r) => r.json()),
    refetchInterval: 3000,
  });

  const { data: errLogs, refetch: refetchErr } = useQuery<{ lines: string[] }>({
    queryKey: ["logs-errors"],
    queryFn: () => fetch(`${API}/logs/errors?n=200`).then((r) => r.json()),
    refetchInterval: 5000,
  });

  const lines = tab === "all" ? allLogs?.lines ?? [] : errLogs?.lines ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines.length]);

  const levelColor = (line: string) => {
    if (line.includes("| ERROR")) return "text-red-400";
    if (line.includes("| WARNING")) return "text-yellow-400";
    if (line.includes("| INFO")) return "text-blue-300";
    return "text-text-muted";
  };

  return (
    <div className="h-48 border-t border-border bg-[#1a1a2e] flex flex-col shrink-0">
      {/* Header */}
      <div className="flex items-center h-7 px-2 bg-bg-secondary border-b border-border/50 text-[10px] gap-2 shrink-0">
        <span className="font-bold text-text-primary">控制台</span>
        <button
          onClick={() => setTab("all")}
          className={`px-1.5 py-0.5 rounded ${tab === "all" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-primary"}`}
        >
          全部
        </button>
        <button
          onClick={() => setTab("errors")}
          className={`px-1.5 py-0.5 rounded flex items-center gap-0.5 ${tab === "errors" ? "bg-red-500/20 text-red-400" : "text-text-muted hover:text-text-primary"}`}
        >
          <AlertTriangle size={10} /> 错误
          {(errLogs?.lines?.length ?? 0) > 0 && (
            <span className="ml-0.5 bg-red-500/30 text-red-300 px-1 rounded-full text-[8px]">
              {errLogs!.lines.length}
            </span>
          )}
        </button>
        <div className="flex-1" />
        <button
          onClick={() => { refetchAll(); refetchErr(); }}
          className="p-0.5 rounded hover:bg-bg-hover text-text-muted"
          title="刷新"
        >
          <RefreshCw size={10} />
        </button>
        <button
          onClick={toggleConsole}
          className="p-0.5 rounded hover:bg-bg-hover text-text-muted"
        >
          <X size={10} />
        </button>
      </div>

      {/* Log Content */}
      <div className="flex-1 overflow-y-auto px-2 py-1 font-mono text-[10px] leading-4">
        {lines.length === 0 ? (
          <div className="text-text-muted italic py-2">暂无日志</div>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={`whitespace-pre-wrap break-all ${levelColor(line)}`}>
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
