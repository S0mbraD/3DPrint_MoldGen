import { useEffect, useRef } from "react";
import { useAppStore, type WorkflowStep } from "../stores/appStore";

type ActionMap = Record<string, () => void>;

/**
 * Hook for a step panel to register toolbar actions.
 * When the StepToolbar dispatches `moldgen:toolbar-action`,
 * and the current step matches, the corresponding handler fires.
 */
export function useToolbarHandler(actions: ActionMap) {
  const ref = useRef(actions);
  ref.current = actions;

  useEffect(() => {
    const handler = (e: Event) => {
      const id = (e as CustomEvent).detail as string;
      ref.current[id]?.();
    };
    window.addEventListener("moldgen:toolbar-action", handler);
    return () => window.removeEventListener("moldgen:toolbar-action", handler);
  }, []);
}

const SHORTCUT_MAP: Partial<Record<WorkflowStep, Record<string, string>>> = {
  import: { o: "open", u: "upload" },
  repair: { r: "auto_repair", s: "simplify" },
  orientation: { a: "analyze" },
  mold: { p: "parting", g: "build_shell" },
  insert: { a: "analyze_pos", g: "gen_plate" },
  gating: { d: "design" },
  simulation: {},
  export: { e: "export_model" },
};

/**
 * Dispatches toolbar shortcut keys as toolbar-action events.
 * Single-letter keys (no modifiers) fire step-specific shortcuts.
 * F5/F6 fire simulation actions globally.
 */
export function useToolbarShortcuts() {
  const currentStep = useAppStore((s) => s.currentStep);
  const stepRef = useRef(currentStep);
  stepRef.current = currentStep;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        return;
      }
      if (e.ctrlKey || e.altKey || e.metaKey) return;

      if (e.key === "F5") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("moldgen:toolbar-action", { detail: "run_sim" }));
        return;
      }
      if (e.key === "F6") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("moldgen:toolbar-action", { detail: "optimize" }));
        return;
      }

      const map = SHORTCUT_MAP[stepRef.current];
      if (!map) return;
      const actionId = map[e.key.toLowerCase()];
      if (actionId) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("moldgen:toolbar-action", { detail: actionId }));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
}
