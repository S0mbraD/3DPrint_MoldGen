import { create } from "zustand";

export type WorkflowStep =
  | "import"
  | "repair"
  | "orientation"
  | "mold"
  | "insert"
  | "gating"
  | "simulation"
  | "export";

export interface GPUInfo {
  available: boolean;
  device_name: string;
  vram_total_mb: number;
  vram_used_mb: number;
  vram_free_mb?: number;
  compute_capability?: string;
  cuda_version?: string;
  driver_version?: string;
  numba_cuda?: boolean;
  cupy?: boolean;
}

interface AppState {
  currentStep: WorkflowStep;
  setStep: (step: WorkflowStep) => void;

  leftPanelOpen: boolean;
  rightPanelOpen: boolean;
  toggleLeftPanel: () => void;
  toggleRightPanel: () => void;

  settingsOpen: boolean;
  toggleSettings: () => void;
  setSettingsOpen: (v: boolean) => void;

  gpu: GPUInfo | null;
  setGpu: (info: GPUInfo) => void;

  modelLoaded: boolean;
  modelName: string;
  faceCount: number;
  setModelInfo: (name: string, faces: number) => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentStep: "import",
  setStep: (step) => set({ currentStep: step }),

  leftPanelOpen: true,
  rightPanelOpen: true,
  toggleLeftPanel: () => set((s) => ({ leftPanelOpen: !s.leftPanelOpen })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),

  settingsOpen: false,
  toggleSettings: () => set((s) => ({ settingsOpen: !s.settingsOpen })),
  setSettingsOpen: (v) => set({ settingsOpen: v }),

  gpu: null,
  setGpu: (info) => set({ gpu: info }),

  modelLoaded: false,
  modelName: "",
  faceCount: 0,
  setModelInfo: (name, faces) =>
    set({ modelLoaded: true, modelName: name, faceCount: faces }),
}));
