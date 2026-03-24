import { create } from "zustand";

export interface DirectionScore {
  direction: number[];
  total_score: number;
  visibility_ratio: number;
  undercut_ratio: number;
  flatness: number;
  min_draft_angle: number;
  mean_draft_angle?: number;
  symmetry: number;
  stability: number;
  compactness?: number;
  support_area?: number;
}

export interface OrientationResult {
  best_direction: number[];
  best_score: DirectionScore;
  top_candidates: DirectionScore[];
}

export interface PartingLineInfo {
  vertex_count: number;
  edge_count: number;
  is_closed: boolean;
  length: number;
}

export interface PartingResult {
  direction: number[];
  parting_lines: PartingLineInfo[];
  parting_surface?: { face_count: number; normal: number[]; bounds_min: number[]; bounds_max: number[] } | null;
  n_upper_faces: number;
  n_lower_faces: number;
}

export interface MoldShellInfo {
  shell_id: number;
  direction: number[];
  volume: number;
  surface_area: number;
  face_count: number;
  is_printable: boolean;
  min_draft_angle: number;
}

export interface HoleInfo {
  position: number[];
  diameter: number;
  type: string;
  score: number;
}

export interface AlignmentFeatureInfo {
  position: number[];
  type: string;
  diameter: number;
  height: number;
}

export interface MoldResultInfo {
  n_shells: number;
  shells: MoldShellInfo[];
  cavity_volume: number;
  pour_hole: HoleInfo | number[] | null;
  vent_holes: (HoleInfo | number[])[];
  alignment_features?: AlignmentFeatureInfo[];
}

interface MoldState {
  orientationResult: OrientationResult | null;
  partingResult: PartingResult | null;
  moldId: string | null;
  moldResult: MoldResultInfo | null;
  activeShellId: number | null;
  selectedCandidateIdx: number | null;

  isAnalyzing: boolean;
  isGeneratingParting: boolean;
  isGeneratingMold: boolean;

  setOrientationResult: (r: OrientationResult) => void;
  setPartingResult: (r: PartingResult) => void;
  setMoldResult: (id: string, r: MoldResultInfo) => void;
  setActiveShell: (id: number | null) => void;
  setSelectedCandidate: (idx: number | null) => void;
  setAnalyzing: (v: boolean) => void;
  setGeneratingParting: (v: boolean) => void;
  setGeneratingMold: (v: boolean) => void;
  clearMold: () => void;
}

export const useMoldStore = create<MoldState>((set) => ({
  orientationResult: null,
  partingResult: null,
  moldId: null,
  moldResult: null,
  activeShellId: null,
  selectedCandidateIdx: null,
  isAnalyzing: false,
  isGeneratingParting: false,
  isGeneratingMold: false,

  setOrientationResult: (r) =>
    set({ orientationResult: r, isAnalyzing: false, selectedCandidateIdx: null }),
  setPartingResult: (r) => set({ partingResult: r, isGeneratingParting: false }),
  setMoldResult: (id, r) =>
    set({ moldId: id, moldResult: r, isGeneratingMold: false }),
  setActiveShell: (id) => set({ activeShellId: id }),
  setSelectedCandidate: (idx) => set({ selectedCandidateIdx: idx }),
  setAnalyzing: (v) => set({ isAnalyzing: v }),
  setGeneratingParting: (v) => set({ isGeneratingParting: v }),
  setGeneratingMold: (v) => set({ isGeneratingMold: v }),
  clearMold: () =>
    set({
      orientationResult: null,
      partingResult: null,
      moldId: null,
      moldResult: null,
      activeShellId: null,
      selectedCandidateIdx: null,
    }),
}));
