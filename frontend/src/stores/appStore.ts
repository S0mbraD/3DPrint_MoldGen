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

const STEP_ORDER: WorkflowStep[] = [
  "import", "repair", "orientation", "mold", "insert", "gating", "simulation", "export",
];

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

export type BackendConnStatus = "online" | "offline" | "checking";

interface AppState {
  currentStep: WorkflowStep;
  completedSteps: Set<WorkflowStep>;
  setStep: (step: WorkflowStep) => void;
  markStepCompleted: (step: WorkflowStep) => void;
  canNavigateTo: (step: WorkflowStep) => boolean;

  leftPanelOpen: boolean;
  rightPanelOpen: boolean;
  toggleLeftPanel: () => void;
  toggleRightPanel: () => void;

  settingsOpen: boolean;
  toggleSettings: () => void;
  setSettingsOpen: (v: boolean) => void;

  consoleOpen: boolean;
  toggleConsole: () => void;

  gpu: GPUInfo | null;
  setGpu: (info: GPUInfo) => void;

  backendStatus: BackendConnStatus;
  setBackendStatus: (s: BackendConnStatus) => void;

  modelLoaded: boolean;
  modelName: string;
  faceCount: number;
  setModelInfo: (name: string, faces: number) => void;
  clearModelInfo: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  currentStep: "import",
  completedSteps: new Set<WorkflowStep>(),
  setStep: (step) => {
    if (get().canNavigateTo(step)) {
      set({ currentStep: step });
    }
  },
  markStepCompleted: (step) =>
    set((s) => {
      const next = new Set(s.completedSteps);
      next.add(step);
      return { completedSteps: next };
    }),
  canNavigateTo: (step) => {
    const state = get();
    const targetIdx = STEP_ORDER.indexOf(step);
    if (targetIdx <= 0) return true;
    if (step === "import") return true;
    return state.modelLoaded;
  },

  leftPanelOpen: true,
  rightPanelOpen: true,
  toggleLeftPanel: () => set((s) => ({ leftPanelOpen: !s.leftPanelOpen })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),

  settingsOpen: false,
  toggleSettings: () => set((s) => ({ settingsOpen: !s.settingsOpen })),
  setSettingsOpen: (v) => set({ settingsOpen: v }),

  consoleOpen: false,
  toggleConsole: () => set((s) => ({ consoleOpen: !s.consoleOpen })),

  gpu: null,
  setGpu: (info) => set({ gpu: info }),

  backendStatus: "checking",
  setBackendStatus: (backendStatus) => set({ backendStatus }),

  modelLoaded: false,
  modelName: "",
  faceCount: 0,
  setModelInfo: (name, faces) =>
    set({ modelLoaded: true, modelName: name, faceCount: faces }),
  clearModelInfo: () =>
    set({
      modelLoaded: false, modelName: "", faceCount: 0,
      completedSteps: new Set<WorkflowStep>(),
      currentStep: "import",
    }),
}));

export { STEP_ORDER };
