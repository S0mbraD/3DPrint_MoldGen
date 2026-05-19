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

export interface SidePullDirection {
  direction: number[];
  n_resolved: number;
  coverage: number;
  angle_from_primary: number;
}

export interface UndercutInfo {
  n_undercut_faces: number;
  total_faces: number;
  undercut_ratio: number;
  max_depth: number;
  mean_depth: number;
  total_volume: number;
  severity: "none" | "mild" | "moderate" | "severe";
  side_pulls?: SidePullDirection[];
}

export interface UndercutHeatmapData {
  vertex_positions: number[][];
  face_indices: number[][];
  face_values: number[];
  max_depth: number;
}

export interface PartingSurfaceInfo {
  face_count: number;
  normal: number[];
  bounds_min: number[];
  bounds_max: number[];
  surface_type: string;
}

export interface PartingResult {
  direction: number[];
  parting_lines: PartingLineInfo[];
  parting_surface?: PartingSurfaceInfo | null;
  n_upper_faces: number;
  n_lower_faces: number;
  undercut?: UndercutInfo;
  surface_type_used?: string;
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

export interface ScrewHoleInfo {
  position: number[];
  screw_size: string;
  through_diameter: number;
  counterbore_diameter: number;
  counterbore_depth: number;
}

export interface ClampBracketInfo {
  face_count: number;
  screw_positions: number[][];
}

export interface MoldResultInfo {
  n_shells: number;
  shells: MoldShellInfo[];
  cavity_volume: number;
  parting_style?: string;
  parting_surface_type?: string;
  undercut_severity?: string;
  pour_hole: HoleInfo | number[] | null;
  vent_holes: (HoleInfo | number[])[];
  alignment_features?: AlignmentFeatureInfo[];
  screw_holes?: ScrewHoleInfo[];
  clamp_brackets?: ClampBracketInfo[];
}

// ── Skin Mold (蒙皮模具) ──

export interface RegistrationFeatureInfo {
  position: number[];
  direction: number[];
  diameter: number;
  height: number;
  type: string;
}

export interface SkinThicknessStats {
  min: number;
  max: number;
  mean: number;
  std: number;
  median: number;
  p5: number;
  p95: number;
  n_thin_spots?: number;
  n_thick_spots?: number;
  uniformity_score?: number;
}

export interface SkinCoreInfo {
  face_count: number;
  vertex_count: number;
  volume: number;
  is_hollow: boolean;
}

export interface SkinMoldResultInfo {
  core: SkinCoreInfo;
  mold: MoldResultInfo;
  registration: RegistrationFeatureInfo[];
  skin_volume: number;
  original_volume: number;
  skin_thickness_stats: SkinThicknessStats;
  has_thickness_map?: boolean;
}

export type MoldMode = "standard" | "skin";

interface MoldState {
  moldMode: MoldMode;
  orientationResult: OrientationResult | null;
  partingResult: PartingResult | null;
  moldId: string | null;
  moldResult: MoldResultInfo | null;
  activeShellId: number | null;
  selectedCandidateIdx: number | null;
  undercutHeatmap: UndercutHeatmapData | null;
  undercutHeatmapVisible: boolean;

  // Skin mold state
  skinMoldId: string | null;
  skinMoldResult: SkinMoldResultInfo | null;

  isAnalyzing: boolean;
  isGeneratingParting: boolean;
  isGeneratingMold: boolean;

  setMoldMode: (m: MoldMode) => void;
  setOrientationResult: (r: OrientationResult) => void;
  setPartingResult: (r: PartingResult) => void;
  setMoldResult: (id: string, r: MoldResultInfo) => void;
  setActiveShell: (id: number | null) => void;
  setSelectedCandidate: (idx: number | null) => void;
  setUndercutHeatmap: (data: UndercutHeatmapData | null) => void;
  setUndercutHeatmapVisible: (v: boolean) => void;
  setAnalyzing: (v: boolean) => void;
  setGeneratingParting: (v: boolean) => void;
  setGeneratingMold: (v: boolean) => void;
  setSkinMoldResult: (id: string, r: SkinMoldResultInfo) => void;
  clearMold: () => void;
}

export const useMoldStore = create<MoldState>((set) => ({
  moldMode: "standard" as MoldMode,
  orientationResult: null,
  partingResult: null,
  moldId: null,
  moldResult: null,
  activeShellId: null,
  selectedCandidateIdx: null,
  undercutHeatmap: null,
  undercutHeatmapVisible: false,
  skinMoldId: null,
  skinMoldResult: null,
  isAnalyzing: false,
  isGeneratingParting: false,
  isGeneratingMold: false,

  setMoldMode: (m) => set({ moldMode: m }),
  setOrientationResult: (r) =>
    set({ orientationResult: r, isAnalyzing: false, selectedCandidateIdx: null }),
  setPartingResult: (r) => set({ partingResult: r, isGeneratingParting: false }),
  setMoldResult: (id, r) =>
    set({ moldId: id, moldResult: r, isGeneratingMold: false }),
  setActiveShell: (id) => set({ activeShellId: id }),
  setSelectedCandidate: (idx) => set({ selectedCandidateIdx: idx }),
  setUndercutHeatmap: (data) => set({ undercutHeatmap: data }),
  setUndercutHeatmapVisible: (v) => set({ undercutHeatmapVisible: v }),
  setAnalyzing: (v) => set({ isAnalyzing: v }),
  setGeneratingParting: (v) => set({ isGeneratingParting: v }),
  setGeneratingMold: (v) => set({ isGeneratingMold: v }),
  setSkinMoldResult: (id, r) =>
    set({ skinMoldId: id, skinMoldResult: r, isGeneratingMold: false }),
  clearMold: () => {
    set({
      moldMode: "standard" as MoldMode,
      orientationResult: null,
      partingResult: null,
      moldId: null,
      moldResult: null,
      activeShellId: null,
      selectedCandidateIdx: null,
      undercutHeatmap: null,
      undercutHeatmapVisible: false,
      skinMoldId: null,
      skinMoldResult: null,
      isAnalyzing: false,
      isGeneratingParting: false,
      isGeneratingMold: false,
    });
    import("./viewportStore").then(({ useViewportStore }) =>
      useViewportStore.getState().clearShellOverrides(),
    );
  },
}));
