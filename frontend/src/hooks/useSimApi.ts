import { useMutation, useQuery } from "@tanstack/react-query";
import {
  useSimStore,
  type GatingResultInfo,
  type SimResultInfo,
  type OptimizationResultInfo,
  type VisualizationData,
  type CrossSectionData,
} from "../stores/simStore";
import { useMoldStore } from "../stores/moldStore";

const API = "/api/v1/simulation";

export function useMaterials() {
  return useQuery({
    queryKey: ["materials"],
    queryFn: async () => {
      const resp = await fetch(`${API}/materials`);
      if (!resp.ok) throw new Error(await resp.text());
      return (await resp.json()).materials as Record<string, Record<string, unknown>>;
    },
  });
}

export function useGatingDesign() {
  const store = useSimStore();

  return useMutation({
    mutationFn: async ({
      modelId,
      moldId,
      material,
      gateDiameter,
      nVents,
    }: {
      modelId: string;
      moldId: string;
      material?: string;
      gateDiameter?: number;
      nVents?: number;
    }) => {
      store.setDesigningGating(true);
      const body: Record<string, unknown> = {
        model_id: modelId,
        mold_id: moldId,
        material: material || store.selectedMaterial,
      };
      if (gateDiameter != null) body.gate_diameter = gateDiameter;
      if (nVents != null) body.n_vents = nVents;
      const resp = await fetch(`${API}/gating/design`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return { gatingId: data.gating_id as string, result: data.result as GatingResultInfo };
    },
    onSuccess: ({ gatingId, result }) => {
      store.setGatingResult(gatingId, result);
      useMoldStore.getState().bumpShellMeshRevision();
    },
    onError: () => store.setDesigningGating(false),
  });
}

export function useRunSimulation() {
  const store = useSimStore();

  return useMutation({
    mutationFn: async ({
      modelId,
      gatingId,
      material,
      level = 1,
    }: {
      modelId: string;
      gatingId: string;
      material?: string;
      level?: number;
    }) => {
      store.setSimulating(true);
      const resp = await fetch(`${API}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_id: modelId,
          gating_id: gatingId,
          material: material || store.selectedMaterial,
          level,
          voxel_resolution: level === 2 ? 48 : 32,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return { simId: data.sim_id as string, result: data.result as SimResultInfo };
    },
    onSuccess: ({ simId, result }) => store.setSimResult(simId, result),
    onError: () => store.setSimulating(false),
  });
}

export function useRunOptimization() {
  const store = useSimStore();

  return useMutation({
    mutationFn: async ({
      modelId,
      moldId,
      gatingId,
      material,
    }: {
      modelId: string;
      moldId: string;
      gatingId: string;
      material?: string;
    }) => {
      store.setOptimizing(true);
      const resp = await fetch(`${API}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_id: modelId,
          mold_id: moldId,
          gating_id: gatingId,
          material: material || store.selectedMaterial,
          max_iterations: 3,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      return (await resp.json()).result as OptimizationResultInfo;
    },
    onSuccess: (result) => {
      store.setOptimizationResult(result);
      useMoldStore.getState().bumpShellMeshRevision();
    },
    onError: () => store.setOptimizing(false),
  });
}

export function useFetchVisualization() {
  const store = useSimStore();

  return useMutation({
    mutationFn: async (simId: string) => {
      store.setLoadingVisualization(true);
      const resp = await fetch(`${API}/visualization/${simId}`);
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return data as VisualizationData;
    },
    onSuccess: (data) => {
      store.setVisualizationData(data);
      store.setHeatmapVisible(true);
      store.setAnimationProgress(0);
      store.setAnimationPlaying(true);
    },
    onError: () => store.setLoadingVisualization(false),
  });
}

export function useFetchAnalysis() {
  return useMutation({
    mutationFn: async (simId: string) => {
      const resp = await fetch(`${API}/analysis/${simId}`);
      if (!resp.ok) throw new Error(await resp.text());
      return await resp.json();
    },
  });
}

export function useFetchSurfaceMap() {
  const store = useSimStore();

  return useMutation({
    mutationFn: async ({
      simId,
      modelId,
      field,
    }: {
      simId: string;
      modelId: string;
      field: string;
    }) => {
      store.setSurfaceMapLoading(true);
      const params = new URLSearchParams({ model_id: modelId, field });
      const resp = await fetch(`${API}/surface-map/${simId}?${params}`);
      if (!resp.ok) throw new Error(await resp.text());
      return await resp.json();
    },
    onSuccess: (data) => store.setSurfaceMapData(data),
    onError: () => store.setSurfaceMapLoading(false),
  });
}

export interface FEAResultInfo {
  n_vertices: number;
  max_displacement_mm: number;
  max_stress_mpa: number;
  min_safety_factor: number;
  avg_stress_mpa: number;
  total_strain_energy: number;
}

export interface FEAVisualizationData {
  n_vertices: number;
  displacement_magnitude: number[];
  von_mises_stress: number[];
  safety_factor: number[];
  strain_energy: number[];
  max_displacement_mm: number;
  max_stress_mpa: number;
  min_safety_factor: number;
}

export function useRunFEA() {
  const store = useSimStore();

  return useMutation({
    mutationFn: async ({
      modelId,
      materialPreset,
      pressureLoad = 0.1,
    }: {
      modelId: string;
      materialPreset?: string;
      pressureLoad?: number;
    }) => {
      store.setFEARunning(true);
      const resp = await fetch(`${API}/fea/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_id: modelId,
          material_preset: materialPreset || "pla",
          pressure_load: pressureLoad,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return {
        feaId: data.fea_id as string,
        result: data.result as FEAResultInfo,
      };
    },
    onSuccess: ({ feaId, result }) => store.setFEAResult(feaId, result as unknown as Record<string, unknown>),
    onError: () => store.setFEARunning(false),
  });
}

export function useFetchFEAVisualization() {
  const store = useSimStore();

  return useMutation({
    mutationFn: async (feaId: string) => {
      const resp = await fetch(`${API}/fea/visualization/${feaId}`);
      if (!resp.ok) throw new Error(await resp.text());
      return (await resp.json()) as FEAVisualizationData;
    },
    onSuccess: (data) => store.setFEAVisualizationData(data as unknown as Record<string, unknown>),
  });
}

export function useFetchCrossSection() {
  const store = useSimStore();

  return useMutation({
    mutationFn: async ({
      simId,
      axis,
      position,
      field,
    }: {
      simId: string;
      axis: string;
      position: number;
      field: string;
    }) => {
      const params = new URLSearchParams({
        axis,
        position: position.toString(),
        field,
      });
      const resp = await fetch(`${API}/cross-section/${simId}?${params}`);
      if (!resp.ok) throw new Error(await resp.text());
      return (await resp.json()) as CrossSectionData;
    },
    onSuccess: (data) => store.setCrossSectionData(data),
  });
}
