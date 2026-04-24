import { motion, AnimatePresence } from "framer-motion";
import {
  MessageCircle,
  X,
  Send,
  Bot,
  Cpu,
  Loader2,
  Trash2,
  FileBox,
  Sparkles,
  Wand2,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useAIStore } from "../../stores/aiStore";
import { useModelStore } from "../../stores/modelStore";
import { useAgentExecute } from "../../hooks/useAgentApi";
import { cn } from "../../lib/utils";

const SUGGESTIONS: Record<
  "modeling" | "mold" | "simulation" | "export",
  { label: string; items: string[] }
> = {
  modeling: {
    label: "建模",
    items: [
      "生成心脏教学模型",
      "简化网格并保留细节",
      "修复非流形边并检查水密",
      "根据教学主题推荐几何特征",
    ],
  },
  mold: {
    label: "模具",
    items: [
      "全自动模具设计",
      "分析脱模方向与倒扣",
      "优化分型线与拔模角",
      "生成上下模壳与浇口建议",
    ],
  },
  simulation: {
    label: "仿真",
    items: [
      "预测充填与气穴风险",
      "浇道布局与流道平衡",
      "运行一次快速充填仿真",
      "根据缺陷优化工艺参数",
    ],
  },
  export: {
    label: "导出",
    items: [
      "导出 STL 用于 FDM 打印",
      "打包模具壳体与模型 ZIP",
      "导出支撑板与装配验证",
      "推荐适合课堂展示的格式",
    ],
  },
};

const QUICK_ACTIONS: { label: string; prompt: string; icon: typeof Wand2 }[] = [
  { label: "智能建模", prompt: "根据当前模型给出建模与修复建议", icon: Wand2 },
  { label: "模具方案", prompt: "为当前模型规划脱模方向与模具步骤", icon: Sparkles },
  { label: "仿真检查", prompt: "分析浇道设计并建议是否需仿真", icon: Cpu },
  { label: "导出清单", prompt: "列出可导出资源与推荐文件格式", icon: FileBox },
];

function formatMessageTime(ts: number) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(ts));
  } catch {
    return "";
  }
}

export function ChatBubble() {
  const {
    chatOpen,
    toggleChat,
    messages,
    addMessage,
    clearMessages,
    isExecuting,
    toggleAgentWorkstation,
  } = useAIStore();
  const modelId = useModelStore((s) => s.modelId);
  const filename = useModelStore((s) => s.filename);
  const meshInfo = useModelStore((s) => s.meshInfo);
  const [input, setInput] = useState("");
  const messagesEnd = useRef<HTMLDivElement>(null);
  const agentExecute = useAgentExecute();

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    addMessage({ role: "user", content: text });
    setInput("");
    agentExecute.mutate({
      request: text,
      mode: "auto",
      model_id: modelId ?? undefined,
    });
  };

  const applySuggestion = (text: string) => {
    setInput(text);
  };

  return (
    <>
      <motion.button
        onClick={toggleChat}
        className={cn(
          "fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full",
          "bg-accent shadow-lg shadow-accent/25 flex items-center justify-center",
          "hover:bg-accent-hover transition-colors",
        )}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        animate={
          isExecuting
            ? {
                rotate: [0, 360],
                transition: { duration: 2, repeat: Infinity, ease: "linear" },
              }
            : {
                scale: [1, 1.04, 1],
                transition: { duration: 2, repeat: Infinity },
              }
        }
      >
        {chatOpen ? (
          <X size={22} color="white" />
        ) : (
          <MessageCircle size={22} color="white" />
        )}
      </motion.button>

      <AnimatePresence>
        {chatOpen && (
          <motion.div
            initial={{ x: 420, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 420, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed right-0 top-0 bottom-0 w-[400px] z-40 bg-bg-panel border-l border-border flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center gap-2 px-4 h-12 border-b border-border shrink-0">
              <Bot size={18} className="text-accent" />
              <span className="text-sm font-semibold">AI 助手</span>
              <div className="ml-auto flex items-center gap-1">
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={toggleAgentWorkstation}
                  className="p-1.5 rounded hover:bg-bg-secondary text-text-muted hover:text-accent"
                  title="Agent 工作站"
                >
                  <Cpu size={14} />
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={clearMessages}
                  className="p-1.5 rounded hover:bg-bg-secondary text-text-muted hover:text-red-400"
                  title="清空对话"
                >
                  <Trash2 size={14} />
                </motion.button>
              </div>
            </div>

            {/* Model context */}
            {modelId && (
              <div className="px-4 py-2 border-b border-border/80 bg-bg-secondary/40 shrink-0">
                <div className="flex items-center gap-2 text-[11px] text-text-secondary">
                  <FileBox size={14} className="text-accent shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-text-primary truncate">
                      已加载模型
                    </div>
                    <div className="truncate text-text-muted">
                      {filename ?? modelId}
                    </div>
                    {meshInfo && (
                      <div className="text-[12px] text-text-muted mt-0.5">
                        {meshInfo.face_count.toLocaleString()} 面 ·{" "}
                        {meshInfo.vertex_count.toLocaleString()} 顶点
                        {meshInfo.unit ? ` · ${meshInfo.unit}` : ""}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 && (
                <div className="space-y-4">
                  <div className="text-center text-text-muted text-xs py-2">
                    <Bot size={32} className="mx-auto mb-3 opacity-30" />
                    <p className="text-text-primary font-medium">
                      你好！我是 MoldGen AI 助手
                    </p>
                    <p className="mt-1 text-[11px]">
                      告诉我你想制作什么教具模型，或从下方快速开始。
                    </p>
                  </div>

                  <div className="rounded-lg border border-border/80 bg-bg-secondary/30 p-3">
                    <div className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-wider text-text-muted mb-2">
                      <Sparkles size={12} className="text-accent" />
                      快速操作
                    </div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {QUICK_ACTIONS.map((a) => {
                        const Icon = a.icon;
                        return (
                          <motion.button
                            key={a.label}
                            type="button"
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => applySuggestion(a.prompt)}
                            className="flex items-center gap-1.5 rounded-md border border-border/60 bg-bg-panel px-2 py-1.5 text-left text-[11px] text-text-secondary hover:border-accent/50 hover:text-accent transition-colors"
                          >
                            <Icon size={12} className="shrink-0 opacity-80" />
                            <span className="leading-tight">{a.label}</span>
                          </motion.button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="space-y-3">
                    {(Object.keys(SUGGESTIONS) as Array<keyof typeof SUGGESTIONS>).map(
                      (key) => {
                        const cat = SUGGESTIONS[key];
                        return (
                          <div key={key}>
                            <div className="text-[12px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">
                              {cat.label}
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {cat.items.map((text) => (
                                <SuggestionChip
                                  key={text}
                                  text={text}
                                  onClick={applySuggestion}
                                />
                              ))}
                            </div>
                          </div>
                        );
                      },
                    )}
                  </div>
                </div>
              )}
              {messages.map((msg) => (
                <motion.div
                  key={msg.id}
                  initial={{ y: 10, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  className={cn(
                    "max-w-[85%] flex flex-col gap-0.5",
                    msg.role === "user" ? "ml-auto items-end" : "items-start",
                  )}
                >
                  <div
                    className={cn(
                      "rounded-xl px-3 py-2 text-sm",
                      msg.role === "user"
                        ? "bg-accent/20 text-text-primary"
                        : "bg-bg-secondary text-text-primary",
                    )}
                  >
                    {msg.content}
                  </div>
                  <span className="text-[11px] text-text-muted/90 px-1 tabular-nums">
                    {formatMessageTime(msg.timestamp)}
                  </span>
                </motion.div>
              ))}
              {isExecuting && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center gap-2 text-xs text-text-muted"
                >
                  <Loader2 size={12} className="animate-spin" />
                  <span>Agent 执行中...</span>
                </motion.div>
              )}
              <div ref={messagesEnd} />
            </div>

            {/* Input */}
            <div className="px-3 py-3 border-t border-border shrink-0">
              <div className="flex gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                  placeholder="描述你的需求..."
                  disabled={isExecuting}
                  className="flex-1 bg-bg-secondary rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
                />
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={handleSend}
                  disabled={isExecuting}
                  className="p-2 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-50"
                >
                  {isExecuting ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Send size={16} />
                  )}
                </motion.button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function SuggestionChip({
  text,
  onClick,
}: {
  text: string;
  onClick: (t: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(text)}
      className="inline-block px-2.5 py-1 rounded-full text-[12px] leading-snug bg-bg-secondary text-text-secondary hover:bg-accent/20 hover:text-accent transition-colors text-left max-w-full"
    >
      {text}
    </button>
  );
}
