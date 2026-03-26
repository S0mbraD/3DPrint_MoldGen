import { useCallback, useMemo, useRef } from "react";
import * as THREE from "three";
import { useInsertStore } from "../../stores/insertStore";

/**
 * 3D brush painter overlay for the insert plate.
 *
 * Supports two modes:
 *   - "holes": paints circular regions where mesh holes will be generated
 *   - "ribs":  paints circular regions where ribs will be generated
 *
 * Regions are stored as {u, v, radius} in the insert store.
 */
export function HoleBrushPainter({
  plateNormal,
  plateCentre,
}: {
  plateNormal: [number, number, number];
  plateCentre: [number, number, number];
}) {
  const active = useInsertStore((s) => s.holeBrushActive);
  const brushSize = useInsertStore((s) => s.holeBrushSize);
  const brushMode = useInsertStore((s) => s.brushMode);
  const holeRegions = useInsertStore((s) => s.holeBrushRegions);
  const ribRegions = useInsertStore((s) => s.ribBrushRegions);
  const addHoleRegion = useInsertStore((s) => s.addHoleBrushRegion);
  const addRibRegion = useInsertStore((s) => s.addRibBrushRegion);
  const isPainting = useRef(false);

  const { up, uAx, vAx, centre } = useMemo(() => {
    const _up = new THREE.Vector3(...plateNormal).normalize();
    const arb =
      Math.abs(_up.x) < 0.9
        ? new THREE.Vector3(1, 0, 0)
        : new THREE.Vector3(0, 1, 0);
    const _uAx = new THREE.Vector3().crossVectors(_up, arb).normalize();
    const _vAx = new THREE.Vector3().crossVectors(_up, _uAx).normalize();
    return {
      up: _up,
      uAx: _uAx,
      vAx: _vAx,
      centre: new THREE.Vector3(...plateCentre),
    };
  }, [plateNormal, plateCentre]);

  const projectToUV = useCallback(
    (point: THREE.Vector3) => {
      const delta = point.clone().sub(centre);
      return { u: delta.dot(uAx), v: delta.dot(vAx) };
    },
    [centre, uAx, vAx],
  );

  const addRegion = brushMode === "ribs" ? addRibRegion : addHoleRegion;

  const paintAt = useCallback(
    (event: THREE.Event & { point?: THREE.Vector3 }) => {
      if (!active || !event.point) return;
      const { u, v } = projectToUV(event.point);
      addRegion({ u, v, radius: brushSize });
    },
    [active, brushSize, addRegion, projectToUV],
  );

  const onPointerDown = useCallback(
    (e: THREE.Event) => {
      if (!active) return;
      isPainting.current = true;
      paintAt(e as THREE.Event & { point?: THREE.Vector3 });
    },
    [active, paintAt],
  );

  const onPointerMove = useCallback(
    (e: THREE.Event) => {
      if (!active || !isPainting.current) return;
      paintAt(e as THREE.Event & { point?: THREE.Vector3 });
    },
    [active, paintAt],
  );

  const onPointerUp = useCallback(() => {
    isPainting.current = false;
  }, []);

  if (!active) return null;

  const planeQuat = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 0, 1),
    up,
  );
  const planeRotation = new THREE.Euler().setFromQuaternion(planeQuat);

  const holeColor = 0xff3355;
  const ribColor = 0x3388ff;

  return (
    <group>
      {/* Invisible plane to catch raycasts */}
      <mesh
        visible={false}
        position={centre}
        rotation={planeRotation}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <planeGeometry args={[500, 500]} />
        <meshBasicMaterial transparent opacity={0} side={THREE.DoubleSide} />
      </mesh>

      {/* Hole region feedback */}
      {holeRegions.map((r, i) => {
        const pos = centre
          .clone()
          .add(uAx.clone().multiplyScalar(r.u))
          .add(vAx.clone().multiplyScalar(r.v))
          .add(up.clone().multiplyScalar(0.5));
        return (
          <mesh key={`h-${i}`} position={pos} rotation={planeRotation}>
            <circleGeometry args={[r.radius, 32]} />
            <meshBasicMaterial
              color={holeColor}
              transparent
              opacity={0.25}
              side={THREE.DoubleSide}
              depthWrite={false}
            />
          </mesh>
        );
      })}

      {/* Rib region feedback */}
      {ribRegions.map((r, i) => {
        const pos = centre
          .clone()
          .add(uAx.clone().multiplyScalar(r.u))
          .add(vAx.clone().multiplyScalar(r.v))
          .add(up.clone().multiplyScalar(0.5));
        return (
          <mesh key={`r-${i}`} position={pos} rotation={planeRotation}>
            <circleGeometry args={[r.radius, 32]} />
            <meshBasicMaterial
              color={ribColor}
              transparent
              opacity={0.25}
              side={THREE.DoubleSide}
              depthWrite={false}
            />
          </mesh>
        );
      })}
    </group>
  );
}
