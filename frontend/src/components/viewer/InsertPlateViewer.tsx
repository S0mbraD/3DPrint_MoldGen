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

const PLATE_COLOR = new THREE.Color(0.2, 0.85, 0.45);
const PILLAR_COLOR = new THREE.Color(0.95, 0.65, 0.15);

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
  const plateUrl = useMemo(
    () => `/api/v1/inserts/result/${insertId}/plate/${plateIndex}/glb`,
    [insertId, plateIndex],
  );
  const pillarUrl = useMemo(
    () => `/api/v1/inserts/result/${insertId}/plate/${plateIndex}/pillars.glb`,
    [insertId, plateIndex],
  );

  return (
    <>
      <InsertErrorBoundary>
        <Suspense fallback={null}>
          <PlateModel url={plateUrl} color={PLATE_COLOR} opacity={opacity} visible={visible} />
        </Suspense>
      </InsertErrorBoundary>
      <InsertErrorBoundary>
        <Suspense fallback={null}>
          <PlateModel url={pillarUrl} color={PILLAR_COLOR} opacity={Math.min(1, opacity + 0.2)} visible={visible} />
        </Suspense>
      </InsertErrorBoundary>
    </>
  );
}

function PlateModel({
  url,
  color,
  opacity,
  visible,
}: {
  url: string;
  color: THREE.Color;
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
          color,
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
  }, [scene, opacity, color]);

  return <primitive object={clonedScene} visible={visible} />;
}
