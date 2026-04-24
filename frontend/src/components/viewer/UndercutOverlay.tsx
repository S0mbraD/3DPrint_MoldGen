import { useMemo } from "react";
import * as THREE from "three";
import { useMoldStore } from "../../stores/moldStore";

function depthToRGB(t: number): [number, number, number] {
  t = Math.max(0, Math.min(1, t));
  if (t < 0.25) return [0, t * 4, 1];
  if (t < 0.5) return [0, 1, 1 - (t - 0.25) * 4];
  if (t < 0.75) return [(t - 0.5) * 4, 1, 0];
  return [1, 1 - (t - 0.75) * 4, 0];
}

export function UndercutOverlay() {
  const heatmap = useMoldStore((s) => s.undercutHeatmap);
  const visible = useMoldStore((s) => s.undercutHeatmapVisible);

  const geometry = useMemo(() => {
    if (!heatmap || heatmap.vertex_positions.length === 0) return null;

    const nVerts = heatmap.vertex_positions.length;
    const nFaces = heatmap.face_indices.length;
    const positions = new Float32Array(nFaces * 3 * 3);
    const colors = new Float32Array(nFaces * 3 * 3);

    for (let fi = 0; fi < nFaces; fi++) {
      const [a, b, c] = heatmap.face_indices[fi];
      const val = heatmap.face_values[fi] ?? 0;
      const [r, g, bl] = depthToRGB(val);

      for (let vi = 0; vi < 3; vi++) {
        const vertIdx = [a, b, c][vi];
        const v = vertIdx < nVerts ? heatmap.vertex_positions[vertIdx] : [0, 0, 0];
        const base = (fi * 3 + vi) * 3;
        positions[base] = v[0];
        positions[base + 1] = v[1];
        positions[base + 2] = v[2];
        colors[base] = r;
        colors[base + 1] = g;
        colors[base + 2] = bl;
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    return geo;
  }, [heatmap]);

  if (!visible || !geometry || !heatmap) return null;

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        vertexColors
        transparent
        opacity={0.7}
        side={THREE.DoubleSide}
        roughness={0.5}
        depthWrite={false}
      />
    </mesh>
  );
}
