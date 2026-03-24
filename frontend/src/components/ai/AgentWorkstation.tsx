import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Cpu,
  Bot,
  Wrench,
  Play,
  CheckCircle2,
  XCircle,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { useState } from "react";
import { useAIStore, type AgentInfo } from "../../stores/aiStore";
import { useModelStore } from "../../stores/modelStore";
import {
  useAgentList,
  useAgentExecuteSingle,
  usePipelineList,
  useToolList,
} from "../../hooks/useAgentApi";
import { cn } from "../../lib/utils";

type TabId = "agents" | "pipelines" | "tools" | "history";

export function AgentWorkstation() {
  const { agentWorkstationOpen, toggleAgentWorkstation, executionResult, isExecuting } =
    useAIStore();
  const [tab, setTab] = useState<TabId>("agents");

  useAgentList(agentWorkstationOpen);

  return (
    <AnimatePresence>
      {agentWorkstationOpen && (
        <motion.div
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="fixed inset-x-0 bottom-0 z-30 h-[420px] bg-bg-panel border-t border-border shadow-2xl flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center gap-3 px-4 h-10 border-b border-border shrink-0">
            <Cpu size={16} className="text-accent" />
            <span className="text-sm font-semibold">Agent 工作站</span>

            <div className="flex gap-0.5 ml-4">
              {(["agents", "pipelines", "tools", "history"] as TabId[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={cn(
                    "px-3 py-1 text-xs rounded transition-colors",
                    tab === t
                      ? "bg-accent/20 text-accent"
                      : "text-text-muted hover:text-text-primary hover:bg-bg-secondary",
                  )}
                >
                  {t === "agents" && "Agents"}
                  {t === "pipelines" && "流水线"}
                  {t === "tools" && "工具"}
                  {t === "history" && "执行记录"}
                </button>
              ))}
            </div>

            {isExecuting && (
              <div className="flex items-center gap-1 ml-auto mr-2 text-xs text-accent">
                <Loader2 size={12} className="animate-spin" />
                执行中
              </div>
            )}

            <button
              onClick={toggleAgentWorkstation}
              className="ml-auto p-1 rounded hover:bg-bg-secondary text-text-muted"
            >
              <X size={16} />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4">
            {tab === "agents" && <AgentsTab />}
            {tab === "pipelines" && <PipelinesTab />}
            {tab === "tools" && <ToolsTab />}
            {tab === "history" && <HistoryTab result={executionResult} />}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function AgentsTab() {
  const agents = useAIStore((s) => s.agents);
  const modelId = useModelStore((s) => s.modelId);
  const executeSingle = useAgentExecuteSingle();
  const [taskInput, setTaskInput] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const ROLE_ICONS: Record<string, string> = {
    master: "🎯", model: "📦", mold: "🔧",
    insert: "📌", sim: "🧪", creative: "🎨",
  };

  const handleExecute = () => {
    if (!selectedAgent || !taskInput.trim()) return;
    executeSingle.mutate({
      agent: selectedAgent,
      task: taskInput,
      model_id: modelId ?? undefined,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        {agents.map((a: AgentInfo) => (
          <motion.button
            key={a.role}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setSelectedAgent(a.role)}
            className={cn(
              "p-3 rounded-lg border text-left transition-colors",
              selectedAgent === a.role
                ? "border-accent bg-accent/10"
                : "border-border bg-bg-secondary hover:border-accent/50",
            )}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-base">{ROLE_ICONS[a.role] ?? "⚡"}</span>
              <span className="text-xs font-semibold text-text-primary">{a.name}</span>
            </div>
            <p className="text-[10px] text-text-muted leading-tight">{a.description}</p>
            <div className="mt-1.5 text-[9px] text-text-muted">
              {a.tools.length} 工具可用
            </div>
          </motion.button>
        ))}
      </div>

      {selectedAgent && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          className="flex gap-2"
        >
          <input
            value={taskInput}
            onChange={(e) => setTaskInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleExecute()}
            placeholder={`向 ${selectedAgent} 描述任务...`}
            className="flex-1 bg-bg-secondary rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:ring-1 focus:ring-accent"
          />
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleExecute}
            disabled={!taskInput.trim() || executeSingle.isPending}
            className="px-4 py-2 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover disabled:opacity-50 flex items-center gap-1"
          >
            {executeSingle.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Play size={14} />
            )}
            执行
          </motion.button>
        </motion.div>
      )}
    </div>
  );
}

function PipelinesTab() {
  const { data: pipelines, isLoading } = usePipelineList();

  if (isLoading) return <p className="text-xs text-text-muted">加载中...</p>;

  const PIPELINE_INFO: Record<string, { label: string; desc: string }> = {
    full_from_model: { label: "完整流程（已有模型）", desc: "加载→检查→修复→方向分析→模具→仿真" },
    full_from_text: { label: "从零开始", desc: "AI生成→检查→模具→仿真" },
    mold_only: { label: "仅模具设计", desc: "方向分析→分型面→壳体" },
    sim_only: { label: "仅仿真优化", desc: "浇注系统→仿真→优化" },
  };

  return (
    <div className="space-y-2">
      {pipelines &&
        Object.entries(pipelines).map(([key, steps]) => {
          const info = PIPELINE_INFO[key];
          return (
            <div
              key={key}
              className="p-3 rounded-lg border border-border bg-bg-secondary"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-text-primary">
                  {info?.label ?? key}
                </span>
                <span className="text-[10px] text-text-muted">
                  {(steps as unknown[]).length} 步骤
                </span>
              </div>
              <p className="text-[11px] text-text-muted mb-2">{info?.desc ?? ""}</p>
              <div className="flex flex-wrap items-center gap-1">
                {(steps as { agent: string; task: string }[]).map((s, i) => (
                  <span key={i} className="flex items-center gap-0.5">
                    <span className="px-2 py-0.5 rounded text-[10px] bg-bg-primary text-text-secondary">
                      {s.agent}
                    </span>
                    {i < (steps as unknown[]).length - 1 && (
                      <ChevronRight size={10} className="text-text-muted" />
                    )}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
    </div>
  );
}

function ToolsTab() {
  const [category, setCategory] = useState<string | undefined>(undefined);
  const { data, isLoading } = useToolList(category);

  return (
    <div className="space-y-3">
      {data?.categories && (
        <div className="flex gap-1 flex-wrap">
          <button
            onClick={() => setCategory(undefined)}
            className={cn(
              "px-2 py-0.5 rounded text-[10px] transition-colors",
              !category ? "bg-accent/20 text-accent" : "bg-bg-secondary text-text-muted hover:text-text-primary",
            )}
          >
            全部
          </button>
          {(data.categories as string[]).map((c: string) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={cn(
                "px-2 py-0.5 rounded text-[10px] transition-colors",
                category === c
                  ? "bg-accent/20 text-accent"
                  : "bg-bg-secondary text-text-muted hover:text-text-primary",
              )}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {isLoading && <p className="text-xs text-text-muted">加载中...</p>}

      <div className="grid grid-cols-2 gap-1.5">
        {data?.tools?.map((t: { name: string; description: string; category: string; requires_confirmation: boolean }) => (
          <div
            key={t.name}
            className="flex items-start gap-2 p-2 rounded border border-border bg-bg-secondary"
          >
            <Wrench size={12} className="text-text-muted mt-0.5 shrink-0" />
            <div>
              <p className="text-[11px] font-mono text-text-primary">{t.name}</p>
              <p className="text-[10px] text-text-muted leading-tight">{t.description}</p>
            </div>
          </div>
        ))}
      </div>
      {data?.total !== undefined && (
        <p className="text-[10px] text-text-muted">共 {data.total} 个工具</p>
      )}
    </div>
  );
}

function HistoryTab({ result }: { result: unknown }) {
  if (!result) {
    return (
      <div className="text-center text-text-muted text-xs py-8">
        <Bot size={24} className="mx-auto mb-2 opacity-30" />
        <p>暂无执行记录</p>
      </div>
    );
  }

  const r = result as Record<string, unknown>;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        {r.success ? (
          <CheckCircle2 size={14} className="text-green-400" />
        ) : (
          <XCircle size={14} className="text-red-400" />
        )}
        <span className="text-sm font-semibold text-text-primary">
          {(r.step_name as string) ?? "执行结果"}
        </span>
      </div>

      <pre className="text-[11px] text-text-secondary bg-bg-secondary p-3 rounded-lg overflow-auto max-h-[280px] font-mono">
        {JSON.stringify(r, null, 2)}
      </pre>
    </div>
  );
}
