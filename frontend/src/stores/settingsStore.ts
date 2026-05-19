import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeMode = "dark" | "light" | "system";
export type AccentColor = "indigo" | "blue" | "emerald" | "rose" | "amber" | "violet" | "cyan";
export type UIDensity = "compact" | "normal" | "comfortable";

const ACCENT_COLORS: Record<AccentColor, { main: string; hover: string; muted: string }> = {
  indigo: { main: "#6366f1", hover: "#818cf8", muted: "#4338ca" },
  blue:   { main: "#3b82f6", hover: "#60a5fa", muted: "#2563eb" },
  emerald:{ main: "#10b981", hover: "#34d399", muted: "#059669" },
  rose:   { main: "#f43f5e", hover: "#fb7185", muted: "#e11d48" },
  amber:  { main: "#f59e0b", hover: "#fbbf24", muted: "#d97706" },
  violet: { main: "#8b5cf6", hover: "#a78bfa", muted: "#7c3aed" },
  cyan:   { main: "#06b6d4", hover: "#22d3ee", muted: "#0891b2" },
};

export { ACCENT_COLORS };

interface SettingsState {
  // 外观
  themeMode: ThemeMode;
  accentColor: AccentColor;
  uiDensity: UIDensity;
  fontSize: number;
  panelFontSize: number;
  monoFontSize: number;
  borderRadius: number;

  // 3D 视口
  showGrid: boolean;
  showAxes: boolean;
  showGizmo: boolean;
  autoRotate: boolean;
  antiAlias: boolean;

  // 交互
  enableAnimations: boolean;
  enableSounds: boolean;
  confirmBeforeDelete: boolean;
  autoSave: boolean;
  autoSaveInterval: number;

  // Actions
  setThemeMode: (m: ThemeMode) => void;
  setAccentColor: (c: AccentColor) => void;
  setUIDensity: (d: UIDensity) => void;
  setFontSize: (s: number) => void;
  setPanelFontSize: (s: number) => void;
  setMonoFontSize: (s: number) => void;
  setBorderRadius: (r: number) => void;
  setShowGrid: (v: boolean) => void;
  setShowAxes: (v: boolean) => void;
  setShowGizmo: (v: boolean) => void;
  setAutoRotate: (v: boolean) => void;
  setAntiAlias: (v: boolean) => void;
  setEnableAnimations: (v: boolean) => void;
  setEnableSounds: (v: boolean) => void;
  setConfirmBeforeDelete: (v: boolean) => void;
  setAutoSave: (v: boolean) => void;
  setAutoSaveInterval: (v: number) => void;
  resetAll: () => void;
}

const DEFAULTS = {
  themeMode: "dark" as ThemeMode,
  accentColor: "indigo" as AccentColor,
  uiDensity: "normal" as UIDensity,
  fontSize: 14,
  panelFontSize: 13,
  monoFontSize: 13,
  borderRadius: 8,
  showGrid: true,
  showAxes: true,
  showGizmo: true,
  autoRotate: false,
  antiAlias: true,
  enableAnimations: true,
  enableSounds: false,
  confirmBeforeDelete: true,
  autoSave: false,
  autoSaveInterval: 60,
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      ...DEFAULTS,

      setThemeMode: (m) => set({ themeMode: m }),
      setAccentColor: (c) => set({ accentColor: c }),
      setUIDensity: (d) => set({ uiDensity: d }),
      setFontSize: (s) => set({ fontSize: s }),
      setPanelFontSize: (s) => set({ panelFontSize: s }),
      setMonoFontSize: (s) => set({ monoFontSize: s }),
      setBorderRadius: (r) => set({ borderRadius: r }),
      setShowGrid: (v) => set({ showGrid: v }),
      setShowAxes: (v) => set({ showAxes: v }),
      setShowGizmo: (v) => set({ showGizmo: v }),
      setAutoRotate: (v) => set({ autoRotate: v }),
      setAntiAlias: (v) => set({ antiAlias: v }),
      setEnableAnimations: (v) => set({ enableAnimations: v }),
      setEnableSounds: (v) => set({ enableSounds: v }),
      setConfirmBeforeDelete: (v) => set({ confirmBeforeDelete: v }),
      setAutoSave: (v) => set({ autoSave: v }),
      setAutoSaveInterval: (v) => set({ autoSaveInterval: v }),
      resetAll: () => set(DEFAULTS),
    }),
    {
      name: "moldgen-settings",
      version: 3,
      migrate: (persisted: unknown, version: number) => {
        const state = persisted as Record<string, unknown>;
        if (version < 3) {
          if ((state.fontSize as number) <= 13) state.fontSize = DEFAULTS.fontSize;
          if ((state.panelFontSize as number) <= 12) state.panelFontSize = DEFAULTS.panelFontSize;
          if ((state.monoFontSize as number) <= 12) state.monoFontSize = DEFAULTS.monoFontSize;
        }
        return state;
      },
    },
  ),
);
