import { useCallback, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useViewportStore } from "../../stores/viewportStore";

const POINT_COLOR = "#ff4081";
const LINE_COLOR = "#ffd740";

export function MeasureOverlay() {
  const measureTool = useViewportStore((s) => s.measureTool);
  const measurePoints = useViewportStore((s) => s.measurePoints);
  const measureResult = useViewportStore((s) => s.measureResult);

  if (measureTool === "none") return null;

  return (
    <group>
      <MeasureClickCatcher />
      {measurePoints.map((p, i) => (
        <MeasurePoint key={i} position={p.position} index={i} />
      ))}
      {measurePoints.length >= 2 && <MeasureLines points={measurePoints.map((p) => p.position)} />}
      {measureResult && measurePoints.length >= 2 && (
        <MeasureLabel
          position={measurePoints[Math.floor(measurePoints.length / 2)].position}
          text={measureResult}
        />
      )}
    </group>
  );
}

function MeasureClickCatcher() {
  const { scene, camera, gl } = useThree();
  const addMeasurePoint = useViewportStore((s) => s.addMeasurePoint);
  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const mouse = useRef(new THREE.Vector2());

  const handleClick = useCallback(
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
      const n = hits[0].face?.normal;
      addMeasurePoint({
        position: [pt.x, pt.y, pt.z],
        normal: n ? [n.x, n.y, n.z] : undefined,
      });
    },
    [addMeasurePoint, camera, gl, scene, raycaster],
  );

  useEffect(() => {
    const el = gl.domElement;
    el.addEventListener("pointerdown", handleClick);
    return () => el.removeEventListener("pointerdown", handleClick);
  }, [gl, handleClick]);

  return null;
}

function MeasurePoint({ position, index }: { position: [number, number, number]; index: number }) {
  return (
    <group position={position}>
      <mesh>
        <sphereGeometry args={[1.2, 12, 12]} />
        <meshStandardMaterial color={POINT_COLOR} emissive={POINT_COLOR} emissiveIntensity={0.5} />
      </mesh>
      <Html center distanceFactor={150} style={{ pointerEvents: "none" }}>
        <div className="bg-black/70 text-white text-[10px] px-1 rounded">
          P{index + 1}
        </div>
      </Html>
    </group>
  );
}

function MeasureLines({ points }: { points: [number, number, number][] }) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const verts = new Float32Array(points.length * 3);
    for (let i = 0; i < points.length; i++) {
      verts[i * 3] = points[i][0];
      verts[i * 3 + 1] = points[i][1];
      verts[i * 3 + 2] = points[i][2];
    }
    g.setAttribute("position", new THREE.BufferAttribute(verts, 3));
    return g;
  }, [points]);

  return (
    <line>
      <primitive object={geometry} attach="geometry" />
      <lineBasicMaterial color={LINE_COLOR} linewidth={2} />
    </line>
  );
}

function MeasureLabel({ position, text }: { position: [number, number, number]; text: string }) {
  return (
    <Html position={position} center distanceFactor={200} style={{ pointerEvents: "none" }}>
      <div className="bg-black/80 text-yellow-300 text-[12px] font-mono px-2 py-0.5 rounded shadow-lg whitespace-nowrap">
        {text}
      </div>
    </Html>
  );
}

export default MeasureOverlay;
