import { create } from "zustand";

export interface InsertPosition {
  origin: number[];
  normal: number[];
  score: number;
  section_area: number;
  reason: string;
  skeleton_type?: string;
}

export interface InsertPlateInfo {
  face_count: number;
  vertex_count: number;
  thickness: number;
  insert_type: string;
  skeleton_type?: string;
  position?: {
    origin: number[];
    normal: number[];
    score: number;
    section_area: number;
    reason: string;
  };
  anchor?: { type: string; count: number; feature_size: number } | null;
  n_pillars: number;
  pillars: Array<{
    start: number[];
    end: number[];
    direction: number[];
    length: number;
    diameter: number;
    mold_hole_center: number[];
  }>;
  volume: number;
  center: number[];
}

export interface HoleBrushRegion {
  u: number;
  v: number;
  radius: number;
}

interface InsertState {
  positions: InsertPosition[];
  setPositions: (p: InsertPosition[]) => void;

  insertId: string | null;
  setInsertId: (id: string | null) => void;

  plates: InsertPlateInfo[];
  setPlates: (p: InsertPlateInfo[]) => void;

  assemblyValid: boolean;
  setAssemblyValid: (v: boolean) => void;

  validationMessages: string[];
  setValidationMessages: (m: string[]) => void;

  isAnalyzing: boolean;
  setAnalyzing: (v: boolean) => void;

  isGenerating: boolean;
  setGenerating: (v: boolean) => void;

  // Brush painting (holes + ribs)
  brushMode: "holes" | "ribs";
  setBrushMode: (m: "holes" | "ribs") => void;
  holeBrushActive: boolean;
  setHoleBrushActive: (v: boolean) => void;
  holeBrushSize: number;
  setHoleBrushSize: (v: number) => void;
  holeBrushRegions: HoleBrushRegion[];
  addHoleBrushRegion: (r: HoleBrushRegion) => void;
  clearHoleBrushRegions: () => void;
  ribBrushRegions: HoleBrushRegion[];
  addRibBrushRegion: (r: HoleBrushRegion) => void;
  clearRibBrushRegions: () => void;
}

export const useInsertStore = create<InsertState>((set) => ({
  positions: [],
  setPositions: (positions) => set({ positions }),

  insertId: null,
  setInsertId: (insertId) => set({ insertId }),

  plates: [],
  setPlates: (plates) => set({ plates }),

  assemblyValid: false,
  setAssemblyValid: (assemblyValid) => set({ assemblyValid }),

  validationMessages: [],
  setValidationMessages: (validationMessages) => set({ validationMessages }),

  isAnalyzing: false,
  setAnalyzing: (isAnalyzing) => set({ isAnalyzing }),

  isGenerating: false,
  setGenerating: (isGenerating) => set({ isGenerating }),

  brushMode: "holes",
  setBrushMode: (brushMode) => set({ brushMode }),
  holeBrushActive: false,
  setHoleBrushActive: (holeBrushActive) => set({ holeBrushActive }),
  holeBrushSize: 15,
  setHoleBrushSize: (holeBrushSize) => set({ holeBrushSize }),
  holeBrushRegions: [],
  addHoleBrushRegion: (r) =>
    set((s) => ({ holeBrushRegions: [...s.holeBrushRegions, r] })),
  clearHoleBrushRegions: () => set({ holeBrushRegions: [] }),
  ribBrushRegions: [],
  addRibBrushRegion: (r) =>
    set((s) => ({ ribBrushRegions: [...s.ribBrushRegions, r] })),
  clearRibBrushRegions: () => set({ ribBrushRegions: [] }),
}));
