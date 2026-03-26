import { create } from "zustand";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
}

export interface AgentConfigData {
  enabled: boolean;
  default_mode: string;
  thinking_style: string;
  max_retries: number;
  retry_delay: number;
  auto_confirm_threshold: number;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  enable_memory: boolean;
  enable_self_reflection: boolean;
  verbose_logging: boolean;
}

export interface AgentInfo {
  role: string;
  name: string;
  description: string;
  tools: string[];
  config?: AgentConfigData;
}

export interface AgentStepResult {
  step_name: string;
  success: boolean;
  output: unknown;
  tool_calls: unknown[];
  thinking?: string;
  events?: AgentEventData[];
  elapsed_seconds?: number;
  error?: string;
}

export interface AgentEventData {
  event_type: string;
  agent_role: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export interface ExecutionHistoryItem {
  task: string;
  step_name: string;
  success: boolean;
  elapsed: number;
  timestamp: number;
}

export interface GlobalAgentConfig {
  default_mode: string;
  thinking_style: string;
  enable_memory: boolean;
  enable_self_reflection: boolean;
  max_retries: number;
  auto_confirm_threshold: number;
}

export interface MemoryStatus {
  short_term: { entries: Record<string, unknown>; summary: string; size: number };
  long_term: {
    user_defaults: Record<string, unknown>;
    frequent_organs: string[];
    preferred_materials: string[];
    n_successful_configs: number;
    agent_preferences: Record<string, unknown>;
  };
}

interface AIState {
  chatOpen: boolean;
  toggleChat: () => void;

  messages: ChatMessage[];
  addMessage: (msg: Omit<ChatMessage, "id" | "timestamp">) => void;
  clearMessages: () => void;

  isGenerating: boolean;
  setGenerating: (v: boolean) => void;

  agentWorkstationOpen: boolean;
  toggleAgentWorkstation: () => void;

  agents: AgentInfo[];
  setAgents: (agents: AgentInfo[]) => void;

  executionResult: AgentStepResult | null;
  setExecutionResult: (r: AgentStepResult | null) => void;

  isExecuting: boolean;
  setExecuting: (v: boolean) => void;

  executionHistory: ExecutionHistoryItem[];
  setExecutionHistory: (h: ExecutionHistoryItem[]) => void;
  addHistoryItem: (item: ExecutionHistoryItem) => void;

  globalConfig: GlobalAgentConfig | null;
  setGlobalConfig: (c: GlobalAgentConfig) => void;

  memoryStatus: MemoryStatus | null;
  setMemoryStatus: (m: MemoryStatus) => void;

  liveEvents: AgentEventData[];
  addLiveEvent: (e: AgentEventData) => void;
  clearLiveEvents: () => void;
}

export const useAIStore = create<AIState>((set) => ({
  chatOpen: false,
  toggleChat: () => set((s) => ({ chatOpen: !s.chatOpen })),

  messages: [],
  addMessage: (msg) =>
    set((s) => ({
      messages: [
        ...s.messages,
        { ...msg, id: crypto.randomUUID(), timestamp: Date.now() },
      ],
    })),
  clearMessages: () => set({ messages: [] }),

  isGenerating: false,
  setGenerating: (v) => set({ isGenerating: v }),

  agentWorkstationOpen: false,
  toggleAgentWorkstation: () =>
    set((s) => ({ agentWorkstationOpen: !s.agentWorkstationOpen })),

  agents: [],
  setAgents: (agents) => set({ agents }),

  executionResult: null,
  setExecutionResult: (r) => set({ executionResult: r }),

  isExecuting: false,
  setExecuting: (v) => set({ isExecuting: v }),

  executionHistory: [],
  setExecutionHistory: (h) => set({ executionHistory: h }),
  addHistoryItem: (item) =>
    set((s) => ({
      executionHistory: [...s.executionHistory.slice(-99), item],
    })),

  globalConfig: null,
  setGlobalConfig: (c) => set({ globalConfig: c }),

  memoryStatus: null,
  setMemoryStatus: (m) => set({ memoryStatus: m }),

  liveEvents: [],
  addLiveEvent: (e) =>
    set((s) => ({ liveEvents: [...s.liveEvents.slice(-49), e] })),
  clearLiveEvents: () => set({ liveEvents: [] }),
}));
