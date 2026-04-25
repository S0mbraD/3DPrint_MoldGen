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
      partingSurfaceType = "flat",
      partingDepth = 3.0,
      partingPitch = 10.0,
      addPourHole = true,
      pourHoleDiameter = 15.0,
      pourHolePosition,
      addVentHoles = true,
      ventHoleDiameter = 3.0,
      nVentHoles = 4,
      ventHolePositions,
      addScrewHoles = false,
      screwSize = "M4",
      nScrews = 4,
      screwTabThickness = 5.0,
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
      partingSurfaceType?: string;
      partingDepth?: number;
      partingPitch?: number;
      addPourHole?: boolean;
      pourHoleDiameter?: number;
      pourHolePosition?: number[] | null;
      addVentHoles?: boolean;
      ventHoleDiameter?: number;
      nVentHoles?: number;
      ventHolePositions?: number[][] | null;
      addScrewHoles?: boolean;
      screwSize?: string;
      nScrews?: number;
      screwTabThickness?: number;
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
        parting_surface_type: partingSurfaceType,
        parting_depth: partingDepth,
        parting_pitch: partingPitch,
        add_pour_hole: addPourHole,
        pour_hole_diameter: pourHoleDiameter,
        add_vent_holes: addVentHoles,
        vent_hole_diameter: ventHoleDiameter,
        n_vent_holes: nVentHoles,
        add_screw_holes: addScrewHoles,
        screw_size: screwSize,
        n_screws: nScrews,
        screw_tab_thickness: screwTabThickness,
        shrinkage_compensation: shrinkageCompensation,
        add_ejectors: addEjectors,
        n_ejectors: nEjectors,
      };
      if (direction) body.direction = direction;
      if (pourHolePosition) body.pour_hole_position = pourHolePosition;
      if (ventHolePositions && ventHolePositions.length > 0) body.vent_hole_positions = ventHolePositions;

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

export function useHolePreview() {
  return useMutation({
    mutationFn: async ({
      modelId,
      direction,
      pourHoleDiameter = 15.0,
      ventHoleDiameter = 3.0,
      nVentHoles = 4,
    }: {
      modelId: string;
      direction?: number[];
      pourHoleDiameter?: number;
      ventHoleDiameter?: number;
      nVentHoles?: number;
    }) => {
      const body: Record<string, unknown> = {
        pour_hole_diameter: pourHoleDiameter,
        vent_hole_diameter: ventHoleDiameter,
        n_vent_holes: nVentHoles,
      };
      if (direction) body.direction = direction;

      const resp = await fetch(`${API}/${modelId}/mold/hole-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return {
        pourHole: data.pour_hole as { position: number[]; diameter: number; type: string; score: number },
        ventHoles: data.vent_holes as { position: number[]; diameter: number; type: string; score: number }[],
      };
    },
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
