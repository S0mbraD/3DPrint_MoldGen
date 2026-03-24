import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface MeshInfo {
  vertex_count: number;
  face_count: number;
  bounds_min: number[];
  bounds_max: number[];
  extents: number[];
  center: number[];
  is_watertight: boolean;
  volume: number | null;
  surface_area: number;
  unit: string;
  source_format: string;
}

interface UploadResult {
  model_id: string;
  filename: string;
  format: string;
  size_mb: number;
  mesh_info: MeshInfo;
}

interface QualityReport {
  is_watertight: boolean;
  is_manifold: boolean;
  face_count: number;
  vertex_count: number;
  holes: number;
  degenerate_faces: number;
  duplicate_faces: number;
  min_edge_length: number;
  max_edge_length: number;
  mean_edge_length: number;
  max_aspect_ratio: number;
  volume: number | null;
  surface_area: number;
}

export function useUploadModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File): Promise<UploadResult> => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/v1/models/upload", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useModelInfo(modelId: string | null) {
  return useQuery<{ model_id: string; mesh_info: MeshInfo }>({
    queryKey: ["model-info", modelId],
    queryFn: async () => {
      const res = await fetch(`/api/v1/models/${modelId}`);
      if (!res.ok) throw new Error("Failed to fetch model info");
      return res.json();
    },
    enabled: !!modelId,
  });
}

export function useModelQuality(modelId: string | null) {
  return useQuery<{ model_id: string; quality: QualityReport }>({
    queryKey: ["model-quality", modelId],
    queryFn: async () => {
      const res = await fetch(`/api/v1/models/${modelId}/quality`);
      if (!res.ok) throw new Error("Failed to fetch quality report");
      return res.json();
    },
    enabled: !!modelId,
  });
}

export function useRepairModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (modelId: string) => {
      const res = await fetch(`/api/v1/models/${modelId}/repair`, { method: "POST" });
      if (!res.ok) throw new Error("Repair failed");
      return res.json();
    },
    onSuccess: (_data, modelId) => {
      queryClient.invalidateQueries({ queryKey: ["model-info", modelId] });
      queryClient.invalidateQueries({ queryKey: ["model-quality", modelId] });
    },
  });
}

export function useSimplifyModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ modelId, targetFaces, ratio }: { modelId: string; targetFaces?: number; ratio?: number }) => {
      const res = await fetch(`/api/v1/models/${modelId}/simplify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_faces: targetFaces, ratio }),
      });
      if (!res.ok) throw new Error("Simplify failed");
      return res.json();
    },
    onSuccess: (_data, { modelId }) => {
      queryClient.invalidateQueries({ queryKey: ["model-info", modelId] });
      queryClient.invalidateQueries({ queryKey: ["model-glb", modelId] });
    },
  });
}

export function useSubdivideModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ modelId, iterations, maxEdge }: { modelId: string; iterations?: number; maxEdge?: number }) => {
      const res = await fetch(`/api/v1/models/${modelId}/subdivide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ iterations, max_edge: maxEdge }),
      });
      if (!res.ok) throw new Error("Subdivide failed");
      return res.json();
    },
    onSuccess: (_data, { modelId }) => {
      queryClient.invalidateQueries({ queryKey: ["model-info", modelId] });
      queryClient.invalidateQueries({ queryKey: ["model-glb", modelId] });
    },
  });
}

export function useTransformModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ modelId, ...params }: { modelId: string; operation: string; [key: string]: unknown }) => {
      const res = await fetch(`/api/v1/models/${modelId}/transform`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) throw new Error("Transform failed");
      return res.json();
    },
    onSuccess: (_data, { modelId }) => {
      queryClient.invalidateQueries({ queryKey: ["model-info", modelId] });
      queryClient.invalidateQueries({ queryKey: ["model-glb", modelId] });
    },
  });
}
