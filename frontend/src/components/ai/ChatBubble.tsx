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
import { useState, useRef, useEffect, useCallback } from "react";
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

const BUBBLE_SIZE = 56;
const SNAP_THRESHOLD = 40;
const EDGE_PEEK = 16;

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

  const [pos, setPos] = useState({ x: -1, y: -1 });
  const [docked, setDocked] = useState<"none" | "right" | "left" | "bottom">("none");
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<HTMLDivElement>(null);
  const dragStartPos = useRef({ x: 0, y: 0 });
  const wasDragged = useRef(false);

  useEffect(() => {
    if (pos.x < 0) {
      setPos({
        x: window.innerWidth - BUBBLE_SIZE - 24,
        y: window.innerHeight - BUBBLE_SIZE - 24,
      });
    }
  }, [pos.x]);

  useEffect(() => {
    const onResize = () => {
      setPos((p) => ({
        x: Math.min(p.x, window.innerWidth - BUBBLE_SIZE),
        y: Math.min(p.y, window.innerHeight - BUBBLE_SIZE),
      }));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setIsDragging(true);
    wasDragged.current = false;
    dragStartPos.current = { x: e.clientX, y: e.clientY };

    const el = dragRef.current;
    if (el) el.setPointerCapture(e.pointerId);
  }, []);

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging) return;

      const dx = e.clientX - dragStartPos.current.x;
      const dy = e.clientY - dragStartPos.current.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) wasDragged.current = true;

      const rawX = e.clientX - BUBBLE_SIZE / 2;
      const rawY = e.clientY - BUBBLE_SIZE / 2;
      const clampedX = Math.max(0, Math.min(rawX, window.innerWidth - BUBBLE_SIZE));
      const clampedY = Math.max(0, Math.min(rawY, window.innerHeight - BUBBLE_SIZE));

      setPos({ x: clampedX, y: clampedY });
      setDocked("none");
    },
    [isDragging],
  );

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging) return;
      setIsDragging(false);

      const el = dragRef.current;
      if (el) el.releasePointerCapture(e.pointerId);

      const x = pos.x;
      const y = pos.y;
      const ww = window.innerWidth;
      const wh = window.innerHeight;

      if (x < SNAP_THRESHOLD) {
        setPos((p) => ({ ...p, x: -(BUBBLE_SIZE - EDGE_PEEK) }));
        setDocked("left");
      } else if (x > ww - BUBBLE_SIZE - SNAP_THRESHOLD) {
        setPos((p) => ({ ...p, x: ww - EDGE_PEEK }));
        setDocked("right");
      } else if (y > wh - BUBBLE_SIZE - SNAP_THRESHOLD) {
        setPos((p) => ({ ...p, y: wh - EDGE_PEEK }));
        setDocked("bottom");
      }
    },
    [isDragging, pos],
  );

  const handleBubbleClick = useCallback(() => {
    if (wasDragged.current) return;

    if (docked !== "none") {
      const ww = window.innerWidth;
      const wh = window.innerHeight;
      if (docked === "right") setPos((p) => ({ ...p, x: ww - BUBBLE_SIZE - 24 }));
      if (docked === "left") setPos((p) => ({ ...p, x: 24 }));
      if (docked === "bottom") setPos((p) => ({ ...p, y: wh - BUBBLE_SIZE - 24 }));
      setDocked("none");
      return;
    }

    toggleChat();
  }, [docked, toggleChat]);

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

  const bubbleStyle: React.CSSProperties = {
    position: "fixed",
    left: pos.x,
    top: pos.y,
    zIndex: 50,
    width: BUBBLE_SIZE,
    height: BUBBLE_SIZE,
    touchAction: "none",
    cursor: isDragging ? "grabbing" : "grab",
    transition: isDragging ? "none" : "left 0.3s ease, top 0.3s ease",
  };

  const isHidden = docked !== "none";

  return (
    <>
      {/* Draggable bubble */}
      <div
        ref={dragRef}
        style={bubbleStyle}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <motion.div
          onClick={handleBubbleClick}
          className={cn(
            "w-full h-full rounded-full",
            "bg-accent shadow-lg shadow-accent/25 flex items-center justify-center",
            "hover:bg-accent-hover transition-colors select-none",
          )}
          animate={
            isExecuting
              ? {
                  rotate: [0, 360],
                  transition: { duration: 2, repeat: Infinity, ease: "linear" },
                }
              : isHidden
                ? {}
                : {
                    scale: [1, 1.04, 1],
                    transition: { duration: 2, repeat: Infinity },
                  }
          }
          style={{
            opacity: isHidden ? 0.7 : 1,
            borderRadius: isHidden
              ? docked === "right"
                ? "50% 0 0 50%"
                : docked === "left"
                  ? "0 50% 50% 0"
                  : "50% 50% 0 0"
              : "50%",
          }}
        >
          {chatOpen && !isHidden ? (
            <X size={22} color="white" />
          ) : (
            <MessageCircle size={22} color="white" />
          )}
        </motion.div>
      </div>

      {/* Chat panel */}
      <AnimatePresence>
        {chatOpen && !isHidden && (
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
