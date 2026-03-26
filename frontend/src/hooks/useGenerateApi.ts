import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

const API = "/api/v1/ai/generate";

// ── Types ────────────────────────────────────────────────────────────

export interface LocalModelInfo {
  model_id: string;
  name: string;
  category: "image_gen" | "mesh_gen";
  description: string;
  vram_required_mb: number;
  disk_size_gb: number;
  status: string;
  tags: string[];
  hf_repo: string;
  download_progress: number;
  is_loaded: boolean;
}

export interface ModelRecommendation {
  tier: string;
  image_gen: string | null;
  mesh_gen: string | null;
  note: string;
}

export interface ProviderConfig {
  image_provider: string;
  image_local_model: string;
  mesh_provider: string;
  mesh_local_model: string;
  auto_unload_after_gen: boolean;
  cloud_status: { wanxiang: boolean; tripo3d: boolean };
}

export interface ImageGenResult {
  success: boolean;
  images: { id: string; url?: string; local_path?: string; index: number }[];
  provider: string;
  model: string;
  elapsed_seconds: number;
  prompt_used: string;
  error?: string;
}

export interface MeshGenResult {
  success: boolean;
  mesh_path: string;
  mesh_format: string;
  provider: string;
  model: string;
  elapsed_seconds: number;
  vertex_count: number;
  face_count: number;
  error?: string;
}

// ── Local Models ─────────────────────────────────────────────────────

export function useLocalModels(category?: string) {
  return useQuery({
    queryKey: ["local-models", category],
    queryFn: async () => {
      const url = category ? `${API}/local-models?category=${category}` : `${API}/local-models`;
      const res = await fetch(url);
      if (!res.ok) return { models: [], recommendation: null };
      return res.json() as Promise<{ models: LocalModelInfo[]; recommendation: ModelRecommendation }>;
    },
    staleTime: 10_000,
  });
}

export function useLocalModelVram() {
  return useQuery({
    queryKey: ["local-model-vram"],
    queryFn: async () => {
      const res = await fetch(`${API}/local-models/vram`);
      if (!res.ok) return null;
      return res.json();
    },
    staleTime: 5_000,
  });
}

export function useDownloadModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (modelId: string) => {
      const res = await fetch(`${API}/local-models/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["local-models"] });
    },
  });
}

export function useLoadModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (modelId: string) => {
      const res = await fetch(`${API}/local-models/${modelId}/load`, { method: "POST" });
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["local-models"] });
      qc.invalidateQueries({ queryKey: ["local-model-vram"] });
    },
  });
}

export function useUnloadModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (modelId: string) => {
      const res = await fetch(`${API}/local-models/${modelId}/unload`, { method: "POST" });
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["local-models"] });
      qc.invalidateQueries({ queryKey: ["local-model-vram"] });
    },
  });
}

export function useDeleteModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (modelId: string) => {
      const res = await fetch(`${API}/local-models/${modelId}`, { method: "DELETE" });
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["local-models"] });
    },
  });
}

// ── Providers ────────────────────────────────────────────────────────

export function useProviderConfig() {
  return useQuery({
    queryKey: ["provider-config"],
    queryFn: async () => {
      const res = await fetch(`${API}/providers`);
      if (!res.ok) return null;
      return res.json() as Promise<ProviderConfig>;
    },
    staleTime: 10_000,
  });
}

export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (updates: Partial<ProviderConfig>) => {
      const res = await fetch(`${API}/providers`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provider-config"] });
    },
  });
}

// ── Image Generation ─────────────────────────────────────────────────

export function useGenerateImage() {
  return useMutation({
    mutationFn: async (params: {
      prompt: string;
      negative_prompt?: string;
      num_images?: number;
      width?: number;
      height?: number;
      steps?: number;
      seed?: number;
      provider?: string;
      model_id?: string;
    }) => {
      const res = await fetch(`${API}/image/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      return res.json() as Promise<ImageGenResult>;
    },
  });
}

// ── 3D Mesh Generation ───────────────────────────────────────────────

export function useTextTo3D() {
  return useMutation({
    mutationFn: async (params: { prompt: string; provider?: string }) => {
      const res = await fetch(`${API}/mesh/text-to-3d`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      return res.json() as Promise<MeshGenResult>;
    },
  });
}

export function useImageTo3D() {
  return useMutation({
    mutationFn: async (params: {
      image_path: string;
      provider?: string;
      model_id?: string;
      mc_resolution?: number;
    }) => {
      const res = await fetch(`${API}/mesh/image-to-3d`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      return res.json() as Promise<MeshGenResult>;
    },
  });
}

// ── Prompt Optimization ──────────────────────────────────────────────

export function useOptimizePrompt() {
  return useMutation({
    mutationFn: async (prompt: string) => {
      const res = await fetch(`${API}/prompt/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      return res.json() as Promise<{ original: string; optimized: string }>;
    },
  });
}
