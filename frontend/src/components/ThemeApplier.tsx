import { useEffect } from "react";
import { useSettingsStore, ACCENT_COLORS } from "../stores/settingsStore";

const DARK_TOKENS: Record<string, string> = {
  "--color-bg-primary": "#0d0d12",
  "--color-bg-secondary": "#14141e",
  "--color-bg-panel": "#191924",
  "--color-bg-hover": "#22223a",
  "--color-bg-active": "#2a2a48",
  "--color-bg-inset": "#111118",
  "--color-border": "#262640",
  "--color-border-subtle": "#1e1e34",
  "--color-text-primary": "#e8ecf4",
  "--color-text-secondary": "#9ca3b4",
  "--color-text-muted": "#5c6478",
};

const LIGHT_TOKENS: Record<string, string> = {
  "--color-bg-primary": "#f8f9fc",
  "--color-bg-secondary": "#ffffff",
  "--color-bg-panel": "#f1f3f8",
  "--color-bg-hover": "#e8eaf0",
  "--color-bg-active": "#dcdfe8",
  "--color-bg-inset": "#eceef4",
  "--color-border": "#d1d5e0",
  "--color-border-subtle": "#e2e5ec",
  "--color-text-primary": "#1a1d26",
  "--color-text-secondary": "#4a5068",
  "--color-text-muted": "#8891a5",
};

function resolveSystemTheme(): "dark" | "light" {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeApplier() {
  const themeMode = useSettingsStore((s) => s.themeMode);
  const accentColor = useSettingsStore((s) => s.accentColor);
  const fontSize = useSettingsStore((s) => s.fontSize);
  const panelFontSize = useSettingsStore((s) => s.panelFontSize);
  const monoFontSize = useSettingsStore((s) => s.monoFontSize);
  const borderRadius = useSettingsStore((s) => s.borderRadius);
  const uiDensity = useSettingsStore((s) => s.uiDensity);
  const enableAnimations = useSettingsStore((s) => s.enableAnimations);

  useEffect(() => {
    const resolved = themeMode === "system" ? resolveSystemTheme() : themeMode;
    const tokens = resolved === "light" ? LIGHT_TOKENS : DARK_TOKENS;
    const root = document.documentElement;

    for (const [prop, val] of Object.entries(tokens)) {
      root.style.setProperty(prop, val);
    }

    const accent = ACCENT_COLORS[accentColor];
    root.style.setProperty("--color-accent", accent.main);
    root.style.setProperty("--color-accent-hover", accent.hover);
    root.style.setProperty("--color-accent-muted", accent.muted);
    root.style.setProperty("--color-border-accent", accent.main);

    root.style.setProperty("--mg-font-size", `${fontSize}px`);
    root.style.setProperty("--mg-panel-font-size", `${panelFontSize}px`);
    root.style.setProperty("--mg-mono-font-size", `${monoFontSize}px`);
    root.style.setProperty("--mg-border-radius", `${borderRadius}px`);

    const DESIGN_BASE = 13;
    const scale = fontSize / DESIGN_BASE;
    root.style.setProperty("--mg-ui-scale", scale.toFixed(4));

    root.style.fontSize = "";

    const spacing = uiDensity === "compact" ? "0.85" : uiDensity === "comfortable" ? "1.2" : "1";
    root.style.setProperty("--mg-density", spacing);

    root.classList.toggle("no-animations", !enableAnimations);
    root.dataset.theme = resolved;
  }, [themeMode, accentColor, fontSize, panelFontSize, monoFontSize, borderRadius, uiDensity, enableAnimations]);

  useEffect(() => {
    if (themeMode !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const resolved = resolveSystemTheme();
      const tokens = resolved === "light" ? LIGHT_TOKENS : DARK_TOKENS;
      const root = document.documentElement;
      for (const [prop, val] of Object.entries(tokens)) {
        root.style.setProperty(prop, val);
      }
      root.dataset.theme = resolved;
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [themeMode]);

  return null;
}
