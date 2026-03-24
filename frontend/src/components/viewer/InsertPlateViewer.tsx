import { useGLTF } from "@react-three/drei";
import { Component, Suspense, useMemo, type ReactNode } from "react";
import type { Mesh } from "three";
import * as THREE from "three";

class InsertErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) return null;
    return this.props.children;
  }
}

const INSERT_COLOR = new THREE.Color(0.2, 0.85, 0.45);

export function InsertPlateViewer({
  insertId,
  plateIndex,
  opacity = 0.55,
  visible = true,
}: {
  insertId: string;
  plateIndex: number;
  opacity?: number;
  visible?: boolean;
}) {
  const url = useMemo(
    () => `/api/v1/inserts/result/${insertId}/plate/${plateIndex}/glb`,
    [insertId, plateIndex],
  );

  return (
    <InsertErrorBoundary>
      <Suspense fallback={null}>
        <PlateModel url={url} opacity={opacity} visible={visible} />
      </Suspense>
    </InsertErrorBoundary>
  );
}

function PlateModel({
  url,
  opacity,
  visible,
}: {
  url: string;
  opacity: number;
  visible: boolean;
}) {
  const { scene } = useGLTF(url);

  const clonedScene = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse((child) => {
      if ((child as Mesh).isMesh) {
        const mesh = child as Mesh;
        mesh.material = new THREE.MeshPhysicalMaterial({
          color: INSERT_COLOR,
          roughness: 0.3,
          metalness: 0.05,
          transparent: true,
          opacity: Math.max(0.2, opacity),
          side: THREE.DoubleSide,
          depthWrite: opacity >= 0.85,
          transmission: 0.15,
          thickness: 1.5,
          clearcoat: 0.3,
          clearcoatRoughness: 0.3,
        });
      }
    });
    return clone;
  }, [scene, opacity]);

  return <primitive object={clonedScene} visible={visible} />;
}
