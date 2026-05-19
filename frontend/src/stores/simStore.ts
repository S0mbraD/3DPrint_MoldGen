import { create } from "zustand";

export interface GateInfo {
  position: number[];
  score: number;
  flow_balance: number;
  accessibility: number;
}

export interface VentInfo {
  position: number[];
  normal: number[];
}

export interface MeshGeometry {
  vertices: number[][];
  faces: number[][];
}

export interface GatingResultInfo {
  gate: GateInfo;
  vents: VentInfo[];
  gate_diameter: number;
  runner_width: number;
  cavity_volume: number;
  estimated_fill_time: number;
  estimated_material_volume: number;
  gate_mesh?: MeshGeometry;
  vent_meshes?: MeshGeometry[];
}

export interface DefectInfo {
  type: string;
  position: number[] | null;
  severity: number;
  description: string;
}

export interface AnalysisReportInfo {
  fill_quality_score: number;
  fill_uniformity_index: number;
  pressure_uniformity_index: number;
  velocity_uniformity_index: number;
  max_shear_rate: number;
  avg_shear_rate: number;
  temperature_range: [number, number];
  avg_temperature: number;
  cure_progress_range: [number, number];
  avg_cure_progress: number;
  thin_wall_fraction: number;
  thick_wall_fraction: number;
  min_thickness: number;
  max_thickness: number;
  avg_thickness: number;
  flow_length_ratio: number;
  fill_balance_score: number;
  gate_efficiency: number;
  n_stagnation_zones: number;
  n_high_shear_zones: number;
  recommendations: string[];
}

export interface SimResultInfo {
  fill_fraction: number;
  fill_time_seconds: number;
  max_pressure: number;
  defects: DefectInfo[];
  has_fill_time_field: boolean;
  has_pressure_field: boolean;
  has_velocity_field: boolean;
  has_shear_rate_field: boolean;
  has_temperature_field: boolean;
  has_cure_progress_field: boolean;
  has_thickness_field: boolean;
  n_animation_frames: number;
  has_visualization: boolean;
  voxel_resolution?: number[];
  analysis?: AnalysisReportInfo;
  /** Last-known solver residual per iteration, when provided by the backend */
  convergence_history?: { iteration: number; residual: number }[];
  /** Characteristic Reynolds number for the flow analysis when available */
  reynolds_number?: number;
}

export interface OptimizationResultInfo {
  converged: boolean;
  iterations: number;
  initial_fill_fraction: number;
  final_fill_fraction: number;
  initial_defects: number;
  final_defects: number;
}

export interface DefectPosition {
  type: string;
  position: number[];
  severity: number;
}

export interface VisualizationData {
  n_points: number;
  positions: number[][];
  fill_times: number[];
  pressures: number[];
  velocities: number[];
  shear_rates: number[];
  temperatures: number[];
  cure_progress: number[];
  thickness: number[];
  max_fill_time: number;
  max_pressure: number;
  max_velocity: number;
  max_shear_rate: number;
  temperature_range: [number, number];
  max_thickness: number;
  voxel_pitch: number;
  defect_positions: DefectPosition[];
  /** Sparse velocity direction samples for arrow glyphs (pos + dir, e.g. velocity vector) */
  velocity_vectors?: { pos: number[]; dir: number[] }[];
  /** Polylines from backend RK2 integration (each path: sequence of [x,y,z]) */
  streamline_paths?: number[][][];
  /** Precomputed particle trajectories */
  particle_paths?: { path: number[][]; times: number[]; speed: number }[];
}

export interface CrossSectionData {
  axis: string;
  slice_index: number;
  field: string;
  width: number;
  height: number;
  value_range: [number, number];
  pixels: number[][];
}

export type HeatmapField =
  | "fill_time"
  | "pressure"
  | "velocity"
  | "shear_rate"
  | "temperature"
  | "cure_progress"
  | "thickness";

export type SimColorPalette = "jet" | "coolwarm" | "viridis" | "turbo" | "rainbow";

interface SimState {
  selectedMaterial: string;
  gatingId: string | null;
  gatingResult: GatingResultInfo | null;
  simId: string | null;
  simResult: SimResultInfo | null;
  optimizationResult: OptimizationResultInfo | null;

  isDesigningGating: boolean;
  isSimulating: boolean;
  isOptimizing: boolean;

  // Visualization state
  visualizationData: VisualizationData | null;
  isLoadingVisualization: boolean;
  heatmapField: HeatmapField;
  heatmapVisible: boolean;
  heatmapOpacity: number;
  pointSize: number;
  colorPalette: SimColorPalette;
  showVelocityArrows: boolean;
  showColorLegend: boolean;

  // Streamline & particle controls
  streamlinesVisible: boolean;
  streamlineCount: number;
  particleDensity: number; // 1 = normal, 2 = 2x, etc.

  showFlowParticles: boolean;
  showFlowFront: boolean;
  showAnimatedStreamlines: boolean;
  flowParticleCount: number;
  flowParticleSpeed: number;
  flowParticleSize: number;

  // Animation state
  animationPlaying: boolean;
  animationProgress: number; // 0-1
  animationSpeed: number; // multiplier
  animationLoop: boolean;

  // Cross-section state
  crossSectionData: CrossSectionData | null;
  crossSectionAxis: "x" | "y" | "z";
  crossSectionPosition: number; // 0-1
  crossSectionVisible: boolean;

  // Surface map overlay
  surfaceMapData: Record<string, unknown> | null;
  surfaceMapLoading: boolean;
  surfaceMapVisible: boolean;

  // FEA state
  feaId: string | null;
  feaResult: Record<string, unknown> | null;
  feaVisualizationData: Record<string, unknown> | null;
  feaRunning: boolean;
  feaField: "displacement" | "von_mises" | "safety_factor" | "strain_energy";
  feaVisible: boolean;

  // Analysis state
  analysisExpanded: boolean;

  setMaterial: (m: string) => void;
  setGatingResult: (id: string, r: GatingResultInfo) => void;
  setSimResult: (id: string, r: SimResultInfo) => void;
  setOptimizationResult: (r: OptimizationResultInfo) => void;
  setDesigningGating: (v: boolean) => void;
  setSimulating: (v: boolean) => void;
  setOptimizing: (v: boolean) => void;

  setVisualizationData: (data: VisualizationData | null) => void;
  setLoadingVisualization: (v: boolean) => void;
  setHeatmapField: (field: HeatmapField) => void;
  setHeatmapVisible: (v: boolean) => void;
  setHeatmapOpacity: (v: number) => void;
  setPointSize: (v: number) => void;
  setColorPalette: (p: SimColorPalette) => void;
  setShowVelocityArrows: (v: boolean) => void;
  setShowColorLegend: (v: boolean) => void;

  setStreamlinesVisible: (v: boolean) => void;
  setStreamlineCount: (v: number) => void;
  setParticleDensity: (v: number) => void;

  setShowFlowParticles: (v: boolean) => void;
  setShowFlowFront: (v: boolean) => void;
  setShowAnimatedStreamlines: (v: boolean) => void;
  setFlowParticleCount: (v: number) => void;
  setFlowParticleSpeed: (v: number) => void;
  setFlowParticleSize: (v: number) => void;

  setAnimationPlaying: (v: boolean) => void;
  setAnimationProgress: (v: number) => void;
  setAnimationSpeed: (v: number) => void;
  setAnimationLoop: (v: boolean) => void;

  setCrossSectionData: (data: CrossSectionData | null) => void;
  setCrossSectionAxis: (axis: "x" | "y" | "z") => void;
  setCrossSectionPosition: (v: number) => void;
  setCrossSectionVisible: (v: boolean) => void;

  setSurfaceMapData: (data: Record<string, unknown> | null) => void;
  setSurfaceMapLoading: (v: boolean) => void;
  setSurfaceMapVisible: (v: boolean) => void;

  setFEAResult: (id: string, result: Record<string, unknown>) => void;
  setFEAVisualizationData: (data: Record<string, unknown>) => void;
  setFEARunning: (v: boolean) => void;
  setFEAField: (f: "displacement" | "von_mises" | "safety_factor" | "strain_energy") => void;
  setFEAVisible: (v: boolean) => void;

  setAnalysisExpanded: (v: boolean) => void;

  // Interactive gating placement
  placementMode: "none" | "gate" | "vent";
  manualGatePos: [number, number, number] | null;
  manualVentPositions: [number, number, number][];
  setPlacementMode: (mode: "none" | "gate" | "vent") => void;
  setManualGatePos: (pos: [number, number, number] | null) => void;
  addManualVentPos: (pos: [number, number, number]) => void;
  removeManualVentPos: (index: number) => void;
  updateManualVentPos: (index: number, pos: [number, number, number]) => void;
  clearManualPositions: () => void;

  setGatingId: (id: string) => void;
  setSimId: (id: string) => void;

  clearSim: () => void;
}

export const useSimStore = create<SimState>((set) => ({
  selectedMaterial: "silicone_a30",
  gatingId: null,
  gatingResult: null,
  simId: null,
  simResult: null,
  optimizationResult: null,
  isDesigningGating: false,
  isSimulating: false,
  isOptimizing: false,

  placementMode: "none",
  manualGatePos: null,
  manualVentPositions: [],

  visualizationData: null,
  isLoadingVisualization: false,
  heatmapField: "fill_time",
  heatmapVisible: true,
  heatmapOpacity: 0.85,
  pointSize: 4.5,
  colorPalette: "jet",
  showVelocityArrows: false,
  showColorLegend: true,

  streamlinesVisible: true,
  streamlineCount: 50,
  particleDensity: 2,

  showFlowParticles: true,
  showFlowFront: true,
  showAnimatedStreamlines: true,
  flowParticleCount: 200,
  flowParticleSpeed: 1.0,
  flowParticleSize: 2.0,

  animationPlaying: false,
  animationProgress: 1.0,
  animationSpeed: 1.0,
  animationLoop: true,

  crossSectionData: null,
  crossSectionAxis: "z",
  crossSectionPosition: 0.5,
  crossSectionVisible: false,

  surfaceMapData: null,
  surfaceMapLoading: false,
  surfaceMapVisible: false,

  feaId: null,
  feaResult: null,
  feaVisualizationData: null,
  feaRunning: false,
  feaField: "von_mises",
  feaVisible: false,

  analysisExpanded: false,

  setMaterial: (m) => set({ selectedMaterial: m }),
  setGatingResult: (id, r) => set({ gatingId: id, gatingResult: r, isDesigningGating: false }),
  setSimResult: (id, r) => set({ simId: id, simResult: r, isSimulating: false }),
  setOptimizationResult: (r) => set({ optimizationResult: r, isOptimizing: false }),
  setGatingId: (id) => set({ gatingId: id }),
  setSimId: (id) => set({ simId: id }),
  setDesigningGating: (v) => set({ isDesigningGating: v }),
  setSimulating: (v) => set({ isSimulating: v }),
  setOptimizing: (v) => set({ isOptimizing: v }),

  setVisualizationData: (data) => set({ visualizationData: data, isLoadingVisualization: false }),
  setLoadingVisualization: (v) => set({ isLoadingVisualization: v }),
  setHeatmapField: (field) => set({ heatmapField: field }),
  setHeatmapVisible: (v) => set({ heatmapVisible: v }),
  setHeatmapOpacity: (v) => set({ heatmapOpacity: v }),
  setPointSize: (v) => set({ pointSize: v }),
  setColorPalette: (p) => set({ colorPalette: p }),
  setShowVelocityArrows: (v) => set({ showVelocityArrows: v }),
  setShowColorLegend: (v) => set({ showColorLegend: v }),

  setStreamlinesVisible: (v) => set({ streamlinesVisible: v }),
  setStreamlineCount: (v) => set({ streamlineCount: v }),
  setParticleDensity: (v) => set({ particleDensity: v }),

  setShowFlowParticles: (v) => set({ showFlowParticles: v }),
  setShowFlowFront: (v) => set({ showFlowFront: v }),
  setShowAnimatedStreamlines: (v) => set({ showAnimatedStreamlines: v }),
  setFlowParticleCount: (v) =>
    set({ flowParticleCount: Math.max(1, Math.min(300, Math.round(v))) }),
  setFlowParticleSpeed: (v) =>
    set({ flowParticleSpeed: Math.min(3.0, Math.max(0.5, v)) }),
  setFlowParticleSize: (v) =>
    set({ flowParticleSize: Math.min(8.0, Math.max(0.5, v)) }),

  setAnimationPlaying: (v) => set({ animationPlaying: v }),
  setAnimationProgress: (v) => set({ animationProgress: v }),
  setAnimationSpeed: (v) =>
    set({ animationSpeed: Math.min(3.0, Math.max(0.5, v)) }),
  setAnimationLoop: (v) => set({ animationLoop: v }),

  setCrossSectionData: (data) => set({ crossSectionData: data }),
  setCrossSectionAxis: (axis) => set({ crossSectionAxis: axis }),
  setCrossSectionPosition: (v) => set({ crossSectionPosition: v }),
  setCrossSectionVisible: (v) => set({ crossSectionVisible: v }),

  setSurfaceMapData: (data) => set({ surfaceMapData: data, surfaceMapLoading: false }),
  setSurfaceMapLoading: (v) => set({ surfaceMapLoading: v }),
  setSurfaceMapVisible: (v) => set({ surfaceMapVisible: v }),

  setFEAResult: (id, result) => set({ feaId: id, feaResult: result, feaRunning: false }),
  setFEAVisualizationData: (data) => set({ feaVisualizationData: data }),
  setFEARunning: (v) => set({ feaRunning: v }),
  setFEAField: (f) => set({ feaField: f }),
  setFEAVisible: (v) => set({ feaVisible: v }),

  setAnalysisExpanded: (v) => set({ analysisExpanded: v }),

  setPlacementMode: (mode) => set({ placementMode: mode }),
  setManualGatePos: (pos) => set({ manualGatePos: pos }),
  addManualVentPos: (pos) => set((s) => ({
    manualVentPositions: [...s.manualVentPositions, pos],
  })),
  removeManualVentPos: (index) => set((s) => ({
    manualVentPositions: s.manualVentPositions.filter((_, i) => i !== index),
  })),
  updateManualVentPos: (index, pos) => set((s) => {
    const arr = [...s.manualVentPositions];
    arr[index] = pos;
    return { manualVentPositions: arr };
  }),
  clearManualPositions: () => set({
    placementMode: "none", manualGatePos: null, manualVentPositions: [],
  }),

  clearSim: () =>
    set({
      gatingId: null, gatingResult: null,
      simId: null, simResult: null,
      optimizationResult: null,
      visualizationData: null,
      crossSectionData: null,
      animationPlaying: false,
      placementMode: "none", manualGatePos: null, manualVentPositions: [],
      animationProgress: 1.0,
      colorPalette: "jet",
      showVelocityArrows: false,
      showColorLegend: true,
      showFlowParticles: true,
      showFlowFront: true,
      showAnimatedStreamlines: true,
      flowParticleCount: 200,
      flowParticleSpeed: 1.0,
      flowParticleSize: 2.0,
      surfaceMapData: null,
      surfaceMapLoading: false,
      isDesigningGating: false,
      isSimulating: false,
      isOptimizing: false,
      feaId: null, feaResult: null, feaVisualizationData: null,
      feaRunning: false,
    }),
}));
