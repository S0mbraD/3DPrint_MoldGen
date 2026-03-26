import { useMemo } from "react";
import * as THREE from "three";
import { useSimStore, type MeshGeometry } from "../../stores/simStore";

function GatingMesh({ geo, color }: { geo: MeshGeometry; color: string }) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const verts = new Float32Array(geo.vertices.flat());
    const indices: number[] = [];
    for (const f of geo.faces) {
      indices.push(f[0], f[1], f[2]);
    }
    g.setAttribute("position", new THREE.BufferAttribute(verts, 3));
    g.setIndex(indices);
    g.computeVertexNormals();
    return g;
  }, [geo]);

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color={color}
        transparent
        opacity={0.85}
        roughness={0.3}
        metalness={0.1}
      />
    </mesh>
  );
}

export function GatingViewer() {
  const gatingResult = useSimStore((s) => s.gatingResult);
  if (!gatingResult) return null;

  return (
    <group>
      {gatingResult.gate_mesh && (
        <GatingMesh geo={gatingResult.gate_mesh} color="#ff6b35" />
      )}
      {gatingResult.vent_meshes?.map((vm, i) => (
        <GatingMesh key={`vent-${i}`} geo={vm} color="#4ecdc4" />
      ))}
      <GateMarker position={gatingResult.gate.position} diameter={gatingResult.gate_diameter} />
      {gatingResult.vents.map((v, i) => (
        <VentMarker key={`vm-${i}`} position={v.position} normal={v.normal} />
      ))}
    </group>
  );
}

function GateMarker({ position, diameter }: { position: number[]; diameter: number }) {
  return (
    <mesh position={[position[0], position[1], position[2]]}>
      <sphereGeometry args={[diameter / 2, 16, 16]} />
      <meshStandardMaterial color="#ff6b35" transparent opacity={0.4} wireframe />
    </mesh>
  );
}

function VentMarker({ position, normal }: { position: number[]; normal: number[] }) {
  const quaternion = useMemo(() => {
    const q = new THREE.Quaternion();
    const dir = new THREE.Vector3(normal[0], normal[1], normal[2]).normalize();
    q.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
    return q;
  }, [normal]);

  return (
    <mesh position={[position[0], position[1], position[2]]} quaternion={quaternion}>
      <coneGeometry args={[2, 5, 8]} />
      <meshStandardMaterial color="#4ecdc4" transparent opacity={0.5} />
    </mesh>
  );
}
