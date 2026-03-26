import { useMutation } from "@tanstack/react-query";

const API = "/api/v1/advanced";

async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

// ── Mesh Boolean ────────────────────────────────────────────────────

export interface BooleanResult {
  result_id: string;
  operation: string;
  blend_radius: number;
  vertices: number;
  faces: number;
}

export function useMeshBoolean() {
  return useMutation({
    mutationFn: async (params: {
      modelAId: string;
      modelBId: string;
      operation: string;
      blendRadius?: number;
    }) =>
      postJson<BooleanResult>(`${API}/boolean`, {
        model_a_id: params.modelAId,
        model_b_id: params.modelBId,
        operation: params.operation,
        blend_radius: params.blendRadius ?? 0,
      }),
  });
}

// ── Topology Optimisation ───────────────────────────────────────────

export interface TOResult2D {
  iterations: number;
  final_compliance: number;
  final_volfrac: number;
  compliance_history: number[];
  density: number[][];
}

export function useTopologyOpt2D() {
  return useMutation({
    mutationFn: async (params: {
      nelx?: number;
      nely?: number;
      volfrac?: number;
      penal?: number;
      rmin?: number;
      bcType?: string;
      maxIter?: number;
    }) =>
      postJson<TOResult2D>(`${API}/topology-opt/2d`, {
        nelx: params.nelx ?? 60,
        nely: params.nely ?? 30,
        volfrac: params.volfrac ?? 0.4,
        penal: params.penal ?? 3.0,
        rmin: params.rmin ?? 1.5,
        bc_type: params.bcType ?? "cantilever",
        max_iter: params.maxIter ?? 100,
      }),
  });
}

export interface TOResult3D {
  iterations: number;
  final_compliance: number;
  final_volfrac: number;
  compliance_history: number[];
  density_shape: number[];
}

export function useTopologyOpt3D() {
  return useMutation({
    mutationFn: async (params: {
      nelx?: number;
      nely?: number;
      nelz?: number;
      volfrac?: number;
      bcType?: string;
    }) =>
      postJson<TOResult3D>(`${API}/topology-opt/3d`, {
        nelx: params.nelx ?? 20,
        nely: params.nely ?? 10,
        nelz: params.nelz ?? 10,
        volfrac: params.volfrac ?? 0.3,
        bc_type: params.bcType ?? "cantilever",
      }),
  });
}

// ── Lattice Generation ──────────────────────────────────────────────

export interface LatticeResult {
  result_id: string;
  lattice_type: string;
  cell_count: number;
  beam_count: number;
  volume_fraction: number;
  vertices: number;
  faces: number;
}

export function useGenerateLattice() {
  return useMutation({
    mutationFn: async (params: {
      modelId: string;
      latticeType?: string;
      cellType?: string;
      tpmsType?: string;
      cellSize?: number;
      beamRadius?: number;
      wallThickness?: number;
      variableThickness?: boolean;
      thicknessField?: string;
      resolution?: number;
      nCells?: number;
    }) =>
      postJson<LatticeResult>(`${API}/lattice/generate`, {
        model_id: params.modelId,
        lattice_type: params.latticeType ?? "tpms",
        cell_type: params.cellType ?? "bcc",
        tpms_type: params.tpmsType ?? "gyroid",
        cell_size: params.cellSize ?? 5.0,
        beam_radius: params.beamRadius ?? 0.5,
        wall_thickness: params.wallThickness ?? 0.5,
        variable_thickness: params.variableThickness ?? false,
        thickness_field: params.thicknessField ?? "uniform",
        resolution: params.resolution ?? 80,
        n_cells: params.nCells ?? 200,
      }),
  });
}

// ── Interference / Clearance ────────────────────────────────────────

export interface InterferenceResult {
  interference_detected: boolean;
  min_clearance: number;
  max_clearance: number;
  mean_clearance: number;
  interference_volume: number;
  interference_faces_a: number;
  interference_faces_b: number;
  histogram: Array<{ bin_start: number; bin_end: number; count: number }>;
}

export function useInterferenceCheck() {
  return useMutation({
    mutationFn: async (params: {
      modelAId: string;
      modelBId: string;
      sampleCount?: number;
    }) =>
      postJson<InterferenceResult>(`${API}/interference/check`, {
        model_a_id: params.modelAId,
        model_b_id: params.modelBId,
        sample_count: params.sampleCount ?? 5000,
      }),
  });
}

export interface AssemblyCheckResult {
  all_clear: boolean;
  total_interference_volume: number;
  checks: Array<{
    part_a: string;
    part_b: string;
    status: string;
    min_clearance?: number;
    max_clearance?: number;
    mean_clearance?: number;
    interference_volume?: number;
    error?: string;
  }>;
}

export function useAssemblyCheck() {
  return useMutation({
    mutationFn: async (params: {
      modelIds: string[];
      minClearance?: number;
    }) =>
      postJson<AssemblyCheckResult>(`${API}/interference/assembly`, {
        model_ids: params.modelIds,
        min_clearance: params.minClearance ?? 0.5,
      }),
  });
}

// ── Mesh Quality ────────────────────────────────────────────────────

export interface MeshQualityResult {
  model_id: string;
  n_vertices: number;
  n_faces: number;
  n_edges: number;
  aspect_ratio_mean: number;
  aspect_ratio_max: number;
  skinny_triangle_count: number;
  skinny_fraction: number;
  degenerate_face_count: number;
  edge_length: { min: number; max: number; mean: number; std: number };
  area: { min: number; max: number; mean: number };
  topology: {
    is_watertight: boolean;
    is_manifold: boolean;
    euler_characteristic: number;
    genus: number;
  };
  volume: number;
  surface_area: number;
  compactness: number;
  histograms: {
    aspect_ratio: Array<{ bin_start: number; bin_end: number; count: number }>;
    edge_length: Array<{ bin_start: number; bin_end: number; count: number }>;
    min_angle: Array<{ bin_start: number; bin_end: number; count: number }>;
  };
}

export function useMeshQuality() {
  return useMutation({
    mutationFn: async (params: { modelId: string }) =>
      postJson<MeshQualityResult>(`${API}/${params.modelId}/mesh-quality`),
  });
}

// ── SDF / Variable Shell ────────────────────────────────────────────

export interface VariableShellResult {
  result_id: string;
  min_thickness: number;
  max_thickness: number;
  mean_thickness: number;
  vertices: number;
  faces: number;
}

export function useVariableShell() {
  return useMutation({
    mutationFn: async (params: {
      modelId: string;
      baseThickness?: number;
      thicknessVariation?: number;
      fieldType?: string;
      resolution?: number;
    }) =>
      postJson<VariableShellResult>(`${API}/sdf/variable-shell`, {
        model_id: params.modelId,
        base_thickness: params.baseThickness ?? 2.0,
        thickness_variation: params.thicknessVariation ?? 1.0,
        field_type: params.fieldType ?? "distance_from_center",
        resolution: params.resolution ?? 64,
      }),
  });
}
