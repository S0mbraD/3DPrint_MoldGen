import { useMutation } from "@tanstack/react-query";

const API = "/api/v1/analysis";

async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export interface ThicknessData {
  min: number;
  max: number;
  mean: number;
  std: number;
  thin_count: number;
  n_vertices: number;
  histogram_bins: number[];
  histogram_counts: number[];
  values: number[];
}

export interface CurvatureData {
  n_vertices: number;
  gaussian_min: number;
  gaussian_max: number;
  mean_curvature_min: number;
  mean_curvature_max: number;
  max_curvature_mean: number;
  gaussian: number[];
  mean: number[];
  max_abs: number[];
}

export interface DraftData {
  n_faces: number;
  min_draft: number;
  max_draft: number;
  mean_draft: number;
  undercut_fraction: number;
  critical_fraction: number;
  histogram_bins: number[];
  histogram_counts: number[];
  per_face: number[];
}

export interface SymmetryData {
  x_symmetry: number;
  y_symmetry: number;
  z_symmetry: number;
  best_plane: string;
  best_score: number;
  principal_axes: number[][];
}

export interface OverhangData {
  n_faces: number;
  overhang_fraction: number;
  overhang_area_mm2: number;
  total_area_mm2: number;
  critical_angle_deg: number;
  per_face: number[];
}

export function useThicknessAnalysis() {
  return useMutation({
    mutationFn: async ({
      modelId,
      nRays = 6,
      maxDistance = 50,
      thinThreshold = 1.0,
    }: {
      modelId: string;
      nRays?: number;
      maxDistance?: number;
      thinThreshold?: number;
    }) => {
      const data = await postJson<{ model_id: string; thickness: ThicknessData }>(
        `${API}/${modelId}/thickness`,
        { n_rays: nRays, max_distance: maxDistance, thin_threshold: thinThreshold },
      );
      return data.thickness;
    },
  });
}

export function useCurvatureAnalysis() {
  return useMutation({
    mutationFn: async (modelId: string) => {
      const data = await postJson<{ model_id: string; curvature: CurvatureData }>(
        `${API}/${modelId}/curvature`,
      );
      return data.curvature;
    },
  });
}

export function useDraftAnalysis() {
  return useMutation({
    mutationFn: async ({
      modelId,
      pullDirection,
      criticalAngle = 3,
    }: {
      modelId: string;
      pullDirection?: number[];
      criticalAngle?: number;
    }) => {
      const data = await postJson<{ model_id: string; draft: DraftData }>(
        `${API}/${modelId}/draft`,
        { pull_direction: pullDirection, critical_angle: criticalAngle },
      );
      return data.draft;
    },
  });
}

export function useSymmetryAnalysis() {
  return useMutation({
    mutationFn: async (modelId: string) => {
      const data = await postJson<{ model_id: string; symmetry: SymmetryData }>(
        `${API}/${modelId}/symmetry`,
      );
      return data.symmetry;
    },
  });
}

export function useOverhangAnalysis() {
  return useMutation({
    mutationFn: async ({
      modelId,
      buildDirection,
      criticalAngle = 45,
    }: {
      modelId: string;
      buildDirection?: number[];
      criticalAngle?: number;
    }) => {
      const data = await postJson<{ model_id: string; overhang: OverhangData }>(
        `${API}/${modelId}/overhang`,
        { build_direction: buildDirection, critical_angle: criticalAngle },
      );
      return data.overhang;
    },
  });
}

export function useSmoothMesh() {
  return useMutation({
    mutationFn: async ({
      modelId,
      method = "laplacian",
      iterations = 3,
    }: {
      modelId: string;
      method?: string;
      iterations?: number;
    }) => {
      const data = await postJson<{ model_id: string; mesh_info: unknown }>(
        `${API}/${modelId}/smooth`,
        { method, iterations },
      );
      return data;
    },
  });
}

export function useRemeshMesh() {
  return useMutation({
    mutationFn: async ({
      modelId,
      targetEdgeLength,
    }: {
      modelId: string;
      targetEdgeLength?: number;
    }) => {
      const data = await postJson<{ model_id: string; mesh_info: unknown }>(
        `${API}/${modelId}/remesh`,
        { target_edge_length: targetEdgeLength },
      );
      return data;
    },
  });
}

export function useThickenMesh() {
  return useMutation({
    mutationFn: async ({
      modelId,
      thickness = 2.0,
      direction = "both",
    }: {
      modelId: string;
      thickness?: number;
      direction?: string;
    }) => {
      const data = await postJson<{ model_id: string; mesh_info: unknown }>(
        `${API}/${modelId}/thicken`,
        { thickness, direction },
      );
      return data;
    },
  });
}

export function useOffsetMesh() {
  return useMutation({
    mutationFn: async ({
      modelId,
      distance = 1.0,
    }: {
      modelId: string;
      distance?: number;
    }) => {
      const data = await postJson<{ model_id: string; mesh_info: unknown }>(
        `${API}/${modelId}/offset`,
        { distance },
      );
      return data;
    },
  });
}
