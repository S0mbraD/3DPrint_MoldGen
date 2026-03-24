import { useGLTF } from "@react-three/drei";
import { useEffect, useRef } from "react";
import type { Mesh } from "three";
import * as THREE from "three";
import { useModelStore } from "../../stores/modelStore";
import { useViewportStore, type DisplayMode } from "../../stores/viewportStore";
import { useInsertStore } from "../../stores/insertStore";

function createMaterial(mode: DisplayMode, opacity: number): THREE.Material {
  const side = THREE.DoubleSide;
  const transparent = opacity < 1;

  switch (mode) {
    case "wireframe":
      return new THREE.MeshStandardMaterial({
        color: 0x8b9dc3, roughness: 0.35, metalness: 0.15,
        wireframe: true, side, transparent, opacity,
      });
    case "clay":
      return new THREE.MeshStandardMaterial({
        color: 0xd4c5a9, roughness: 0.85, metalness: 0.0,
        side, transparent, opacity,
      });
    case "xray":
      return new THREE.MeshPhysicalMaterial({
        color: 0x88ccff, roughness: 0.1, metalness: 0.0,
        transparent: true, opacity: Math.min(opacity, 0.25),
        side, depthWrite: false,
      });
    case "flat":
      return new THREE.MeshStandardMaterial({
        color: 0x8b9dc3, roughness: 0.5, metalness: 0.1,
        flatShading: true, side, transparent, opacity,
      });
    case "normal":
      return new THREE.MeshNormalMaterial({ side, transparent, opacity });
    default:
      return new THREE.MeshStandardMaterial({
        color: 0x8b9dc3, roughness: 0.35, metalness: 0.15,
        side, transparent, opacity,
      });
  }
}

export function ModelViewer() {
  const glbUrl = useModelStore((s) => s.glbUrl);
  if (!glbUrl) return null;
  return <LoadedModel url={glbUrl} />;
}

function LoadedModel({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const groupRef = useRef<THREE.Group>(null);
  const displayMode = useViewportStore((s) => s.displayMode);
  const visible = useViewportStore((s) => s.modelVisible);
  const baseOpacity = useViewportStore((s) => s.modelOpacity);
  const insertVisible = useViewportStore((s) => s.insertVisible);
  const hasInserts = useInsertStore((s) => !!s.insertId && s.plates.length > 0);

  const opacity = hasInserts && insertVisible
    ? Math.min(baseOpacity, 0.35)
    : baseOpacity;

  useEffect(() => {
    scene.traverse((child) => {
      if ((child as Mesh).isMesh) {
        const mesh = child as Mesh;
        mesh.material = createMaterial(displayMode, opacity);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
      }
    });
  }, [scene, displayMode, opacity]);

  return <primitive ref={groupRef} object={scene} visible={visible} />;
}
