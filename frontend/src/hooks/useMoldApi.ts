import { useMutation } from "@tanstack/react-query";
import {
  useMoldStore,
  type OrientationResult,
  type PartingResult,
  type MoldResultInfo,
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
    }: {
      modelId: string;
      direction?: number[];
    }) => {
      store.setGeneratingParting(true);
      const body: Record<string, unknown> = {};
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
