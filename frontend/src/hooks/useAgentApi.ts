import { useMutation, useQuery } from "@tanstack/react-query";
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
  const { setExecuting, setExecutionResult, addMessage } = useAIStore();
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
    },
    onError: () => {
      setExecuting(false);
    },
  });
}

export function useAgentExecuteSingle() {
  const { setExecuting, setExecutionResult } = useAIStore();
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
