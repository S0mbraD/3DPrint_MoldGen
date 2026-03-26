import { create } from "zustand";

export interface MeshInfo {
  vertex_count: number;
  face_count: number;
  bounds_min: number[];
  bounds_max: number[];
  extents: number[];
  center: number[];
  is_watertight: boolean;
  volume: number | null;
  surface_area: number;
  unit: string;
  source_format: string;
}

interface ModelState {
  modelId: string | null;
  filename: string | null;
  meshInfo: MeshInfo | null;
  glbUrl: string | null;
  glbRevision: number;
  isLoading: boolean;

  setModel: (id: string, filename: string, info: MeshInfo) => void;
  updateMeshInfo: (info: MeshInfo) => void;
  setGlbUrl: (url: string) => void;
  bumpGlbRevision: () => void;
  setLoading: (v: boolean) => void;
  clearModel: () => void;
}

export const useModelStore = create<ModelState>((set) => ({
  modelId: null,
  filename: null,
  meshInfo: null,
  glbUrl: null,
  glbRevision: 0,
  isLoading: false,

  setModel: (id, filename, info) => {
    set({
      modelId: id,
      filename,
      meshInfo: info,
      glbUrl: `/api/v1/models/${id}/glb`,
      glbRevision: 0,
      isLoading: false,
    });
    _syncToApp(filename, info.face_count);
  },
  updateMeshInfo: (info) => {
    set({ meshInfo: info });
    const state = useModelStore.getState();
    if (state.filename) _syncToApp(state.filename, info.face_count);
  },
  setGlbUrl: (url) => set({ glbUrl: url }),
  bumpGlbRevision: () => set((s) => ({
    glbRevision: s.glbRevision + 1,
    glbUrl: `/api/v1/models/${s.modelId}/glb?v=${s.glbRevision + 1}`,
  })),
  setLoading: (v) => set({ isLoading: v }),
  clearModel: () => {
    set({
      modelId: null,
      filename: null,
      meshInfo: null,
      glbUrl: null,
      glbRevision: 0,
    });
    import("./appStore").then(({ useAppStore }) => useAppStore.getState().clearModelInfo());
  },
}));

function _syncToApp(filename: string, faceCount: number) {
  import("./appStore").then(({ useAppStore }) => useAppStore.getState().setModelInfo(filename, faceCount));
}
