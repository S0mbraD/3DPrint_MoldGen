import { useRef, useMemo, useEffect } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { useSimStore, type HeatmapField } from "../../stores/simStore";
import { useModelStore } from "../../stores/modelStore";

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

  vec3 heatmap(float t) {
    t = clamp(t, 0.0, 1.0);
    vec3 c;
    if (t < 0.25) {
      float s = t / 0.25;
      c = mix(vec3(0.05, 0.05, 0.5), vec3(0.0, 0.5, 0.8), s);
    } else if (t < 0.5) {
      float s = (t - 0.25) / 0.25;
      c = mix(vec3(0.0, 0.5, 0.8), vec3(0.1, 0.8, 0.3), s);
    } else if (t < 0.75) {
      float s = (t - 0.5) / 0.25;
      c = mix(vec3(0.1, 0.8, 0.3), vec3(0.95, 0.85, 0.1), s);
    } else {
      float s = (t - 0.75) / 0.25;
      c = mix(vec3(0.95, 0.85, 0.1), vec3(0.9, 0.15, 0.1), s);
    }
    return c;
  }

  void main() {
    if (vVisible < 0.5) discard;

    vec2 cxy = 2.0 * gl_PointCoord - 1.0;
    float r = dot(cxy, cxy);
    if (r > 1.0) discard;

    // Soft glow edge
    float alpha = vOpacity * (1.0 - smoothstep(0.3, 1.0, r));

    vec3 color = heatmap(vValue);
    // Slight additive glow at center
    color += vec3(0.15) * (1.0 - smoothstep(0.0, 0.4, r));

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

const STREAMLINE_COLORS = [
  new THREE.Color(0.95, 0.3, 0.3),
  new THREE.Color(1.0, 0.6, 0.15),
  new THREE.Color(0.2, 0.85, 0.4),
  new THREE.Color(0.2, 0.6, 1.0),
  new THREE.Color(0.7, 0.3, 1.0),
  new THREE.Color(1.0, 0.85, 0.1),
];

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

export function StreamlineViewer() {
  const visData = useSimStore((s) => s.visualizationData);
  const streamlinesVisible = useSimStore((s) => s.streamlinesVisible);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const streamlineCount = useSimStore((s) => s.streamlineCount);
  const animProgress = useSimStore((s) => s.animationProgress);

  const lines = useMemo(() => {
    if (!visData || visData.n_points < 10) return [];

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
    const result: { points: THREE.Vector3[]; color: THREE.Color }[] = [];

    const { grid } = buildSpatialGrid(pos, cellSize);

    const seeds: number[] = [];
    const seedStep = Math.max(1, Math.floor(sorted.length / (nLines * 3)));
    for (let i = 0; i < sorted.length && seeds.length < nLines; i += seedStep) {
      if (ft[sorted[i]] < 0.15) seeds.push(sorted[i]);
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
      let cur = seeds[si];
      const visited = new Set<number>();

      for (let s = 0; s < maxSteps; s++) {
        if (visited.has(cur)) break;
        visited.add(cur);

        const cp = pos[cur];
        linePoints.push(new THREE.Vector3(cp[0], cp[1], cp[2]));

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
          color: STREAMLINE_COLORS[si % STREAMLINE_COLORS.length],
        });
      }
    }

    return result;
  }, [visData, streamlineCount]);

  if (!streamlinesVisible || !heatmapVisible || lines.length === 0) return null;

  return (
    <group>
      {lines.map((line, i) => (
        <StreamlineCurve
          key={i}
          points={line.points}
          color={line.color}
          animProgress={animProgress}
        />
      ))}
    </group>
  );
}

function StreamlineCurve({
  points,
  color,
  animProgress,
}: {
  points: THREE.Vector3[];
  color: THREE.Color;
  animProgress: number;
}) {
  const ref = useRef<THREE.Line>(null);

  const { geometry, material } = useMemo(() => {
    const curve = new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5);
    const smoothPoints = curve.getPoints(points.length * 4);
    const geo = new THREE.BufferGeometry().setFromPoints(smoothPoints);

    const colors = new Float32Array(smoothPoints.length * 3);
    for (let i = 0; i < smoothPoints.length; i++) {
      const t = i / (smoothPoints.length - 1);
      const fade = t <= animProgress ? Math.min(1.0, (animProgress - t) * 5 + 0.3) : 0.0;
      colors[i * 3] = color.r * fade;
      colors[i * 3 + 1] = color.g * fade;
      colors[i * 3 + 2] = color.b * fade;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    const mat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      linewidth: 1,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    return { geometry: geo, material: mat };
  }, [points, color, animProgress]);

  return <primitive ref={ref} object={new THREE.Line(geometry, material)} />;
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

  const geometry = useMemo(() => {
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

  if (!feaVisible || !geometry || !glbUrl) return null;

  return <FEAMeshOverlay colors={geometry.colors} />;
}

function FEAMeshOverlay({ colors }: { colors: Float32Array }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const meshInfo = useModelStore((s) => s.meshInfo);

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh?.geometry) return;
    const geo = mesh.geometry;
    if (geo.attributes.position && colors.length / 3 === geo.attributes.position.count) {
      geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      geo.attributes.color.needsUpdate = true;
    }
  }, [colors]);

  if (!meshInfo) return null;

  const center = meshInfo.center || [0, 0, 0];

  return (
    <mesh ref={meshRef} position={[0, 0, 0]}>
      <sphereGeometry args={[0.01, 1, 1]} />
      <meshStandardMaterial
        vertexColors
        transparent
        opacity={0.8}
        side={THREE.DoubleSide}
        roughness={0.5}
      />
    </mesh>
  );
}
