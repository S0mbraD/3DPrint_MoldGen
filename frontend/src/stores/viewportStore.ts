import { create } from "zustand";

export type DisplayMode =
  | "standard"
  | "wireframe"
  | "clay"
  | "xray"
  | "flat"
  | "normal";

export type GridUnit = "mm" | "cm" | "m" | "inch";

export const GRID_CONFIGS: Record<
  GridUnit,
  { cellSize: number; sectionSize: number; fadeDistance: number }
> = {
  mm: { cellSize: 1, sectionSize: 10, fadeDistance: 300 },
  cm: { cellSize: 10, sectionSize: 5, fadeDistance: 500 },
  m: { cellSize: 1000, sectionSize: 1, fadeDistance: 5000 },
  inch: { cellSize: 25.4, sectionSize: 4, fadeDistance: 500 },
};

export const DISPLAY_MODE_LABELS: Record<DisplayMode, string> = {
  standard: "标准",
  wireframe: "线框",
  clay: "黏土",
  xray: "X光",
  flat: "平面着色",
  normal: "法线",
};

interface ViewportState {
  modelVisible: boolean;
  modelOpacity: number;
  moldVisible: boolean;
  moldOpacity: number;
  shellOverrides: Record<number, { visible: boolean; opacity: number }>;

  insertVisible: boolean;
  insertOpacity: number;

  displayMode: DisplayMode;
  gridUnit: GridUnit;

  setModelVisible: (v: boolean) => void;
  setModelOpacity: (v: number) => void;
  setMoldVisible: (v: boolean) => void;
  setMoldOpacity: (v: number) => void;
  setShellOverride: (
    id: number,
    patch: Partial<{ visible: boolean; opacity: number }>,
  ) => void;
  setInsertVisible: (v: boolean) => void;
  setInsertOpacity: (v: number) => void;
  setDisplayMode: (m: DisplayMode) => void;
  setGridUnit: (u: GridUnit) => void;
}

export const useViewportStore = create<ViewportState>((set) => ({
  modelVisible: true,
  modelOpacity: 1.0,
  moldVisible: true,
  moldOpacity: 0.35,
  shellOverrides: {},

  insertVisible: true,
  insertOpacity: 0.55,

  displayMode: "standard",
  gridUnit: "cm",

  setModelVisible: (v) => set({ modelVisible: v }),
  setModelOpacity: (v) => set({ modelOpacity: v }),
  setMoldVisible: (v) => set({ moldVisible: v }),
  setMoldOpacity: (v) => set({ moldOpacity: v }),
  setShellOverride: (id, patch) =>
    set((s) => {
      const prev = s.shellOverrides[id] ?? {
        visible: true,
        opacity: s.moldOpacity,
      };
      return {
        shellOverrides: {
          ...s.shellOverrides,
          [id]: { ...prev, ...patch },
        },
      };
    }),
  setInsertVisible: (v) => set({ insertVisible: v }),
  setInsertOpacity: (v) => set({ insertOpacity: v }),
  setDisplayMode: (m) => set({ displayMode: m }),
  setGridUnit: (u) => set({ gridUnit: u }),
}));
