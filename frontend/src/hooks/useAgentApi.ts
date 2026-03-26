import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAIStore } from "../stores/aiStore";

const API = "/api/v1/ai/agent";

export function useAgentList(enabled = true) {
  const setAgents = useAIStore((s) => s.setAgents);
  return useQuery({
    queryKey: ["agents"],
    queryFn: async () => {
      try {
        const res = await fetch(`${API}/agents`);
        if (!res.ok) return [];
        const data = await res.json();
        const agents = data.agents ?? [];
        setAgents(agents);
        return agents;
      } catch {
        return [];
      }
    },
    staleTime: 60_000,
    retry: false,
    enabled,
  });
}

export function useAgentExecute() {
  const { setExecuting, setExecutionResult, addMessage, addHistoryItem } = useAIStore();
  return useMutation({
    mutationFn: async (params: {
      request: string;
      mode?: string;
      model_id?: string;
      mold_id?: string;
    }) => {
      setExecuting(true);
      const res = await fetch(`${API}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      return res.json();
    },
    onSuccess: (data) => {
      setExecuting(false);
      setExecutionResult(data);
      if (data.output?.message) {
        addMessage({ role: "assistant", content: data.output.message });
      }
      addHistoryItem({
        task: data.step_name ?? "execute",
        step_name: data.step_name ?? "",
        success: data.success,
        elapsed: data.elapsed_seconds ?? 0,
        timestamp: Date.now() / 1000,
      });
    },
    onError: () => {
      setExecuting(false);
    },
  });
}

export function useAgentExecuteSingle() {
  const { setExecuting, setExecutionResult, addHistoryItem } = useAIStore();
  return useMutation({
    mutationFn: async (params: {
      agent: string;
      task: string;
      model_id?: string;
      mold_id?: string;
    }) => {
      setExecuting(true);
      const res = await fetch(`${API}/execute/single`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      return res.json();
    },
    onSuccess: (data) => {
      setExecuting(false);
      setExecutionResult(data);
      addHistoryItem({
        task: data.step_name ?? "single",
        step_name: data.step_name ?? "",
        success: data.success,
        elapsed: data.elapsed_seconds ?? 0,
        timestamp: Date.now() / 1000,
      });
    },
    onError: () => {
      setExecuting(false);
    },
  });
}

export function useClassifyIntent() {
  return useMutation({
    mutationFn: async (task: string) => {
      const res = await fetch(`${API}/classify?task=${encodeURIComponent(task)}`);
      return res.json();
    },
  });
}

export function usePipelineList() {
  return useQuery({
    queryKey: ["pipelines"],
    queryFn: async () => {
      try {
        const res = await fetch(`${API}/pipelines`);
        if (!res.ok) return [];
        const data = await res.json();
        return data.pipelines ?? [];
      } catch {
        return [];
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useToolList(category?: string) {
  return useQuery({
    queryKey: ["tools", category],
    queryFn: async () => {
      try {
        const url = category ? `${API}/tools?category=${category}` : `${API}/tools`;
        const res = await fetch(url);
        if (!res.ok) return { categories: [], tools: [], total: 0 };
        return await res.json();
      } catch {
        return { categories: [], tools: [], total: 0 };
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

// ── Agent Config Hooks ───────────────────────────────────────────────

export function useGlobalAgentConfig() {
  const setGlobalConfig = useAIStore((s) => s.setGlobalConfig);
  return useQuery({
    queryKey: ["agent-global-config"],
    queryFn: async () => {
      try {
        const res = await fetch(`${API}/config`);
        if (!res.ok) return null;
        const data = await res.json();
        setGlobalConfig(data.config);
        return data.config;
      } catch {
        return null;
      }
    },
    staleTime: 30_000,
    retry: false,
  });
}

export function useUpdateGlobalConfig() {
  const qc = useQueryClient();
  const setGlobalConfig = useAIStore((s) => s.setGlobalConfig);
  return useMutation({
    mutationFn: async (updates: Record<string, unknown>) => {
      const res = await fetch(`${API}/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      return res.json();
    },
    onSuccess: (data) => {
      if (data.config) {
        setGlobalConfig(data.config);
        qc.invalidateQueries({ queryKey: ["agent-global-config"] });
        qc.invalidateQueries({ queryKey: ["agents"] });
      }
    },
  });
}

export function useUpdateAgentConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { role: string; updates: Record<string, unknown> }) => {
      const res = await fetch(`${API}/config/${params.role}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params.updates),
      });
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

// ── Memory Hooks ─────────────────────────────────────────────────────

export function useMemoryStatus() {
  const setMemoryStatus = useAIStore((s) => s.setMemoryStatus);
  return useQuery({
    queryKey: ["agent-memory"],
    queryFn: async () => {
      try {
        const res = await fetch(`${API}/memory`);
        if (!res.ok) return null;
        const data = await res.json();
        setMemoryStatus(data);
        return data;
      } catch {
        return null;
      }
    },
    staleTime: 15_000,
    retry: false,
  });
}

export function useClearShortTermMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API}/memory/short-term`, { method: "DELETE" });
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-memory"] });
    },
  });
}

export function useUsageStats() {
  return useQuery({
    queryKey: ["agent-usage-stats"],
    queryFn: async () => {
      try {
        const res = await fetch(`${API}/memory/usage-stats`);
        if (!res.ok) return {};
        const data = await res.json();
        return data.stats ?? {};
      } catch {
        return {};
      }
    },
    staleTime: 30_000,
    retry: false,
  });
}

export function useExecutionHistory() {
  const setExecutionHistory = useAIStore((s) => s.setExecutionHistory);
  return useQuery({
    queryKey: ["agent-history"],
    queryFn: async () => {
      try {
        const res = await fetch(`${API}/history`);
        if (!res.ok) return [];
        const data = await res.json();
        const history = data.history ?? [];
        setExecutionHistory(history);
        return history;
      } catch {
        return [];
      }
    },
    staleTime: 10_000,
    retry: false,
  });
}
