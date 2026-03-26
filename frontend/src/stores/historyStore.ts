import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface HistoryRecord {
  id: string;
  timestamp: number;
  type: "import" | "repair" | "simplify" | "orientation" | "parting" | "mold" | "insert" | "gating" | "simulation" | "export";
  label: string;
  detail?: string;
  modelId?: string;
  moldId?: string;
  meta?: Record<string, unknown>;
}

interface HistoryState {
  records: HistoryRecord[];
  maxRecords: number;
  push: (record: Omit<HistoryRecord, "id" | "timestamp">) => void;
  clear: () => void;
  remove: (id: string) => void;
}

export const useHistoryStore = create<HistoryState>()(
  persist(
    (set) => ({
      records: [],
      maxRecords: 200,
      push: (entry) =>
        set((s) => {
          const rec: HistoryRecord = {
            ...entry,
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            timestamp: Date.now(),
          };
          const next = [rec, ...s.records].slice(0, s.maxRecords);
          return { records: next };
        }),
      clear: () => set({ records: [] }),
      remove: (id) =>
        set((s) => ({ records: s.records.filter((r) => r.id !== id) })),
    }),
    { name: "moldgen-history" },
  ),
);
