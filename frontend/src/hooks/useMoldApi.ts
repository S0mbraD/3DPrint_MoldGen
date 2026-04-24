import { useMutation } from "@tanstack/react-query";
import {
  useMoldStore,
  type OrientationResult,
  type PartingResult,
  type MoldResultInfo,
  type UndercutInfo,
  type UndercutHeatmapData,
} from "../stores/moldStore";

const API = "/api/v1/molds";

export function useOrientationAnalysis() {
  const store = useMoldStore();

  return useMutation({
    mutationFn: async ({
      modelId,
      nSamples = 100,
      nFinal = 5,
    }: {
      modelId: string;
      nSamples?: number;
      nFinal?: number;
    }) => {
      store.setAnalyzing(true);
      const resp = await fetch(`${API}/${modelId}/orientation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ n_samples: nSamples, n_final: nFinal }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return data.result as OrientationResult;
    },
    onSuccess: (result) => store.setOrientationResult(result),
    onError: () => store.setAnalyzing(false),
  });
}

export function useEvaluateDirection() {
  return useMutation({
    mutationFn: async ({
      modelId,
      direction,
    }: {
      modelId: string;
      direction: number[];
    }) => {
      const resp = await fetch(`${API}/${modelId}/orientation/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      return (await resp.json()).score;
    },
  });
}

export function usePartingGeneration() {
  const store = useMoldStore();

  return useMutation({
    mutationFn: async ({
      modelId,
      direction,
      surfaceType = "auto",
      heightfieldResolution = 40,
      undercutThreshold = 1.0,
    }: {
      modelId: string;
      direction?: number[];
      surfaceType?: string;
      heightfieldResolution?: number;
      undercutThreshold?: number;
    }) => {
      store.setGeneratingParting(true);
      const body: Record<string, unknown> = {
        surface_type: surfaceType,
        heightfield_resolution: heightfieldResolution,
        undercut_threshold: undercutThreshold,
      };
      if (direction) body.direction = direction;

      const resp = await fetch(`${API}/${modelId}/parting`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return data.result as PartingResult;
    },
    onSuccess: (result) => store.setPartingResult(result),
    onError: () => store.setGeneratingParting(false),
  });
}

export function useUndercutAnalysis() {
  return useMutation({
    mutationFn: async ({
      modelId,
      direction,
      undercutThreshold = 1.0,
    }: {
      modelId: string;
      direction?: number[];
      undercutThreshold?: number;
    }) => {
      const body: Record<string, unknown> = {
        undercut_threshold: undercutThreshold,
      };
      if (direction) body.direction = direction;

      const resp = await fetch(`${API}/${modelId}/undercut`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return data.undercut as UndercutInfo;
    },
  });
}

export function useUndercutHeatmap() {
  const store = useMoldStore();

  return useMutation({
    mutationFn: async ({ modelId }: { modelId: string }) => {
      const resp = await fetch(`${API}/${modelId}/undercut/heatmap`);
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return data.heatmap as UndercutHeatmapData;
    },
    onSuccess: (data) => {
      store.setUndercutHeatmap(data);
      store.setUndercutHeatmapVisible(true);
    },
  });
}

export function useMoldGeneration() {
  const store = useMoldStore();

  return useMutation({
    mutationFn: async ({
      modelId,
      direction,
      wallThickness = 4.0,
      clearance = 0.3,
      shellType = "box",
      partingStyle = "flat",
      partingDepth = 3.0,
      partingPitch = 10.0,
      addFlanges = false,
      flangeWidth = 12.0,
      flangeThickness = 4.0,
      screwHoleDiameter = 4.0,
      nFlanges = 4,
      shrinkageCompensation = 0.0,
      addEjectors = false,
      nEjectors = 4,
    }: {
      modelId: string;
      direction?: number[];
      wallThickness?: number;
      clearance?: number;
      shellType?: string;
      partingStyle?: string;
      partingDepth?: number;
      partingPitch?: number;
      addFlanges?: boolean;
      flangeWidth?: number;
      flangeThickness?: number;
      screwHoleDiameter?: number;
      nFlanges?: number;
      shrinkageCompensation?: number;
      addEjectors?: boolean;
      nEjectors?: number;
    }) => {
      store.setGeneratingMold(true);
      const body: Record<string, unknown> = {
        wall_thickness: wallThickness,
        clearance,
        shell_type: shellType,
        parting_style: partingStyle,
        parting_depth: partingDepth,
        parting_pitch: partingPitch,
        add_flanges: addFlanges,
        flange_width: flangeWidth,
        flange_thickness: flangeThickness,
        screw_hole_diameter: screwHoleDiameter,
        n_flanges: nFlanges,
        shrinkage_compensation: shrinkageCompensation,
        add_ejectors: addEjectors,
        n_ejectors: nEjectors,
      };
      if (direction) body.direction = direction;

      const resp = await fetch(`${API}/${modelId}/mold/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return {
        moldId: data.mold_id as string,
        result: data.result as MoldResultInfo,
      };
    },
    onSuccess: ({ moldId, result }) => store.setMoldResult(moldId, result),
    onError: () => store.setGeneratingMold(false),
  });
}

export function useCoolingChannelDesign() {
  return useMutation({
    mutationFn: async (params: {
      moldId: string;
      layout?: string;
      nChannels?: number;
      channelDiameter?: number;
      wallOffset?: number;
    }) => {
      const resp = await fetch(`/api/v1/molds/result/${params.moldId}/cooling`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout: params.layout ?? "conformal",
          n_channels: params.nChannels ?? 4,
          channel_diameter: params.channelDiameter ?? 6.0,
          wall_offset: params.wallOffset ?? 10.0,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      return resp.json();
    },
  });
}

export function useMoldAnalysis() {
  return useMutation({
    mutationFn: async (params: { moldId: string }) => {
      const resp = await fetch(`/api/v1/molds/result/${params.moldId}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!resp.ok) throw new Error(await resp.text());
      return resp.json();
    },
  });
}
