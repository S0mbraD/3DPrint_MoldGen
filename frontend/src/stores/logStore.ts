import { create } from "zustand";

export type LogLevel = "debug" | "info" | "success" | "warn" | "error";

export interface LogEntry {
  id: string;
  timestamp: number;
  level: LogLevel;
  source: string;
  message: string;
  detail?: string;
  duration?: number;
}

interface LogState {
  entries: LogEntry[];
  maxEntries: number;
  log: (level: LogLevel, source: string, message: string, detail?: string, duration?: number) => void;
  clear: () => void;
}

export const useLogStore = create<LogState>((set) => ({
  entries: [],
  maxEntries: 500,
  log: (level, source, message, detail, duration) =>
    set((s) => {
      const entry: LogEntry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 5)}`,
        timestamp: Date.now(),
        level,
        source,
        message,
        detail,
        duration,
      };
      return { entries: [entry, ...s.entries].slice(0, s.maxEntries) };
    }),
  clear: () => set({ entries: [] }),
}));

function _log(level: LogLevel, source: string, message: string, detail?: string, duration?: number) {
  useLogStore.getState().log(level, source, message, detail, duration);
}

export const flog = {
  debug: (source: string, msg: string, detail?: string) => _log("debug", source, msg, detail),
  info: (source: string, msg: string, detail?: string) => _log("info", source, msg, detail),
  success: (source: string, msg: string, detail?: string, duration?: number) => _log("success", source, msg, detail, duration),
  warn: (source: string, msg: string, detail?: string) => _log("warn", source, msg, detail),
  error: (source: string, msg: string, detail?: string) => _log("error", source, msg, detail),
};
