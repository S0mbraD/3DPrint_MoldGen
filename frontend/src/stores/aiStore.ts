import { create } from "zustand";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
}

export interface AgentInfo {
  role: string;
  name: string;
  description: string;
  tools: string[];
}

export interface AgentStepResult {
  step_name: string;
  success: boolean;
  output: unknown;
  tool_calls: unknown[];
  error?: string;
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
}));
