import { useGLTF } from "@react-three/drei";
import { Component, Suspense, useMemo, type ReactNode } from "react";
import type { Mesh } from "three";
import * as THREE from "three";
import { useViewportStore } from "../../stores/viewportStore";

const SHELL_COLORS: [number, number, number][] = [
  [1.0, 0.56, 0.72],  // pink  — shell 0
  [0.38, 0.65, 1.0],  // blue  — shell 1
  [0.65, 0.55, 0.98],
  [0.20, 0.83, 0.60],
  [0.98, 0.75, 0.14],
  [0.98, 0.57, 0.24],
];

class ShellErrorBoundary extends Component<
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

export function MoldShellViewer({
  moldId,
  shellId,
}: {
  moldId: string;
  shellId: number;
}) {
  const url = useMemo(
    () => `/api/v1/molds/result/${moldId}/shell/${shellId}/glb`,
    [moldId, shellId],
  );

  return (
    <ShellErrorBoundary>
      <Suspense fallback={null}>
        <ShellModel url={url} shellId={shellId} />
      </Suspense>
    </ShellErrorBoundary>
  );
}

function ShellModel({ url, shellId }: { url: string; shellId: number }) {
  const { scene } = useGLTF(url);
  const moldVisible = useViewportStore((s) => s.moldVisible);
  const moldOpacity = useViewportStore((s) => s.moldOpacity);
  const shellOverride = useViewportStore((s) => s.shellOverrides[shellId]);

  const visible = moldVisible && (shellOverride?.visible ?? true);
  const opacity = shellOverride?.opacity ?? moldOpacity;
  const rgb = SHELL_COLORS[shellId % SHELL_COLORS.length];
  const color = new THREE.Color(rgb[0], rgb[1], rgb[2]);

  const clonedScene = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse((child) => {
      if ((child as Mesh).isMesh) {
        const mesh = child as Mesh;
        mesh.material = new THREE.MeshPhysicalMaterial({
          color,
          roughness: 0.25,
          metalness: 0.0,
          transparent: true,
          opacity: Math.max(0.15, opacity),
          side: THREE.DoubleSide,
          depthWrite: opacity >= 0.85,
          transmission: 0.3,
          thickness: 2.0,
          clearcoat: 0.4,
          clearcoatRoughness: 0.2,
        });
      }
    });
    return clone;
  }, [scene, color, opacity]);

  return <primitive object={clonedScene} visible={visible} />;
}
