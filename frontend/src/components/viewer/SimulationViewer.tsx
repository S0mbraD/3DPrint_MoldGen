import { useRef, useMemo, useEffect, useLayoutEffect } from "react";
import { useFrame, useLoader } from "@react-three/fiber";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { useSimStore, type HeatmapField, type SimColorPalette, type VisualizationData } from "../../stores/simStore";
import { useModelStore } from "../../stores/modelStore";
import { cn } from "../../lib/utils";

/* ═══════════════════════════════════════════════════════════════════
 *  GLSL Shaders — point cloud heatmap
 * ═══════════════════════════════════════════════════════════════════ */

const VERTEX_SHADER = /* glsl */ `
  attribute float aFillTime;
  attribute float aPressure;
  attribute float aVelocity;
  attribute float aShearRate;
  attribute float aTemperature;
  attribute float aCureProgress;
  attribute float aThickness;

  uniform int uColorMode;
  uniform float uAnimProgress;
  uniform float uPointSize;
  uniform float uOpacity;

  varying float vValue;
  varying float vVisible;
  varying float vOpacity;

  void main() {
    float value = 0.0;
    if (uColorMode == 0) value = aFillTime;
    else if (uColorMode == 1) value = aPressure;
    else if (uColorMode == 2) value = aVelocity;
    else if (uColorMode == 3) value = aShearRate;
    else if (uColorMode == 4) value = aTemperature;
    else if (uColorMode == 5) value = aCureProgress;
    else if (uColorMode == 6) value = aThickness;

    vValue = value;
    vVisible = (aFillTime <= uAnimProgress) ? 1.0 : 0.0;
    vOpacity = uOpacity;

    float fadeDelta = uAnimProgress - aFillTime;
    if (fadeDelta >= 0.0 && fadeDelta < 0.05) {
      vOpacity *= fadeDelta / 0.05;
    }

    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = uPointSize * (300.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const FRAGMENT_SHADER = /* glsl */ `
  varying float vValue;
  varying float vVisible;
  varying float vOpacity;

  uniform float uValueMin;
  uniform float uValueMax;
  uniform int uPalette;

  float normField() {
    float d = uValueMax - uValueMin;
    if (abs(d) < 1.0e-20) return 0.5;
    return clamp((vValue - uValueMin) / d, 0.0, 1.0);
  }

  vec3 lerp5(float t, vec3 a, vec3 b, vec3 c, vec3 d, vec3 e) {
    t = clamp(t, 0.0, 1.0);
    if (t >= 1.0) return e;
    float x = t * 4.0;
    int i = int(floor(x));
    float f = x - float(i);
    if (i <= 0) return mix(a, b, f);
    if (i == 1) return mix(b, c, f);
    if (i == 2) return mix(c, d, f);
    return mix(d, e, f);
  }

  vec3 cmapJet(float t) {
    return lerp5(t,
      vec3(0.0, 0.0, 0.55),
      vec3(0.0, 0.0, 1.0),
      vec3(0.0, 1.0, 1.0),
      vec3(1.0, 1.0, 0.0),
      vec3(0.55, 0.0, 0.0));
  }

  vec3 cmapCoolwarm(float t) {
    return lerp5(t,
      vec3(0.23, 0.30, 0.75),
      vec3(0.47, 0.55, 0.88),
      vec3(0.88, 0.88, 0.88),
      vec3(0.88, 0.52, 0.42),
      vec3(0.71, 0.02, 0.15));
  }

  vec3 cmapViridis(float t) {
    return lerp5(t,
      vec3(0.267, 0.004, 0.329),
      vec3(0.282, 0.141, 0.458),
      vec3(0.128, 0.567, 0.551),
      vec3(0.369, 0.788, 0.383),
      vec3(0.993, 0.906, 0.144));
  }

  vec3 cmapTurbo(float t) {
    return lerp5(t,
      vec3(0.05, 0.15, 0.65),
      vec3(0.15, 0.75, 0.95),
      vec3(0.25, 0.90, 0.35),
      vec3(0.95, 0.85, 0.12),
      vec3(0.80, 0.10, 0.05));
  }

  vec3 cmapRainbow(float t) {
    return lerp5(t,
      vec3(0.05, 0.05, 0.75),
      vec3(0.0, 0.65, 0.95),
      vec3(0.15, 0.85, 0.20),
      vec3(0.98, 0.88, 0.10),
      vec3(0.92, 0.12, 0.05));
  }

  vec3 paletteColor(float t) {
    if (uPalette == 0) return cmapJet(t);
    if (uPalette == 1) return cmapCoolwarm(t);
    if (uPalette == 2) return cmapViridis(t);
    if (uPalette == 3) return cmapTurbo(t);
    return cmapRainbow(t);
  }

  void main() {
    if (vVisible < 0.5) discard;

    vec2 cxy = 2.0 * gl_PointCoord - 1.0;
    float r = dot(cxy, cxy);
    if (r > 1.0) discard;

    float rr = sqrt(r);
    float alpha = vOpacity * exp(-rr * rr * 2.5);

    float tn = normField();
    vec3 color = paletteColor(tn);

    float highlight = exp(-rr * rr * 8.0) * 0.25;
    color += vec3(highlight);

    color *= 1.0 - rr * 0.15;

    gl_FragColor = vec4(color, alpha);
  }
`;

const FIELD_INDEX: Record<HeatmapField, number> = {
  fill_time: 0,
  pressure: 1,
  velocity: 2,
  shear_rate: 3,
  temperature: 4,
  cure_progress: 5,
  thickness: 6,
};

const PALETTE_INDEX: Record<SimColorPalette, number> = {
  jet: 0,
  coolwarm: 1,
  viridis: 2,
  turbo: 3,
  rainbow: 4,
};

/**
 * Shader normalization range: backend already normalizes all field
 * attributes to [0,1], so the shader just needs identity mapping.
 */
function heatmapValueRange(_field: HeatmapField, _vis: VisualizationData): { min: number; max: number } {
  return { min: 0, max: 1 };
}

/**
 * Physical value range for legend display (real units).
 */
export function heatmapPhysicalRange(field: HeatmapField, vis: VisualizationData): { min: number; max: number; unit: string } {
  switch (field) {
    case "fill_time":
      return { min: 0, max: Math.max(vis.max_fill_time, 1e-6), unit: "s" };
    case "pressure":
      return { min: 0, max: Math.max(vis.max_pressure, 1e-6), unit: "Pa" };
    case "velocity":
      return { min: 0, max: Math.max(vis.max_velocity, 1e-6), unit: "mm/s" };
    case "shear_rate":
      return { min: 0, max: Math.max(vis.max_shear_rate, 1e-6), unit: "1/s" };
    case "temperature": {
      const [a, b] = vis.temperature_range;
      return { min: Math.min(a, b), max: Math.max(a, b, Math.min(a, b) + 1e-6), unit: "\u00b0C" };
    }
    case "cure_progress":
      return { min: 0, max: 100, unit: "%" };
    case "thickness":
      return { min: 0, max: Math.max(vis.max_thickness, 1e-6), unit: "mm" };
    default:
      return { min: 0, max: 1, unit: "" };
  }
}

/** Matches fragment shader piecewise palettes for HTML/arrow coloring */
export function sampleSimPalette(t: number, palette: SimColorPalette): [number, number, number] {
  const x = Math.max(0, Math.min(1, t));
  const lerp5 = (
    tt: number,
    a: [number, number, number],
    b: [number, number, number],
    c: [number, number, number],
    d: [number, number, number],
    e: [number, number, number],
  ): [number, number, number] => {
    if (tt >= 1) return e;
    const u = tt * 4;
    const i = Math.min(3, Math.floor(u));
    const f = u - i;
    const stops = [a, b, c, d, e];
    const p0 = stops[i];
    const p1 = stops[i + 1];
    return [
      p0[0] + (p1[0] - p0[0]) * f,
      p0[1] + (p1[1] - p0[1]) * f,
      p0[2] + (p1[2] - p0[2]) * f,
    ];
  };

  const jet: [[number, number, number], ...[number, number, number][]] = [
    [0, 0, 0.55], [0, 0, 1], [0, 1, 1], [1, 1, 0], [0.55, 0, 0],
  ];
  const coolwarm: [[number, number, number], ...[number, number, number][]] = [
    [0.23, 0.3, 0.75], [0.47, 0.55, 0.88], [0.88, 0.88, 0.88],
    [0.88, 0.52, 0.42], [0.71, 0.02, 0.15],
  ];
  const viridis: [[number, number, number], ...[number, number, number][]] = [
    [0.267, 0.004, 0.329], [0.282, 0.141, 0.458], [0.128, 0.567, 0.551],
    [0.369, 0.788, 0.383], [0.993, 0.906, 0.144],
  ];
  const turbo: [[number, number, number], ...[number, number, number][]] = [
    [0.05, 0.15, 0.65], [0.15, 0.75, 0.95], [0.25, 0.9, 0.35],
    [0.95, 0.85, 0.12], [0.8, 0.1, 0.05],
  ];
  const rainbow: [[number, number, number], ...[number, number, number][]] = [
    [0.05, 0.05, 0.75], [0, 0.65, 0.95], [0.15, 0.85, 0.2],
    [0.98, 0.88, 0.1], [0.92, 0.12, 0.05],
  ];

  const table: Record<SimColorPalette, typeof jet> = {
    jet, coolwarm, viridis, turbo, rainbow,
  };
  const [a, b, c, d, e] = table[palette];
  return lerp5(x, a, b, c, d, e);
}

export function simPaletteCssGradient(palette: SimColorPalette, vertical = false): string {
  const stops = [0, 0.25, 0.5, 0.75, 1].map((t) => {
    const [r, g, b] = sampleSimPalette(t, palette);
    const R = Math.round(r * 255);
    const G = Math.round(g * 255);
    const B = Math.round(b * 255);
    return `rgb(${R},${G},${B}) ${(t * 100).toFixed(1)}%`;
  });
  const dir = vertical ? "to top" : "to right";
  return `linear-gradient(${dir}, ${stops.join(", ")})`;
}

/* ═══════════════════════════════════════════════════════════════════
 *  SimulationViewer — point cloud with optional density multiplier
 * ═══════════════════════════════════════════════════════════════════ */

export function SimulationViewer() {
  const visData = useSimStore((s) => s.visualizationData);
  const heatmapField = useSimStore((s) => s.heatmapField);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const heatmapOpacity = useSimStore((s) => s.heatmapOpacity);
  const pointSize = useSimStore((s) => s.pointSize);
  const animProgress = useSimStore((s) => s.animationProgress);
  const animPlaying = useSimStore((s) => s.animationPlaying);
  const animSpeed = useSimStore((s) => s.animationSpeed);
  const animLoop = useSimStore((s) => s.animationLoop);
  const setAnimProgress = useSimStore((s) => s.setAnimationProgress);
  const setAnimPlaying = useSimStore((s) => s.setAnimationPlaying);
  const particleDensity = useSimStore((s) => s.particleDensity);
  const colorPalette = useSimStore((s) => s.colorPalette);

  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const geometry = useMemo(() => {
    if (!visData || visData.n_points === 0) return null;

    const geo = new THREE.BufferGeometry();
    const srcN = visData.n_points;
    const density = Math.max(1, Math.min(particleDensity, 4));

    if (density <= 1) {
      const positions = new Float32Array(srcN * 3);
      for (let i = 0; i < srcN; i++) {
        positions[i * 3] = visData.positions[i][0];
        positions[i * 3 + 1] = visData.positions[i][1];
        positions[i * 3 + 2] = visData.positions[i][2];
      }
      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));

      const setAttr = (name: string, data: number[]) => {
        const arr = new Float32Array(srcN);
        for (let i = 0; i < srcN; i++) arr[i] = data[i] ?? 0;
        geo.setAttribute(name, new THREE.BufferAttribute(arr, 1));
      };

      setAttr("aFillTime", visData.fill_times);
      setAttr("aPressure", visData.pressures);
      setAttr("aVelocity", visData.velocities);
      setAttr("aShearRate", visData.shear_rates);
      setAttr("aTemperature", visData.temperatures);
      setAttr("aCureProgress", visData.cure_progress);
      setAttr("aThickness", visData.thickness);
    } else {
      const totalN = srcN * density;
      const positions = new Float32Array(totalN * 3);
      const fillTimes = new Float32Array(totalN);
      const pressures = new Float32Array(totalN);
      const velocities = new Float32Array(totalN);
      const shearRates = new Float32Array(totalN);
      const temperatures = new Float32Array(totalN);
      const cureProgress = new Float32Array(totalN);
      const thickness = new Float32Array(totalN);
      const pitch = visData.voxel_pitch || 1;
      const jitter = pitch * 0.35;

      for (let i = 0; i < srcN; i++) {
        const bx = visData.positions[i][0];
        const by = visData.positions[i][1];
        const bz = visData.positions[i][2];
        const ft = visData.fill_times[i] ?? 0;
        const pr = visData.pressures[i] ?? 0;
        const vl = visData.velocities[i] ?? 0;
        const sr = visData.shear_rates[i] ?? 0;
        const tp = visData.temperatures[i] ?? 0;
        const cp = visData.cure_progress[i] ?? 0;
        const th = visData.thickness[i] ?? 0;

        for (let d = 0; d < density; d++) {
          const idx = i * density + d;
          if (d === 0) {
            positions[idx * 3] = bx;
            positions[idx * 3 + 1] = by;
            positions[idx * 3 + 2] = bz;
          } else {
            positions[idx * 3] = bx + (Math.random() - 0.5) * jitter;
            positions[idx * 3 + 1] = by + (Math.random() - 0.5) * jitter;
            positions[idx * 3 + 2] = bz + (Math.random() - 0.5) * jitter;
          }
          fillTimes[idx] = ft;
          pressures[idx] = pr;
          velocities[idx] = vl;
          shearRates[idx] = sr;
          temperatures[idx] = tp;
          cureProgress[idx] = cp;
          thickness[idx] = th;
        }
      }

      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geo.setAttribute("aFillTime", new THREE.BufferAttribute(fillTimes, 1));
      geo.setAttribute("aPressure", new THREE.BufferAttribute(pressures, 1));
      geo.setAttribute("aVelocity", new THREE.BufferAttribute(velocities, 1));
      geo.setAttribute("aShearRate", new THREE.BufferAttribute(shearRates, 1));
      geo.setAttribute("aTemperature", new THREE.BufferAttribute(temperatures, 1));
      geo.setAttribute("aCureProgress", new THREE.BufferAttribute(cureProgress, 1));
      geo.setAttribute("aThickness", new THREE.BufferAttribute(thickness, 1));
    }

    geo.computeBoundingBox();
    geo.computeBoundingSphere();
    return geo;
  }, [visData, particleDensity]);

  const shaderMaterial = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: VERTEX_SHADER,
        fragmentShader: FRAGMENT_SHADER,
        uniforms: {
          uColorMode: { value: FIELD_INDEX[heatmapField] },
          uAnimProgress: { value: animProgress },
          uPointSize: { value: pointSize },
          uOpacity: { value: heatmapOpacity },
          uValueMin: { value: 0 },
          uValueMax: { value: 1 },
          uPalette: { value: PALETTE_INDEX.jet },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visData, particleDensity],
  );

  useEffect(() => {
    materialRef.current = shaderMaterial;
  }, [shaderMaterial]);

  useFrame((_, delta) => {
    const mat = materialRef.current;
    if (!mat) return;

    mat.uniforms.uColorMode.value = FIELD_INDEX[heatmapField];
    mat.uniforms.uPointSize.value = pointSize;
    mat.uniforms.uOpacity.value = heatmapOpacity;
    mat.uniforms.uPalette.value = PALETTE_INDEX[colorPalette];
    if (visData) {
      const { min, max } = heatmapValueRange(heatmapField, visData);
      mat.uniforms.uValueMin.value = min;
      mat.uniforms.uValueMax.value = max;
    }

    if (animPlaying) {
      const next = animProgress + delta * animSpeed * 0.3;
      if (next >= 1.0) {
        if (animLoop) {
          setAnimProgress(0);
        } else {
          setAnimProgress(1.0);
          setAnimPlaying(false);
        }
      } else {
        setAnimProgress(next);
      }
    }

    mat.uniforms.uAnimProgress.value = animProgress;
  });

  if (!heatmapVisible || !geometry || !visData) return null;

  return (
    <points geometry={geometry} material={shaderMaterial} />
  );
}

/* ═══════════════════════════════════════════════════════════════════
 *  StreamlineViewer — flow streamlines from fill-time gradient
 * ═══════════════════════════════════════════════════════════════════ */

function buildSpatialGrid(
  pos: number[][],
  cellSize: number,
): { grid: Map<string, number[]>; key: (x: number, y: number, z: number) => string } {
  const grid = new Map<string, number[]>();
  const key = (x: number, y: number, z: number) =>
    `${Math.floor(x / cellSize)},${Math.floor(y / cellSize)},${Math.floor(z / cellSize)}`;

  for (let i = 0; i < pos.length; i++) {
    const k = key(pos[i][0], pos[i][1], pos[i][2]);
    let bucket = grid.get(k);
    if (!bucket) {
      bucket = [];
      grid.set(k, bucket);
    }
    bucket.push(i);
  }
  return { grid, key };
}

function getNeighborIndices(
  grid: Map<string, number[]>,
  cx: number,
  cy: number,
  cz: number,
  cellSize: number,
): number[] {
  const result: number[] = [];
  const ix = Math.floor(cx / cellSize);
  const iy = Math.floor(cy / cellSize);
  const iz = Math.floor(cz / cellSize);
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      for (let dz = -1; dz <= 1; dz++) {
        const bucket = grid.get(`${ix + dx},${iy + dy},${iz + dz}`);
        if (bucket) {
          for (let k = 0; k < bucket.length; k++) result.push(bucket[k]);
        }
      }
    }
  }
  return result;
}

function nearestVoxelIndex(
  px: number, py: number, pz: number,
  pos: number[][],
  grid: Map<string, number[]>,
  cellSize: number,
): number {
  let best = -1;
  let bestD = Infinity;
  const neighbors = getNeighborIndices(grid, px, py, pz, cellSize);
  for (const j of neighbors) {
    const q = pos[j];
    const dx = q[0] - px;
    const dy = q[1] - py;
    const dz = q[2] - pz;
    const d = dx * dx + dy * dy + dz * dz;
    if (d < bestD) {
      bestD = d;
      best = j;
    }
  }
  return best;
}

const FLOW_PARTICLE_TRAIL = 4;
const FLOW_PARTICLE_MAX = 300;

type FlowParticleConfig = {
  path: THREE.Vector3[];
  cumLen: number[];
  totalLen: number;
  fillAtVert: number[];
  speedMul: number;
};

function buildCumulativeLengths(path: THREE.Vector3[]): { cumLen: number[]; totalLen: number } {
  const cumLen: number[] = [0];
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    total += path[i - 1]!.distanceTo(path[i]!);
    cumLen.push(total);
  }
  if (total < 1e-12) total = 1e-12;
  return { cumLen, totalLen: total };
}

function positionOnPath(
  path: THREE.Vector3[],
  cumLen: number[],
  totalLen: number,
  t: number,
  target: THREE.Vector3,
): void {
  const u = Math.max(0, Math.min(1, t)) * totalLen;
  let seg = 0;
  for (let i = 0; i < cumLen.length - 1; i++) {
    if (u <= cumLen[i + 1]!) {
      seg = i;
      break;
    }
    seg = i;
  }
  seg = Math.min(seg, path.length - 2);
  const s0 = cumLen[seg]!;
  const s1 = cumLen[seg + 1]!;
  const span = Math.max(1e-12, s1 - s0);
  const w = (u - s0) / span;
  target.copy(path[seg]!).lerp(path[seg + 1]!, w);
}

function fillTimeOnPath(fillAtVert: number[], cumLen: number[], totalLen: number, t: number): number {
  const u = Math.max(0, Math.min(1, t)) * totalLen;
  let seg = 0;
  for (let i = 0; i < cumLen.length - 1; i++) {
    if (u <= cumLen[i + 1]!) {
      seg = i;
      break;
    }
    seg = i;
  }
  seg = Math.min(seg, fillAtVert.length - 2);
  const s0 = cumLen[seg]!;
  const s1 = cumLen[seg + 1]!;
  const span = Math.max(1e-12, s1 - s0);
  const w = (u - s0) / span;
  return fillAtVert[seg]! * (1 - w) + fillAtVert[seg + 1]! * w;
}

function scalarAtVoxelIndex(j: number, field: HeatmapField, vis: VisualizationData): number {
  if (j < 0) return 0;
  switch (field) {
    case "fill_time": return vis.fill_times[j] ?? 0;
    case "pressure": return vis.pressures[j] ?? 0;
    case "velocity": return vis.velocities[j] ?? 0;
    case "shear_rate": return vis.shear_rates[j] ?? 0;
    case "temperature": return vis.temperatures[j] ?? 0;
    case "cure_progress": return vis.cure_progress[j] ?? 0;
    case "thickness": return vis.thickness[j] ?? 0;
    default: return vis.fill_times[j] ?? 0;
  }
}

export function FlowParticles() {
  const visData = useSimStore((s) => s.visualizationData);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const showFlowParticles = useSimStore((s) => s.showFlowParticles);
  const heatmapField = useSimStore((s) => s.heatmapField);
  const colorPalette = useSimStore((s) => s.colorPalette);
  const animProgress = useSimStore((s) => s.animationProgress);
  const flowParticleCount = useSimStore((s) => s.flowParticleCount);
  const flowParticleSpeed = useSimStore((s) => s.flowParticleSpeed);
  const flowParticleSize = useSimStore((s) => s.flowParticleSize);

  const instancedRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const scratch = useMemo(() => new THREE.Vector3(), []);
  const samplePos = useMemo(() => new THREE.Vector3(), []);
  const colorTmp = useMemo(() => new THREE.Color(), []);

  const spatial = useMemo(() => {
    if (!visData) return null;
    const pitch = visData.voxel_pitch || 1;
    const cellSize = pitch * 3.0;
    const { grid } = buildSpatialGrid(visData.positions, cellSize);
    return { grid, cellSize };
  }, [visData]);

  const particleConfigs = useMemo((): FlowParticleConfig[] => {
    if (!visData || visData.n_points < 1 || !spatial) return [];

    const posArr = visData.positions;
    const ftArr = visData.fill_times;
    const pitch = visData.voxel_pitch || 1;
    const { grid, cellSize } = spatial;

    const cap = Math.min(FLOW_PARTICLE_MAX, Math.max(1, flowParticleCount));
    const out: FlowParticleConfig[] = [];

    const backend = visData.particle_paths;
    if (backend?.length) {
      const useN = Math.min(cap, backend.length);
      const step = Math.max(1, Math.floor(backend.length / useN));
      for (let i = 0; i < backend.length && out.length < useN; i += step) {
        const entry = backend[i]!;
        const raw = entry.path;
        if (!raw || raw.length < 2) continue;
        const path = raw.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
        const { cumLen, totalLen } = buildCumulativeLengths(path);
        const fillAtVert = path.map((v) => {
          const idx = nearestVoxelIndex(v.x, v.y, v.z, posArr, grid, cellSize);
          return idx >= 0 ? (ftArr[idx] ?? 0) : 0;
        });
        out.push({
          path, cumLen, totalLen, fillAtVert,
          speedMul: Math.max(0.25, entry.speed || 1),
        });
      }
      return out;
    }

    const vv = visData.velocity_vectors;
    if (!vv?.length) return [];

    const useN = Math.min(cap, vv.length);
    const step = Math.max(1, Math.floor(vv.length / useN));
    const segLen = pitch * 4;

    for (let i = 0; i < vv.length && out.length < useN; i += step) {
      const { pos, dir } = vv[i]!;
      const dx = dir[0], dy = dir[1], dz = dir[2];
      const mag = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1e-12;
      const ux = dx / mag, uy = dy / mag, uz = dz / mag;
      const p0 = new THREE.Vector3(pos[0], pos[1], pos[2]);
      const p1 = new THREE.Vector3(
        pos[0] + ux * segLen,
        pos[1] + uy * segLen,
        pos[2] + uz * segLen,
      );
      const path = [p0, p1];
      const { cumLen, totalLen } = buildCumulativeLengths(path);
      const fillAtVert = path.map((v) => {
        const idx = nearestVoxelIndex(v.x, v.y, v.z, posArr, grid, cellSize);
        return idx >= 0 ? (ftArr[idx] ?? 0) : 0;
      });
      out.push({ path, cumLen, totalLen, fillAtVert, speedMul: 1 });
    }

    return out;
  }, [visData, flowParticleCount, spatial]);

  const particleTRef = useRef<number[]>([]);
  const trailRef = useRef<THREE.Vector3[][]>([]);

  useLayoutEffect(() => {
    const n = particleConfigs.length;
    const tArr = particleTRef.current;
    const tr = trailRef.current;
    tArr.length = n;
    tr.length = n;
    for (let i = 0; i < n; i++) {
      tArr[i] = (i * 0.137) % 1;
      const cfg = particleConfigs[i]!;
      tr[i] = [];
      for (let k = 0; k < FLOW_PARTICLE_TRAIL; k++) {
        tr[i]![k] = new THREE.Vector3();
        positionOnPath(cfg.path, cfg.cumLen, cfg.totalLen, tArr[i]!, tr[i]![k]!);
      }
    }
  }, [particleConfigs]);

  const baseRadius = useMemo(() => {
    const pitch = visData?.voxel_pitch || 1;
    return 0.3 * pitch * (flowParticleSize / 2);
  }, [visData?.voxel_pitch, flowParticleSize]);

  const sphereGeo = useMemo(() => new THREE.SphereGeometry(1, 10, 10), []);

  const sphereMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        vertexColors: true,
        toneMapped: false,
        transparent: true,
        opacity: 1,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    [],
  );

  useEffect(() => {
    return () => {
      sphereGeo.dispose();
      sphereMat.dispose();
    };
  }, [sphereGeo, sphereMat]);

  useFrame((_, delta) => {
    const mesh = instancedRef.current;
    if (!mesh || particleConfigs.length === 0 || !visData || !spatial) return;

    const tArr = particleTRef.current;
    const tr = trailRef.current;
    const advance = delta * flowParticleSpeed * 0.45;
    const { min, max } = heatmapValueRange(heatmapField, visData);
    const range = Math.max(max - min, 1e-20);
    const { grid, cellSize } = spatial;

    const n = particleConfigs.length;
    const instTotal = n * FLOW_PARTICLE_TRAIL;

    for (let i = 0; i < n; i++) {
      const cfg = particleConfigs[i]!;
      tArr[i] = (tArr[i] ?? 0) + advance * cfg.speedMul;
      while (tArr[i]! >= 1) tArr[i]! -= 1;

      positionOnPath(cfg.path, cfg.cumLen, cfg.totalLen, tArr[i]!, scratch);
      const row = tr[i]!;
      for (let k = FLOW_PARTICLE_TRAIL - 1; k > 0; k--) {
        row[k]!.copy(row[k - 1]!);
      }
      row[0]!.copy(scratch);

      for (let k = 0; k < FLOW_PARTICLE_TRAIL; k++) {
        const idx = i * FLOW_PARTICLE_TRAIL + k;
        const posK = row[k]!;
        const tTrail = Math.max(0, tArr[i]! - k * 0.035);
        const fillK = fillTimeOnPath(cfg.fillAtVert, cfg.cumLen, cfg.totalLen, tTrail);

        if (fillK > animProgress + 1e-6) {
          dummy.position.set(0, 0, -1e6);
          dummy.scale.setScalar(0);
        } else {
          dummy.position.copy(posK);
          const age = k / FLOW_PARTICLE_TRAIL;
          dummy.scale.setScalar(baseRadius * (1.0 - age * 0.35));
        }
        dummy.updateMatrix();
        mesh.setMatrixAt(idx, dummy.matrix);

        if (heatmapField === "fill_time") {
          samplePos.copy(posK);
        } else {
          positionOnPath(cfg.path, cfg.cumLen, cfg.totalLen, tTrail, samplePos);
        }
        const vj = nearestVoxelIndex(
          samplePos.x, samplePos.y, samplePos.z,
          visData.positions, grid, cellSize,
        );
        const raw = scalarAtVoxelIndex(vj, heatmapField, visData);
        const paletteT = Math.max(0, Math.min(1, (raw - min) / range));
        const [r0, g0, b0] = sampleSimPalette(paletteT, colorPalette);
        const age = k / FLOW_PARTICLE_TRAIL;
        const dim = 1.0 - age * 0.55;
        colorTmp.setRGB(r0 * dim, g0 * dim, b0 * dim);
        mesh.setColorAt(idx, colorTmp);
      }
    }

    mesh.count = instTotal;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });

  if (!showFlowParticles || !heatmapVisible || !visData || particleConfigs.length === 0) {
    return null;
  }

  const maxInst = FLOW_PARTICLE_MAX * FLOW_PARTICLE_TRAIL;

  return (
    <instancedMesh
      ref={instancedRef}
      args={[sphereGeo, sphereMat, maxInst]}
      frustumCulled={false}
    />
  );
}

const FLOW_FRONT_VERTEX = /* glsl */ `
  attribute float aFillTime;
  attribute float aValue;

  uniform float uAnimProgress;
  uniform float uTime;
  uniform float uPointSize;

  varying float vValue;
  varying float vEdgeFactor;

  void main() {
    float dt = abs(aFillTime - uAnimProgress);
    float frontWidth = 0.04;
    vEdgeFactor = 1.0 - smoothstep(0.0, frontWidth, dt);
    if (vEdgeFactor < 0.01) {
      gl_Position = vec4(0.0, 0.0, -2.0, 1.0);
      return;
    }

    vValue = aValue;

    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float pulse = 1.0 + 0.3 * sin(uTime * 4.0);
    gl_PointSize = uPointSize * 2.5 * pulse * vEdgeFactor * (300.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

const FLOW_FRONT_FRAGMENT = /* glsl */ `
  varying float vValue;
  varying float vEdgeFactor;

  uniform float uValueMin;
  uniform float uValueMax;
  uniform int uPalette;

  float normField() {
    float d = uValueMax - uValueMin;
    if (abs(d) < 1.0e-20) return 0.5;
    return clamp((vValue - uValueMin) / d, 0.0, 1.0);
  }

  vec3 lerp5(float t, vec3 a, vec3 b, vec3 c, vec3 d, vec3 e) {
    t = clamp(t, 0.0, 1.0);
    if (t >= 1.0) return e;
    float x = t * 4.0;
    int i = int(floor(x));
    float f = x - float(i);
    if (i <= 0) return mix(a, b, f);
    if (i == 1) return mix(b, c, f);
    if (i == 2) return mix(c, d, f);
    return mix(d, e, f);
  }

  vec3 cmapJet(float t) {
    return lerp5(t,
      vec3(0.0, 0.0, 0.55),
      vec3(0.0, 0.0, 1.0),
      vec3(0.0, 1.0, 1.0),
      vec3(1.0, 1.0, 0.0),
      vec3(0.55, 0.0, 0.0));
  }
  vec3 cmapCoolwarm(float t) {
    return lerp5(t,
      vec3(0.23, 0.30, 0.75),
      vec3(0.47, 0.55, 0.88),
      vec3(0.88, 0.88, 0.88),
      vec3(0.88, 0.52, 0.42),
      vec3(0.71, 0.02, 0.15));
  }
  vec3 cmapViridis(float t) {
    return lerp5(t,
      vec3(0.267, 0.004, 0.329),
      vec3(0.282, 0.141, 0.458),
      vec3(0.128, 0.567, 0.551),
      vec3(0.369, 0.788, 0.383),
      vec3(0.993, 0.906, 0.144));
  }
  vec3 cmapTurbo(float t) {
    return lerp5(t,
      vec3(0.05, 0.15, 0.65),
      vec3(0.15, 0.75, 0.95),
      vec3(0.25, 0.90, 0.35),
      vec3(0.95, 0.85, 0.12),
      vec3(0.80, 0.10, 0.05));
  }
  vec3 cmapRainbow(float t) {
    return lerp5(t,
      vec3(0.05, 0.05, 0.75),
      vec3(0.0, 0.65, 0.95),
      vec3(0.15, 0.85, 0.20),
      vec3(0.98, 0.88, 0.10),
      vec3(0.92, 0.12, 0.05));
  }

  vec3 paletteColor(float t) {
    if (uPalette == 0) return cmapJet(t);
    if (uPalette == 1) return cmapCoolwarm(t);
    if (uPalette == 2) return cmapViridis(t);
    if (uPalette == 3) return cmapTurbo(t);
    return cmapRainbow(t);
  }

  void main() {
    vec2 c = 2.0 * gl_PointCoord - 1.0;
    float r = length(c);
    if (r > 1.0) discard;

    float glow = exp(-r * r * 3.0);
    float tn = normField();
    vec3 pal = paletteColor(tn);
    vec3 color = mix(pal, vec3(1.0), glow * 0.6);
    float alpha = glow * vEdgeFactor * 0.9;
    gl_FragColor = vec4(color, alpha);
  }
`;

export function FlowFrontGlow() {
  const visData = useSimStore((s) => s.visualizationData);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const showFlowFront = useSimStore((s) => s.showFlowFront);
  const heatmapField = useSimStore((s) => s.heatmapField);
  const colorPalette = useSimStore((s) => s.colorPalette);
  const animProgress = useSimStore((s) => s.animationProgress);
  const pointSize = useSimStore((s) => s.pointSize);

  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const geometry = useMemo(() => {
    if (!visData || visData.n_points === 0) return null;
    const n = visData.n_points;
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(n * 3);
    const fillTimes = new Float32Array(n);
    const values = new Float32Array(n);

    const pickValue = (i: number): number => {
      switch (heatmapField) {
        case "fill_time": return visData.fill_times[i] ?? 0;
        case "pressure": return visData.pressures[i] ?? 0;
        case "velocity": return visData.velocities[i] ?? 0;
        case "shear_rate": return visData.shear_rates[i] ?? 0;
        case "temperature": return visData.temperatures[i] ?? 0;
        case "cure_progress": return visData.cure_progress[i] ?? 0;
        case "thickness": return visData.thickness[i] ?? 0;
        default: return visData.fill_times[i] ?? 0;
      }
    };

    for (let i = 0; i < n; i++) {
      positions[i * 3] = visData.positions[i]![0]!;
      positions[i * 3 + 1] = visData.positions[i]![1]!;
      positions[i * 3 + 2] = visData.positions[i]![2]!;
      fillTimes[i] = visData.fill_times[i] ?? 0;
      values[i] = pickValue(i);
    }
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("aFillTime", new THREE.BufferAttribute(fillTimes, 1));
    geo.setAttribute("aValue", new THREE.BufferAttribute(values, 1));
    return geo;
  }, [visData, heatmapField]);

  const shaderMaterial = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: FLOW_FRONT_VERTEX,
        fragmentShader: FLOW_FRONT_FRAGMENT,
        uniforms: {
          uAnimProgress: { value: 0 },
          uTime: { value: 0 },
          uPointSize: { value: pointSize },
          uValueMin: { value: 0 },
          uValueMax: { value: 1 },
          uPalette: { value: PALETTE_INDEX.jet },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    [],
  );

  useEffect(() => {
    materialRef.current = shaderMaterial;
  }, [shaderMaterial]);

  useFrame((state) => {
    const mat = materialRef.current;
    if (!mat || !visData) return;
    const { min, max } = heatmapValueRange(heatmapField, visData);
    mat.uniforms.uAnimProgress.value = animProgress;
    mat.uniforms.uTime.value = state.clock.elapsedTime;
    mat.uniforms.uPointSize.value = pointSize;
    mat.uniforms.uValueMin.value = min;
    mat.uniforms.uValueMax.value = max;
    mat.uniforms.uPalette.value = PALETTE_INDEX[colorPalette];
  });

  if (
    !showFlowFront || !heatmapVisible || !geometry || !visData
    || animProgress >= 1.0 - 1e-6
  ) {
    return null;
  }

  return <points geometry={geometry} material={shaderMaterial} />;
}

const STREAMLINE_VERT = /* glsl */ `
  attribute float aFillTime;
  attribute float aAlong;

  varying float vParam;
  varying float vFillTime;

  void main() {
    vParam = aAlong;
    vFillTime = aFillTime;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const STREAMLINE_FRAG = /* glsl */ `
  varying float vParam;
  varying float vFillTime;

  uniform float uTime;
  uniform float uAnimProgress;
  uniform float uAnimated;

  vec3 streamColor(float t) {
    t = clamp(t, 0.0, 1.0);
    if (t < 0.25) {
      float s = t / 0.25;
      return vec3(0.05, 0.1 + s * 0.4, 0.6 + s * 0.3);
    } else if (t < 0.5) {
      float s = (t - 0.25) / 0.25;
      return vec3(0.05 + s * 0.15, 0.5 + s * 0.4, 0.9 - s * 0.5);
    } else if (t < 0.75) {
      float s = (t - 0.5) / 0.25;
      return vec3(0.2 + s * 0.75, 0.9 - s * 0.1, 0.4 - s * 0.35);
    } else {
      float s = (t - 0.75) / 0.25;
      return vec3(0.95, 0.8 - s * 0.65, 0.05 + s * 0.05);
    }
  }

  void main() {
    float visible = step(vFillTime, uAnimProgress);
    if (visible < 0.5) discard;

    float phase = vParam * 8.0 - (uAnimated > 0.5 ? uTime * 2.0 : 0.0);
    float fr = fract(phase);
    float stripe = smoothstep(0.3, 0.35, fr);
    float alpha = mix(0.3, 0.95, stripe) * visible;

    vec3 color = streamColor(vFillTime);
    float edge = smoothstep(0.3, 0.35, fr) - smoothstep(0.55, 0.6, fr);
    color += vec3(0.2) * edge;

    gl_FragColor = vec4(color, alpha);
  }
`;

export function StreamlineViewer() {
  const visData = useSimStore((s) => s.visualizationData);
  const streamlinesVisible = useSimStore((s) => s.streamlinesVisible);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const streamlineCount = useSimStore((s) => s.streamlineCount);
  const animProgress = useSimStore((s) => s.animationProgress);
  const showAnimatedStreamlines = useSimStore((s) => s.showAnimatedStreamlines);

  const lines = useMemo((): { points: THREE.Vector3[]; fillTimes: number[] }[] => {
    if (!visData || visData.n_points < 2) return [];

    const backendPaths = visData.streamline_paths;
    if (backendPaths?.length) {
      const pos = visData.positions;
      const ft = visData.fill_times;
      const pitch = visData.voxel_pitch || 1;
      const cellSize = pitch * 3.0;
      const { grid } = buildSpatialGrid(pos, cellSize);
      const nLines = Math.min(streamlineCount, 80, backendPaths.length);
      const step = Math.max(1, Math.floor(backendPaths.length / nLines));
      const result: { points: THREE.Vector3[]; fillTimes: number[] }[] = [];
      for (let pi = 0; pi < backendPaths.length && result.length < nLines; pi += step) {
        const raw = backendPaths[pi]!;
        if (!raw || raw.length < 2) continue;
        const pts = raw.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
        const lineFt = pts.map((v) => {
          const idx = nearestVoxelIndex(v.x, v.y, v.z, pos, grid, cellSize);
          return idx >= 0 ? (ft[idx] ?? 0) : 0;
        });
        result.push({ points: pts, fillTimes: lineFt });
      }
      return result;
    }

    if (visData.n_points < 10) return [];

    const n = visData.n_points;
    const pos = visData.positions;
    const ft = visData.fill_times;

    const sorted = Array.from({ length: n }, (_, i) => i)
      .filter((i) => ft[i] != null && ft[i] < 1.0)
      .sort((a, b) => ft[a] - ft[b]);

    if (sorted.length < 10) return [];

    const pitch = visData.voxel_pitch || 1;
    const cellSize = pitch * 3.0;
    const searchRadiusSq = cellSize * cellSize;
    const nLines = Math.min(streamlineCount, 80);
    const result: { points: THREE.Vector3[]; fillTimes: number[] }[] = [];

    const { grid } = buildSpatialGrid(pos, cellSize);

    // Seed streamlines from the gate position (pour hole) if available,
    // otherwise fall back to points with earliest fill times.
    const seeds: number[] = [];
    const gatePos = (visData as unknown as Record<string, unknown>).gate_position as
      | number[]
      | null
      | undefined;

    if (gatePos && gatePos.length === 3) {
      // Find points closest to the gate and use them as seeds
      const gx = gatePos[0], gy = gatePos[1], gz = gatePos[2];
      const distToGate = sorted.map((idx) => {
        const p = pos[idx];
        const dx = p[0] - gx, dy = p[1] - gy, dz = p[2] - gz;
        return { idx, d2: dx * dx + dy * dy + dz * dz };
      });
      distToGate.sort((a, b) => a.d2 - b.d2);
      const gateRadius = pitch * 8;
      const gateR2 = gateRadius * gateRadius;
      const gateSeeds = distToGate
        .filter((d) => d.d2 < gateR2)
        .map((d) => d.idx);

      // Pick evenly spaced seeds around the gate
      const step = Math.max(1, Math.floor(gateSeeds.length / nLines));
      for (let i = 0; i < gateSeeds.length && seeds.length < nLines; i += step) {
        seeds.push(gateSeeds[i]);
      }
    }

    // Fall back: use earliest fill-time points
    if (seeds.length < nLines) {
      const extraStep = Math.max(1, Math.floor(sorted.length / nLines));
      for (let i = 0; i < sorted.length && seeds.length < nLines; i += extraStep) {
        if (ft[sorted[i]] < 0.2) seeds.push(sorted[i]);
      }
    }
    if (seeds.length < nLines) {
      const extraStep = Math.max(1, Math.floor(sorted.length / nLines));
      for (let i = 0; i < sorted.length && seeds.length < nLines; i += extraStep) {
        seeds.push(sorted[i]);
      }
    }

    const maxSteps = 60;

    for (let si = 0; si < seeds.length; si++) {
      const linePoints: THREE.Vector3[] = [];
      const lineFillTimes: number[] = [];
      let cur = seeds[si];
      const visited = new Set<number>();

      for (let s = 0; s < maxSteps; s++) {
        if (visited.has(cur)) break;
        visited.add(cur);

        const cp = pos[cur];
        linePoints.push(new THREE.Vector3(cp[0], cp[1], cp[2]));
        lineFillTimes.push(ft[cur] ?? 0);

        const neighbors = getNeighborIndices(grid, cp[0], cp[1], cp[2], cellSize);
        let bestNext = -1;
        let bestFt = ft[cur];

        for (const j of neighbors) {
          if (visited.has(j)) continue;
          if (ft[j] <= bestFt) continue;
          const dx = pos[j][0] - cp[0];
          const dy = pos[j][1] - cp[1];
          const dz = pos[j][2] - cp[2];
          const d2 = dx * dx + dy * dy + dz * dz;
          if (d2 > searchRadiusSq) continue;
          if (bestNext === -1 || ft[j] < ft[bestNext]) {
            bestNext = j;
            bestFt = ft[j];
          }
        }

        if (bestNext === -1) break;
        cur = bestNext;
      }

      if (linePoints.length >= 3) {
        result.push({
          points: linePoints,
          fillTimes: lineFillTimes,
        });
      }
    }

    return result;
  }, [visData, streamlineCount]);

  if (!streamlinesVisible || !heatmapVisible || lines.length === 0) return null;

  return (
    <group>
      {lines.map((line, i) => (
        <StreamlineTube
          key={i}
          points={line.points}
          fillTimes={line.fillTimes}
          animProgress={animProgress}
          animated={showAnimatedStreamlines}
          radius={(visData?.voxel_pitch || 1) * 0.25}
        />
      ))}
    </group>
  );
}

function StreamlineTube({
  points,
  fillTimes,
  animProgress,
  radius,
  animated,
}: {
  points: THREE.Vector3[];
  fillTimes: number[];
  animProgress: number;
  radius: number;
  animated: boolean;
}) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const geometry = useMemo(() => {
    const curve = new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5);
    const nSegments = Math.max(points.length * 3, 20);
    const tubeGeo = new THREE.TubeGeometry(curve, nSegments, radius, 6, false);

    const positions = tubeGeo.attributes.position;
    const nVerts = positions.count;
    const aFillTime = new Float32Array(nVerts);
    const aAlong = new Float32Array(nVerts);

    for (let i = 0; i < nVerts; i++) {
      const vx = positions.getX(i);
      const vy = positions.getY(i);
      const vz = positions.getZ(i);

      let bestT = 0;
      let bestDist = Infinity;
      for (let pi = 0; pi < points.length; pi++) {
        const dx = vx - points[pi]!.x;
        const dy = vy - points[pi]!.y;
        const dz = vz - points[pi]!.z;
        const d = dx * dx + dy * dy + dz * dz;
        if (d < bestDist) {
          bestDist = d;
          bestT = pi;
        }
      }

      const denom = Math.max(1, points.length - 1);
      aAlong[i] = bestT / denom;
      aFillTime[i] = fillTimes[bestT] ?? 0;
    }

    tubeGeo.setAttribute("aFillTime", new THREE.BufferAttribute(aFillTime, 1));
    tubeGeo.setAttribute("aAlong", new THREE.BufferAttribute(aAlong, 1));
    return tubeGeo;
  }, [points, fillTimes, radius]);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: STREAMLINE_VERT,
        fragmentShader: STREAMLINE_FRAG,
        uniforms: {
          uTime: { value: 0 },
          uAnimProgress: { value: animProgress },
          uAnimated: { value: animated ? 1.0 : 0.0 },
        },
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
      }),
    [],
  );

  useEffect(() => {
    materialRef.current = material;
  }, [material]);

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
    };
  }, [geometry, material]);

  useFrame((state) => {
    const mat = materialRef.current;
    if (!mat) return;
    mat.uniforms.uTime.value = state.clock.elapsedTime;
    mat.uniforms.uAnimProgress.value = animProgress;
    mat.uniforms.uAnimated.value = animated ? 1.0 : 0.0;
  });

  return <mesh geometry={geometry} material={material} />;
}

/* ═══════════════════════════════════════════════════════════════════
 *  DefectMarkers — sphere markers for detected defects
 * ═══════════════════════════════════════════════════════════════════ */

export function DefectMarkers() {
  const visData = useSimStore((s) => s.visualizationData);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);

  if (!heatmapVisible || !visData || visData.defect_positions.length === 0) return null;

  return (
    <group>
      {visData.defect_positions.map((d, i) => (
        <mesh key={i} position={[d.position[0], d.position[1], d.position[2]]}>
          <sphereGeometry args={[1.5 + d.severity * 2, 16, 16]} />
          <meshStandardMaterial
            color={
              d.type === "short_shot"
                ? "#ef4444"
                : d.type === "air_trap"
                  ? "#f59e0b"
                  : d.type === "weld_line"
                    ? "#a855f7"
                    : "#3b82f6"
            }
            transparent
            opacity={0.4 + d.severity * 0.3}
            wireframe
          />
        </mesh>
      ))}
    </group>
  );
}

const MAX_VELOCITY_ARROWS = 800;

const LEGEND_FIELD_META: Record<HeatmapField, { label: string; unit: string }> = {
  fill_time: { label: "充填时间", unit: "s" },
  pressure: { label: "压力", unit: "Pa" },
  velocity: { label: "流速", unit: "mm/s" },
  shear_rate: { label: "剪切率", unit: "1/s" },
  temperature: { label: "温度", unit: "°C" },
  cure_progress: { label: "固化进度", unit: "%" },
  thickness: { label: "壁厚", unit: "mm" },
};

/** Sparse velocity vectors as arrow glyphs (cone + cylinder), colored by |dir| */
export function VelocityArrows() {
  const visData = useSimStore((s) => s.visualizationData);
  const showArrows = useSimStore((s) => s.showVelocityArrows);
  const colorPalette = useSimStore((s) => s.colorPalette);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);

  const samples = useMemo(() => {
    const vv = visData?.velocity_vectors;
    if (!vv?.length) return [];
    if (vv.length <= MAX_VELOCITY_ARROWS) return vv.slice();
    const step = Math.ceil(vv.length / MAX_VELOCITY_ARROWS);
    const out: { pos: number[]; dir: number[] }[] = [];
    for (let i = 0; i < vv.length && out.length < MAX_VELOCITY_ARROWS; i += step) {
      out.push(vv[i]);
    }
    return out;
  }, [visData]);

  const maxMag = useMemo(() => {
    let m = 1e-9;
    for (const s of samples) {
      const d = s.dir;
      const l = Math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
      if (l > m) m = l;
    }
    return m;
  }, [samples]);

  const arrowGeometry = useMemo(() => {
    const cy = new THREE.CylinderGeometry(0.06, 0.06, 0.7, 8);
    cy.translate(0, 0.35, 0);
    const co = new THREE.ConeGeometry(0.12, 0.3, 10);
    co.translate(0, 0.85, 0);
    return mergeGeometries([cy, co], false);
  }, []);

  const material = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: 0xffffff,
        toneMapped: false,
        transparent: true,
        opacity: 0.92,
        depthWrite: true,
      }),
    [],
  );

  const instancedRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const up = useMemo(() => new THREE.Vector3(0, 1, 0), []);
  const dir = useMemo(() => new THREE.Vector3(), []);
  const quat = useMemo(() => new THREE.Quaternion(), []);
  const col = useMemo(() => new THREE.Color(), []);

  useLayoutEffect(() => {
    const mesh = instancedRef.current;
    if (!mesh || !visData) return;

    const pitch = visData.voxel_pitch || 1;
    const minLen = pitch * 0.4;
    const maxLen = pitch * 10;

    for (let i = 0; i < samples.length; i++) {
      const { pos, dir: dv } = samples[i];
      dir.set(dv[0], dv[1], dv[2]);
      const mag = dir.length();
      const nmag = mag > 1e-12 ? mag : 1e-12;
      dir.multiplyScalar(1 / nmag);

      if (Math.abs(dir.dot(up) + 1) < 1e-6) {
        quat.setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
      } else {
        quat.setFromUnitVectors(up, dir);
      }

      const len = THREE.MathUtils.clamp(nmag * pitch * 1.25, minLen, maxLen);
      dummy.position.set(pos[0], pos[1], pos[2]);
      dummy.quaternion.copy(quat);
      dummy.scale.set(1, len, 1);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);

      const t = maxMag > 1e-12 ? Math.min(1, nmag / maxMag) : 0;
      const [r, g, b] = sampleSimPalette(t, colorPalette);
      col.setRGB(r, g, b);
      mesh.setColorAt(i, col);
    }

    mesh.count = samples.length;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [samples, visData, colorPalette, maxMag, dummy, dir, quat, col, up]);

  useEffect(() => {
    return () => {
      arrowGeometry.dispose();
      material.dispose();
    };
  }, [arrowGeometry, material]);

  if (!showArrows || !heatmapVisible || samples.length === 0) return null;

  return (
    <instancedMesh
      ref={instancedRef}
      args={[arrowGeometry, material, MAX_VELOCITY_ARROWS]}
      frustumCulled={false}
    />
  );
}

/** CFD-style color bar for the active scalar field (HTML overlay) */
export function ColorLegend() {
  const visData = useSimStore((s) => s.visualizationData);
  const field = useSimStore((s) => s.heatmapField);
  const showLegend = useSimStore((s) => s.showColorLegend);
  const colorPalette = useSimStore((s) => s.colorPalette);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const progress = useSimStore((s) => s.animationProgress);

  const meta = LEGEND_FIELD_META[field] ?? { label: field, unit: "" };
  const { minVal, maxVal } = useMemo(() => {
    if (!visData) return { minVal: 0, maxVal: 1 };
    const r = heatmapPhysicalRange(field, visData);
    return { minVal: r.min, maxVal: r.max };
  }, [visData, field]);

  const gradient = useMemo(() => simPaletteCssGradient(colorPalette, true), [colorPalette]);

  if (!showLegend || !visData || !heatmapVisible) return null;

  const dec = field === "cure_progress" ? 0 : 1;

  return (
    <div
      className={cn(
        "absolute bottom-[8.5rem] left-3 z-20 w-[148px] pointer-events-none select-none",
      )}
    >
      <div
        className={cn(
          "rounded-lg border border-border/60 bg-bg-primary/92 backdrop-blur-md shadow-xl",
          "px-2.5 py-2 flex flex-row gap-2.5 items-stretch",
        )}
      >
        <div
          className="w-3.5 shrink-0 rounded-sm border border-white/10 shadow-inner"
          style={{
            background: gradient,
            minHeight: 120,
            boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.35)",
          }}
        />
        <div className="flex flex-col flex-1 min-w-0 justify-between py-0.5">
          <div>
            <div className="text-[10px] font-semibold text-text-secondary tracking-wide leading-tight">
              {meta.label}
            </div>
            <div className="text-[9px] text-text-muted/80 mt-0.5">单位 · {meta.unit}</div>
          </div>
          <div className="text-right">
            <div className="text-[8px] text-text-muted uppercase tracking-wide">高</div>
            <div className="text-[10px] tabular-nums text-text-primary font-medium leading-none mt-0.5">
              {maxVal.toFixed(dec)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[8px] text-text-muted uppercase tracking-wide">低</div>
            <div className="text-[10px] tabular-nums text-text-primary font-medium leading-none mt-0.5">
              {minVal.toFixed(dec)}
            </div>
          </div>
          <div className="mt-1.5 pt-1.5 border-t border-border/40 text-[9px] text-text-muted tabular-nums">
            充填动画 {(progress * 100).toFixed(0)}%
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
 *  SurfaceOverlayViewer — heatmap mapped onto model surface mesh
 * ═══════════════════════════════════════════════════════════════════ */

function heatmapRGB(t: number): [number, number, number] {
  t = Math.max(0, Math.min(1, t));
  if (t < 0.25) {
    const s = t / 0.25;
    return [0.05 + s * -0.05, 0.05 + s * 0.45, 0.5 + s * 0.3];
  } else if (t < 0.5) {
    const s = (t - 0.25) / 0.25;
    return [0.0 + s * 0.1, 0.5 + s * 0.3, 0.8 - s * 0.5];
  } else if (t < 0.75) {
    const s = (t - 0.5) / 0.25;
    return [0.1 + s * 0.85, 0.8 + s * 0.05, 0.3 - s * 0.19];
  } else {
    const s = (t - 0.75) / 0.25;
    return [0.95 - s * 0.05, 0.85 - s * 0.7, 0.11 - s * 0.01];
  }
}

export function SurfaceOverlayViewer() {
  const surfaceData = useSimStore((s) => s.surfaceMapData) as {
    n_vertices: number;
    values: number[];
    vertex_positions: number[][];
    faces: number[][];
  } | null;
  const surfaceVisible = useSimStore((s) => s.surfaceMapVisible);
  const heatmapOpacity = useSimStore((s) => s.heatmapOpacity);

  const geometry = useMemo(() => {
    if (!surfaceData || !surfaceData.vertex_positions) return null;

    const geo = new THREE.BufferGeometry();
    const nv = surfaceData.n_vertices;
    const nf = surfaceData.faces.length;

    const positions = new Float32Array(nv * 3);
    const colors = new Float32Array(nv * 3);

    for (let i = 0; i < nv; i++) {
      positions[i * 3] = surfaceData.vertex_positions[i][0];
      positions[i * 3 + 1] = surfaceData.vertex_positions[i][1];
      positions[i * 3 + 2] = surfaceData.vertex_positions[i][2];

      const [r, g, b] = heatmapRGB(surfaceData.values[i] ?? 0);
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }

    const indices = new Uint32Array(nf * 3);
    for (let i = 0; i < nf; i++) {
      indices[i * 3] = surfaceData.faces[i][0];
      indices[i * 3 + 1] = surfaceData.faces[i][1];
      indices[i * 3 + 2] = surfaceData.faces[i][2];
    }

    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.setIndex(new THREE.BufferAttribute(indices, 1));
    geo.computeVertexNormals();

    return geo;
  }, [surfaceData]);

  if (!surfaceVisible || !geometry) return null;

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        vertexColors
        transparent
        opacity={heatmapOpacity}
        side={THREE.DoubleSide}
        roughness={0.6}
        metalness={0.0}
        depthWrite={false}
      />
    </mesh>
  );
}

/* ═══════════════════════════════════════════════════════════════════
 *  FEAViewer — Von Mises / displacement overlay on model surface
 * ═══════════════════════════════════════════════════════════════════ */

function feaColorMap(t: number, field: string): [number, number, number] {
  t = Math.max(0, Math.min(1, t));
  if (field === "safety_factor") {
    t = 1.0 - t;
  }
  if (t < 0.2) {
    const s = t / 0.2;
    return [0.0, 0.0 + s * 0.4, 0.6 + s * 0.4];
  } else if (t < 0.4) {
    const s = (t - 0.2) / 0.2;
    return [0.0, 0.4 + s * 0.6, 1.0 - s * 0.3];
  } else if (t < 0.6) {
    const s = (t - 0.4) / 0.2;
    return [0.0 + s * 0.5, 1.0 - s * 0.1, 0.7 - s * 0.7];
  } else if (t < 0.8) {
    const s = (t - 0.6) / 0.2;
    return [0.5 + s * 0.5, 0.9 - s * 0.5, 0.0];
  } else {
    const s = (t - 0.8) / 0.2;
    return [1.0, 0.4 - s * 0.4, 0.0];
  }
}

export function FEAViewer() {
  const feaData = useSimStore((s) => s.feaVisualizationData) as {
    n_vertices: number;
    displacement_magnitude: number[];
    von_mises_stress: number[];
    safety_factor: number[];
    strain_energy: number[];
  } | null;
  const feaVisible = useSimStore((s) => s.feaVisible);
  const feaField = useSimStore((s) => s.feaField);
  const glbUrl = useModelStore((s) => s.glbUrl);

  const colorData = useMemo(() => {
    if (!feaData) return null;

    const n = feaData.n_vertices;
    const fieldMap: Record<string, number[]> = {
      displacement: feaData.displacement_magnitude,
      von_mises: feaData.von_mises_stress,
      safety_factor: feaData.safety_factor,
      strain_energy: feaData.strain_energy,
    };
    const values = fieldMap[feaField] || feaData.von_mises_stress;

    let maxVal = 0;
    for (let i = 0; i < n; i++) {
      if (values[i] > maxVal) maxVal = values[i];
    }
    if (maxVal < 1e-10) maxVal = 1;

    const colors = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const t = feaField === "safety_factor"
        ? Math.min(values[i] / 5.0, 1.0)
        : values[i] / maxVal;
      const [r, g, b] = feaColorMap(t, feaField);
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }

    return { colors, n };
  }, [feaData, feaField]);

  if (!feaVisible || !colorData || !glbUrl) return null;

  return <FEAMeshOverlay glbUrl={glbUrl} colors={colorData.colors} nVerts={colorData.n} />;
}

function FEAMeshOverlay({ glbUrl, colors, nVerts }: {
  glbUrl: string; colors: Float32Array; nVerts: number;
}) {
  const gltf = useLoader(GLTFLoader, glbUrl);
  const meshRef = useRef<THREE.Mesh>(null);

  const clonedGeometry = useMemo(() => {
    let srcGeo: THREE.BufferGeometry | null = null;
    gltf.scene.traverse((child) => {
      if (!srcGeo && (child as THREE.Mesh).isMesh) {
        srcGeo = (child as THREE.Mesh).geometry;
      }
    });
    if (!srcGeo) return null;
    const geo = (srcGeo as THREE.BufferGeometry).clone();
    const nGeo = geo.attributes.position.count;

    if (nGeo === nVerts) {
      geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    } else {
      // Vertex count mismatch: map colors via nearest-neighbor interpolation
      const mapped = new Float32Array(nGeo * 3);
      const ratio = nVerts / nGeo;
      for (let i = 0; i < nGeo; i++) {
        const src = Math.min(Math.floor(i * ratio), nVerts - 1);
        mapped[i * 3] = colors[src * 3];
        mapped[i * 3 + 1] = colors[src * 3 + 1];
        mapped[i * 3 + 2] = colors[src * 3 + 2];
      }
      geo.setAttribute("color", new THREE.BufferAttribute(mapped, 3));
    }
    geo.computeVertexNormals();
    return geo;
  }, [gltf, colors, nVerts]);

  useEffect(() => {
    if (!meshRef.current || !clonedGeometry) return;
    const geo = meshRef.current.geometry;
    if (geo !== clonedGeometry) {
      meshRef.current.geometry = clonedGeometry;
    }
  }, [clonedGeometry]);

  if (!clonedGeometry) return null;

  return (
    <mesh ref={meshRef} geometry={clonedGeometry}>
      <meshPhysicalMaterial
        vertexColors
        transparent
        opacity={0.85}
        side={THREE.DoubleSide}
        roughness={0.4}
        metalness={0.05}
        depthWrite={false}
        clearcoat={0.3}
      />
    </mesh>
  );
}
