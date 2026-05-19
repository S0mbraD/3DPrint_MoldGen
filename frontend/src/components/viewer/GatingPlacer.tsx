import { useCallback, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import { useSimStore } from "../../stores/simStore";

const GATE_COLOR = "#ff6b35";
const VENT_COLOR = "#4ecdc4";
const HANDLE_SIZE = 3;

/**
 * Invisible overlay + raycasting for click-to-place gating points.
 * Also renders draggable markers for already-placed manual positions.
 */
export function GatingPlacer() {
  const placementMode = useSimStore((s) => s.placementMode);
  const manualGatePos = useSimStore((s) => s.manualGatePos);
  const manualVentPositions = useSimStore((s) => s.manualVentPositions);
  const setManualGatePos = useSimStore((s) => s.setManualGatePos);
  const updateManualVentPos = useSimStore((s) => s.updateManualVentPos);
  const removeManualVentPos = useSimStore((s) => s.removeManualVentPos);
  const isActive = placementMode !== "none";

  if (!isActive && !manualGatePos && manualVentPositions.length === 0) return null;

  return (
    <group>
      {isActive && <ClickCatcher />}
      {manualGatePos && (
        <DragHandle
          position={manualGatePos}
          color={GATE_COLOR}
          size={HANDLE_SIZE}
          label="浇口"
          onDrag={(pos) => setManualGatePos(pos)}
          onRemove={() => setManualGatePos(null)}
        />
      )}
      {manualVentPositions.map((pos, i) => (
        <DragHandle
          key={`vent-${i}`}
          position={pos}
          color={VENT_COLOR}
          size={HANDLE_SIZE * 0.8}
          label={`排气${i + 1}`}
          onDrag={(p) => updateManualVentPos(i, p)}
          onRemove={() => removeManualVentPos(i)}
        />
      ))}
      {isActive && <PlacementHint mode={placementMode} />}
    </group>
  );
}

function ClickCatcher() {
  const { scene, camera, gl } = useThree();
  const placementMode = useSimStore((s) => s.placementMode);
  const setManualGatePos = useSimStore((s) => s.setManualGatePos);
  const addManualVentPos = useSimStore((s) => s.addManualVentPos);
  const setPlacementMode = useSimStore((s) => s.setPlacementMode);
  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const mouse = useRef(new THREE.Vector2());

  const handlePointerDown = useCallback(
    (e: PointerEvent) => {
      if (e.button !== 0) return;

      const ndcX = (e.offsetX / gl.domElement.clientWidth) * 2 - 1;
      const ndcY = -(e.offsetY / gl.domElement.clientHeight) * 2 + 1;
      mouse.current.set(ndcX, ndcY);
      raycaster.setFromCamera(mouse.current, camera);

      const meshes: THREE.Mesh[] = [];
      scene.traverse((obj) => {
        if ((obj as THREE.Mesh).isMesh && obj.visible) {
          meshes.push(obj as THREE.Mesh);
        }
      });

      const hits = raycaster.intersectObjects(meshes, false);
      if (hits.length === 0) return;

      e.stopPropagation();
      const pt = hits[0].point;
      const pos: [number, number, number] = [pt.x, pt.y, pt.z];

      if (placementMode === "gate") {
        setManualGatePos(pos);
        setPlacementMode("none");
      } else if (placementMode === "vent") {
        addManualVentPos(pos);
      }
    },
    [placementMode, setManualGatePos, addManualVentPos, setPlacementMode, camera, gl, scene, raycaster],
  );

  useEffect(() => {
    const el = gl.domElement;
    el.addEventListener("pointerdown", handlePointerDown);
    return () => el.removeEventListener("pointerdown", handlePointerDown);
  }, [gl, handlePointerDown]);

  return null;
}

function DragHandle({
  position,
  color,
  size,
  label: _label,
  onDrag,
  onRemove,
}: {
  position: [number, number, number];
  color: string;
  size: number;
  label: string;
  onDrag: (pos: [number, number, number]) => void;
  onRemove: () => void;
}) {
  const { camera, gl, scene } = useThree();
  const isDragging = useRef(false);
  const plane = useRef(new THREE.Plane());
  const offset = useRef(new THREE.Vector3());
  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const meshRef = useRef<THREE.Mesh>(null);

  const handlePointerDown = useCallback(
    (e: THREE.Event) => {
      (e as unknown as { stopPropagation?: () => void }).stopPropagation?.();
      const domEvent = (e as unknown as { nativeEvent?: PointerEvent }).nativeEvent;
      if (!domEvent) return;
      if (domEvent.button === 2) {
        onRemove();
        return;
      }
      isDragging.current = true;
      gl.domElement.style.cursor = "grabbing";

      const camDir = new THREE.Vector3();
      camera.getWorldDirection(camDir);
      const pos3 = new THREE.Vector3(...position);
      plane.current.setFromNormalAndCoplanarPoint(camDir, pos3);

      const ndc = new THREE.Vector2(
        (domEvent.offsetX / gl.domElement.clientWidth) * 2 - 1,
        -(domEvent.offsetY / gl.domElement.clientHeight) * 2 + 1,
      );
      raycaster.setFromCamera(ndc, camera);
      const hit = new THREE.Vector3();
      raycaster.ray.intersectPlane(plane.current, hit);
      offset.current.copy(pos3).sub(hit);

      const onMove = (ev: PointerEvent) => {
        if (!isDragging.current) return;
        const ndcM = new THREE.Vector2(
          (ev.offsetX / gl.domElement.clientWidth) * 2 - 1,
          -(ev.offsetY / gl.domElement.clientHeight) * 2 + 1,
        );
        raycaster.setFromCamera(ndcM, camera);
        const pt = new THREE.Vector3();
        raycaster.ray.intersectPlane(plane.current, pt);
        pt.add(offset.current);

        const meshes: THREE.Mesh[] = [];
        scene.traverse((obj) => {
          if (
            (obj as THREE.Mesh).isMesh &&
            obj.visible &&
            obj !== meshRef.current
          ) {
            meshes.push(obj as THREE.Mesh);
          }
        });
        const surfHits = raycaster.intersectObjects(meshes, false);
        const snapped = surfHits.length > 0 ? surfHits[0].point : pt;
        onDrag([snapped.x, snapped.y, snapped.z]);
      };

      const onUp = () => {
        isDragging.current = false;
        gl.domElement.style.cursor = "auto";
        gl.domElement.removeEventListener("pointermove", onMove);
        gl.domElement.removeEventListener("pointerup", onUp);
        gl.domElement.removeEventListener("pointerleave", onUp);
      };

      gl.domElement.addEventListener("pointermove", onMove);
      gl.domElement.addEventListener("pointerup", onUp);
      gl.domElement.addEventListener("pointerleave", onUp);
    },
    [position, camera, gl, onDrag, onRemove, raycaster, scene],
  );

  return (
    <mesh
      ref={meshRef}
      position={position}
      onPointerDown={handlePointerDown}
      onPointerEnter={() => { gl.domElement.style.cursor = "grab"; }}
      onPointerLeave={() => {
        if (!isDragging.current) gl.domElement.style.cursor = "auto";
      }}
    >
      <sphereGeometry args={[size, 16, 16]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={0.3}
        transparent
        opacity={0.7}
      />
    </mesh>
  );
}

function PlacementHint({ mode }: { mode: "gate" | "vent" | "none" }) {
  if (mode === "none") return null;
  return (
    <group />
  );
}

export default GatingPlacer;
