import { useMutation } from "@tanstack/react-query";
import {
  useMoldStore,
  type OrientationResult,
  type PartingResult,
  type MoldResultInfo,
  type SkinMoldResultInfo,
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
      addScrewHoles = false,
      screwSize = "M4",
      nScrews = 4,
      screwTabThickness = 5.0,
      shrinkageCompensation = 0.0,
      addEjectors = false,
      nEjectors = 4,
      moldMaterial = "pla",
      surfaceTexture = "none",
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
      addScrewHoles?: boolean;
      screwSize?: string;
      nScrews?: number;
      screwTabThickness?: number;
      shrinkageCompensation?: number;
      addEjectors?: boolean;
      nEjectors?: number;
      moldMaterial?: string;
      surfaceTexture?: string;
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
        mold_material: moldMaterial,
        surface_texture: surfaceTexture,
        add_screw_holes: addScrewHoles,
        screw_size: screwSize,
        n_screws: nScrews,
        screw_tab_thickness: screwTabThickness,
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


// ── Skin Mold Generation (蒙皮模具) ──

export interface SkinMoldParams {
  modelId: string;
  direction?: number[];
  skinThickness?: number;
  variableThickness?: boolean;
  curvatureInfluence?: number;
  coreResolution?: number;
  coreSmoothing?: number;
  coreClearance?: number;
  coreShellThickness?: number;
  coreDrainHoles?: boolean;
  addSupportPegs?: boolean;
  pegCount?: number;
  pegDiameter?: number;
  pegHeight?: number;
  registrationType?: string;
  registrationCount?: number;
  registrationDiameter?: number;
  registrationHeight?: number;
  moldWallThickness?: number;
  moldShellType?: string;
  partingStyle?: string;
  addAlignmentPins?: boolean;
  addScrewHoles?: boolean;
  shrinkageCompensation?: number;
}

export function useSkinMoldGeneration() {
  const store = useMoldStore();

  return useMutation({
    mutationFn: async (p: SkinMoldParams) => {
      store.setGeneratingMold(true);
      const body: Record<string, unknown> = {
        skin_thickness: p.skinThickness ?? 3.0,
        variable_thickness: p.variableThickness ?? false,
        curvature_influence: p.curvatureInfluence ?? 0.5,
        core_resolution: p.coreResolution ?? 64,
        core_smoothing: p.coreSmoothing ?? 2,
        core_clearance: p.coreClearance ?? 0.3,
        core_shell_thickness: p.coreShellThickness ?? 0.0,
        core_drain_holes: p.coreDrainHoles ?? false,
        add_support_pegs: p.addSupportPegs ?? true,
        peg_count: p.pegCount ?? 3,
        peg_diameter: p.pegDiameter ?? 4.0,
        peg_height: p.pegHeight ?? 6.0,
        registration_type: p.registrationType ?? "pin",
        registration_count: p.registrationCount ?? 4,
        registration_diameter: p.registrationDiameter ?? 5.0,
        registration_height: p.registrationHeight ?? 8.0,
        mold_wall_thickness: p.moldWallThickness ?? 5.0,
        mold_shell_type: p.moldShellType ?? "box",
        parting_style: p.partingStyle ?? "flat",
        add_alignment_pins: p.addAlignmentPins ?? true,
        add_screw_holes: p.addScrewHoles ?? false,
        shrinkage_compensation: p.shrinkageCompensation ?? 0,
      };
      if (p.direction) body.direction = p.direction;

      const resp = await fetch(`${API}/${p.modelId}/mold/generate-skin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      return {
        skinMoldId: data.skin_mold_id as string,
        moldId: data.mold_id as string,
        result: data.result as SkinMoldResultInfo,
        moldResult: data.result.mold as MoldResultInfo,
      };
    },
    onSuccess: ({ skinMoldId, moldId, result, moldResult }) => {
      store.setSkinMoldResult(skinMoldId, result);
      store.setMoldResult(moldId, moldResult);
    },
    onError: () => store.setGeneratingMold(false),
  });
}
