import { useMutation } from "@tanstack/react-query";
import { useInsertStore } from "../stores/insertStore";

const API = "/api/v1/inserts";

async function checkedJson(res: Response) {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
  return res.json();
}

export function useAnalyzePositions() {
  const { setPositions, setAnalyzing } = useInsertStore();
  return useMutation({
    mutationFn: async (params: { model_id: string; organ_type?: string }) => {
      setAnalyzing(true);
      const res = await fetch(`${API}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      return checkedJson(res);
    },
    onSuccess: (data) => {
      setPositions(data.positions ?? []);
      setAnalyzing(false);
    },
    onError: () => setAnalyzing(false),
  });
}

export function useGenerateInserts() {
  const { setInsertId, setPlates, setAssemblyValid, setValidationMessages, setGenerating } =
    useInsertStore();
  return useMutation({
    mutationFn: async (params: {
      model_id: string;
      organ_type?: string;
      anchor_type?: string;
      insert_type?: string;
      n_plates?: number;
      thickness?: number;
      mold_id?: string;
      conformal_offset?: number;
      rib_height?: number;
      rib_spacing?: number;
      lattice_cell_size?: number;
      lattice_strut_diameter?: number;
      lattice_type?: string;
    }) => {
      setGenerating(true);
      const res = await fetch(`${API}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      return checkedJson(res);
    },
    onSuccess: (data) => {
      setInsertId(data.insert_id ?? null);
      setPlates(data.plates ?? []);
      setAssemblyValid(data.assembly_valid ?? false);
      setValidationMessages(data.validation_messages ?? []);
      setGenerating(false);
    },
    onError: () => setGenerating(false),
  });
}

export function useValidateAssembly() {
  const { setAssemblyValid, setValidationMessages } = useInsertStore();
  return useMutation({
    mutationFn: async (params: {
      model_id: string;
      insert_id: string;
      mold_id?: string;
    }) => {
      const res = await fetch(`${API}/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      return checkedJson(res);
    },
    onSuccess: (data) => {
      setAssemblyValid(data.assembly_valid ?? false);
      setValidationMessages(data.messages ?? []);
    },
  });
}
