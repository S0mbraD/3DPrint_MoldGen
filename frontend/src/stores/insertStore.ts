import { create } from "zustand";

export interface InsertPosition {
  origin: number[];
  normal: number[];
  score: number;
  section_area: number;
  reason: string;
}

export interface InsertPlateInfo {
  face_count: number;
  vertex_count: number;
  thickness: number;
  insert_type: string;
  position: InsertPosition;
  anchor: { type: string; count: number; feature_size: number } | null;
  n_locating_slots: number;
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
}));
