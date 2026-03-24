import { useMutation } from "@tanstack/react-query";

const API = "/api/v1/export";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function useExportModel() {
  return useMutation({
    mutationFn: async (params: { model_id: string; format: string }) => {
      const res = await fetch(`${API}/model`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const ext = params.format;
      downloadBlob(blob, `model.${ext}`);
    },
  });
}

export function useExportMold() {
  return useMutation({
    mutationFn: async (params: { mold_id: string; format: string; include_model?: boolean; model_id?: string }) => {
      const res = await fetch(`${API}/mold`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      downloadBlob(blob, `mold_shells.zip`);
    },
  });
}

export function useExportInsert() {
  return useMutation({
    mutationFn: async (params: { insert_id: string; format: string }) => {
      const res = await fetch(`${API}/insert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      downloadBlob(blob, `inserts.zip`);
    },
  });
}

export function useExportAll() {
  return useMutation({
    mutationFn: async (params: { model_id?: string; mold_id?: string; insert_id?: string; format: string }) => {
      const res = await fetch(`${API}/all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      downloadBlob(blob, `moldgen_export.zip`);
    },
  });
}
