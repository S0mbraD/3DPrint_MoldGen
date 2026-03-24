import { useEffect } from "react";
import { useAppStore, type WorkflowStep } from "../stores/appStore";
import { useAIStore } from "../stores/aiStore";

const STEP_KEYS: Record<string, WorkflowStep> = {
  "1": "import",
  "2": "repair",
  "3": "orientation",
  "4": "mold",
  "5": "insert",
  "6": "gating",
  "7": "simulation",
  "8": "export",
};

export function useKeyboardShortcuts() {
  const setStep = useAppStore((s) => s.setStep);
  const toggleLeftPanel = useAppStore((s) => s.toggleLeftPanel);
  const toggleRightPanel = useAppStore((s) => s.toggleRightPanel);
  const toggleSettings = useAppStore((s) => s.toggleSettings);
  const toggleChat = useAIStore((s) => s.toggleChat);
  const toggleWorkstation = useAIStore((s) => s.toggleAgentWorkstation);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        return;
      }

      if (e.ctrlKey && !e.shiftKey && !e.altKey) {
        const step = STEP_KEYS[e.key];
        if (step) {
          e.preventDefault();
          setStep(step);
          return;
        }
      }

      if (e.ctrlKey && e.key === "b") {
        e.preventDefault();
        toggleLeftPanel();
        return;
      }

      if (e.ctrlKey && e.key === "i" && !e.shiftKey) {
        e.preventDefault();
        toggleRightPanel();
        return;
      }

      if (e.ctrlKey && e.key === "j") {
        e.preventDefault();
        toggleChat();
        return;
      }

      if (e.ctrlKey && e.key === ",") {
        e.preventDefault();
        toggleSettings();
        return;
      }

      if (e.ctrlKey && e.shiftKey && e.key === "A") {
        e.preventDefault();
        toggleWorkstation();
        return;
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    setStep,
    toggleLeftPanel,
    toggleRightPanel,
    toggleSettings,
    toggleChat,
    toggleWorkstation,
  ]);
}
