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

export type MeasureTool = "none" | "distance" | "angle" | "area";

interface MeasurePoint {
  position: [number, number, number];
  normal?: [number, number, number];
}

interface MeasureState {
  measureTool: MeasureTool;
  measurePoints: MeasurePoint[];
  measureResult: string | null;
}

interface ViewportState extends MeasureState {
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
  clearShellOverrides: () => void;

  setMeasureTool: (t: MeasureTool) => void;
  addMeasurePoint: (p: MeasurePoint) => void;
  clearMeasure: () => void;
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
  clearShellOverrides: () => set({ shellOverrides: {} }),

  measureTool: "none",
  measurePoints: [],
  measureResult: null,

  setMeasureTool: (t) => set({ measureTool: t, measurePoints: [], measureResult: null }),
  addMeasurePoint: (p) =>
    set((s) => {
      const pts = [...s.measurePoints, p];
      let result: string | null = null;
      if (s.measureTool === "distance" && pts.length >= 2) {
        const a = pts[0].position;
        const b = pts[1].position;
        const d = Math.sqrt(
          (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2,
        );
        result = `距离: ${d.toFixed(2)} mm`;
      } else if (s.measureTool === "angle" && pts.length >= 3) {
        const [p1, p2, p3] = pts;
        const va = [
          p1.position[0] - p2.position[0],
          p1.position[1] - p2.position[1],
          p1.position[2] - p2.position[2],
        ];
        const vb = [
          p3.position[0] - p2.position[0],
          p3.position[1] - p2.position[1],
          p3.position[2] - p2.position[2],
        ];
        const dot = va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2];
        const magA = Math.sqrt(va[0] ** 2 + va[1] ** 2 + va[2] ** 2);
        const magB = Math.sqrt(vb[0] ** 2 + vb[1] ** 2 + vb[2] ** 2);
        const angle = magA > 0 && magB > 0
          ? Math.acos(Math.min(1, Math.max(-1, dot / (magA * magB)))) * (180 / Math.PI)
          : 0;
        result = `角度: ${angle.toFixed(1)}°`;
      } else if (s.measureTool === "area" && pts.length >= 3) {
        let area = 0;
        for (let i = 1; i < pts.length - 1; i++) {
          const a = pts[0].position;
          const b = pts[i].position;
          const c = pts[i + 1].position;
          const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
          const ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
          const cross = [
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
          ];
          area += 0.5 * Math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2);
        }
        result = `面积: ${area.toFixed(2)} mm²`;
      }
      return { measurePoints: pts, measureResult: result };
    }),
  clearMeasure: () => set({ measureTool: "none", measurePoints: [], measureResult: null }),
}));
