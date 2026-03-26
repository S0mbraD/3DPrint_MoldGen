import { Canvas, useThree } from "@react-three/fiber";
import {
  OrbitControls, Grid, Environment, GizmoHelper, GizmoViewport, Line,
} from "@react-three/drei";
import { Suspense, useMemo, useState, useRef, useEffect } from "react";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useSimStore } from "../../stores/simStore";
import { useAppStore, type WorkflowStep } from "../../stores/appStore";
import {
  useViewportStore, GRID_CONFIGS, DISPLAY_MODE_LABELS,
  type DisplayMode, type GridUnit,
} from "../../stores/viewportStore";
import { ModelViewer } from "./ModelViewer";
import { MoldShellViewer } from "./MoldShellViewer";
import { InsertPlateViewer } from "./InsertPlateViewer";
import { HoleBrushPainter } from "./HoleBrushPainter";
import { SimulationViewer, StreamlineViewer, DefectMarkers, SurfaceOverlayViewer, FEAViewer } from "./SimulationViewer";
import { SimFloatingBar } from "./SimFloatingBar";
import { useInsertStore } from "../../stores/insertStore";
import { useRepairModel, useSimplifyModel, useTransformModel } from "../../hooks/useModelApi";
import { toastSuccess, toastError } from "../../stores/toastStore";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/utils";
import {
  RotateCcw, Scissors, Maximize2, FlipVertical, ArrowUpDown,
  RotateCw, Ruler, ChevronDown, Palette, Move, Loader2,
} from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════ */
/*  Main Viewport                                                     */
/* ═══════════════════════════════════════════════════════════════════ */

export function Viewport() {
  const hasModel = useModelStore((s) => !!s.glbUrl);
  const orientationResult = useMoldStore((s) => s.orientationResult);
  const moldResult = useMoldStore((s) => s.moldResult);
  const moldId = useMoldStore((s) => s.moldId);
  const hasVisualization = useSimStore((s) => !!s.visualizationData);
  const heatmapVisible = useSimStore((s) => s.heatmapVisible);
  const hasSurfaceMap = useSimStore((s) => !!s.surfaceMapData);
  const hasFEA = useSimStore((s) => !!s.feaVisualizationData);
  const moldVisible = useViewportStore((s) => s.moldVisible);
  const insertId = useInsertStore((s) => s.insertId);
  const insertPlates = useInsertStore((s) => s.plates);
  const insertVisible = useViewportStore((s) => s.insertVisible);
  const insertOpacity = useViewportStore((s) => s.insertOpacity);
  const hasInserts = !!insertId && insertPlates.length > 0;

  const gridUnit = useViewportStore((s) => s.gridUnit);
  const gridConfig = GRID_CONFIGS[gridUnit];

  return (
    <div className="flex-1 relative">
      <Canvas
        camera={{ position: [200, 150, 200], fov: 50, near: 0.1, far: 10000 }}
        gl={{ antialias: true }}
        className="!absolute inset-0"
      >
        <color attach="background" args={["#13131a"]} />
        <fog attach="fog" args={["#13131a", 1000, 3000]} />

        <ambientLight intensity={0.4} />
        <directionalLight position={[300, 500, 200]} intensity={1.2} castShadow />
        <directionalLight position={[-200, 300, -100]} intensity={0.3} />

        <Suspense fallback={null}>
          <Grid
            args={[1000, 1000]}
            cellSize={gridConfig.cellSize}
            cellThickness={0.5}
            cellColor="#1e1e2e"
            sectionSize={gridConfig.sectionSize}
            sectionThickness={1}
            sectionColor="#2a2a3e"
            fadeDistance={gridConfig.fadeDistance}
            infiniteGrid
          />

          {hasModel ? <ModelViewer /> : <PlaceholderModel />}

          {orientationResult && (
            <DirectionArrow direction={orientationResult.best_direction} />
          )}

          {moldId && moldResult && moldVisible &&
            !(heatmapVisible && hasVisualization) &&
            moldResult.shells.map((sh) => (
              <MoldShellViewer
                key={sh.shell_id}
                moldId={moldId}
                shellId={sh.shell_id}
              />
            ))}

          {hasInserts && insertVisible && insertId &&
            insertPlates.map((_p, idx) => (
              <InsertPlateViewer
                key={`insert-${insertId}-${idx}`}
                insertId={insertId}
                plateIndex={idx}
                opacity={insertOpacity}
                visible={insertVisible}
              />
            ))}

          {hasInserts && insertPlates[0]?.position && (
            <HoleBrushPainter
              plateNormal={(insertPlates[0].position?.normal ?? [0,0,1]) as [number,number,number]}
              plateCentre={(insertPlates[0].position?.origin ?? [0,0,0]) as [number,number,number]}
            />
          )}

          {hasVisualization && <SimulationViewer />}
          {hasVisualization && <StreamlineViewer />}
          {hasVisualization && <DefectMarkers />}
          {hasSurfaceMap && <SurfaceOverlayViewer />}
          {hasFEA && <FEAViewer />}
        </Suspense>

        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.1}
          minDistance={1}
          maxDistance={5000}
        />

        <CameraAutoFit />

        <GizmoHelper alignment="bottom-right" margin={[60, 60]}>
          <GizmoViewport labelColor="white" axisHeadScale={0.8} />
        </GizmoHelper>

        <Environment preset="city" background={false} />
      </Canvas>

      {/* Floating edit toolbar (left) */}
      <FloatingEditToolbar />

      {/* Display mode switcher (top-left, below hints) */}
      <DisplayModeSwitcher />

      {/* Scale unit switcher (top-right) */}
      <ScaleUnitSwitcher />

      {/* Viewport hints & step info */}
      <ViewportOverlay />

      {/* Heatmap legend */}
      {hasVisualization && heatmapVisible && <HeatmapLegend />}

      {/* Floating simulation controls bar */}
      <SimFloatingBar />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  Auto-fit camera to model on load                                  */
/* ═══════════════════════════════════════════════════════════════════ */

function CameraAutoFit() {
  const meshInfo = useModelStore((s) => s.meshInfo);
  const modelId = useModelStore((s) => s.modelId);
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls);
  const prevModelRef = useRef<string | null>(null);

  useEffect(() => {
    if (!meshInfo?.center || !controls) return;

    const [cx, cy, cz] = meshInfo.center;
    const maxExtent = Math.max(...meshInfo.extents);
    const dist = maxExtent * 2.5;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ctrl = controls as any;
    ctrl.target.set(cx, cy, cz);

    if (prevModelRef.current !== modelId) {
      camera.position.set(cx + dist * 0.8, cy + dist * 0.5, cz + dist * 0.8);
      camera.updateProjectionMatrix();
      prevModelRef.current = modelId;
    }

    ctrl.update();
  }, [meshInfo, camera, controls, modelId]);

  return null;
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  Floating Edit Toolbar (left side of viewport)                     */
/* ═══════════════════════════════════════════════════════════════════ */

function FloatingEditToolbar() {
  const modelId = useModelStore((s) => s.modelId);
  const updateInfo = useModelStore((s) => s.updateMeshInfo);
  const bumpGlb = useModelStore((s) => s.bumpGlbRevision);
  const repair = useRepairModel();
  const simplify = useSimplifyModel();
  const transform = useTransformModel();

  if (!modelId) return null;

  const isLoading = repair.isPending || simplify.isPending || transform.isPending;

  const exec = async (label: string, action: () => Promise<Record<string, unknown>>) => {
    try {
      const data = await action();
      if (data?.mesh_info) {
        updateInfo(data.mesh_info as Parameters<typeof updateInfo>[0]);
        bumpGlb();
      }
      toastSuccess(`${label}完成`);
    } catch (e) {
      toastError(`${label}失败`, (e as Error)?.message);
    }
  };

  const tools: {
    id: string;
    icon: React.ReactNode;
    label: string;
    action: () => void;
    divider?: boolean;
  }[] = [
    {
      id: "repair", icon: <RotateCcw size={14} />, label: "自动修复",
      action: () => exec("修复", () => repair.mutateAsync(modelId)),
    },
    {
      id: "simplify", icon: <Scissors size={14} />, label: "快速简化 50%",
      action: () => exec("简化", () => simplify.mutateAsync({ modelId, ratio: 0.5 })),
    },
    {
      id: "center", icon: <Maximize2 size={14} />, label: "居中", divider: true,
      action: () => exec("居中", () => transform.mutateAsync({ modelId, operation: "center" })),
    },
    {
      id: "floor", icon: <Move size={14} />, label: "落地",
      action: () => exec("落地", () => transform.mutateAsync({ modelId, operation: "align_to_floor" })),
    },
    {
      id: "flip", icon: <FlipVertical size={14} />, label: "翻转 Z",
      action: () => exec("翻转", () => transform.mutateAsync({ modelId, operation: "mirror", plane_normal: [0, 0, 1] })),
    },
    {
      id: "mirror", icon: <ArrowUpDown size={14} />, label: "镜像 X",
      action: () => exec("镜像", () => transform.mutateAsync({ modelId, operation: "mirror", plane_normal: [1, 0, 0] })),
    },
    {
      id: "rot_x", icon: <RotateCw size={14} />, label: "X +90°", divider: true,
      action: () => exec("旋转X", () => transform.mutateAsync({ modelId, operation: "rotate", axis: [1, 0, 0], angle_deg: 90 })),
    },
    {
      id: "rot_y", icon: <RotateCw size={14} />, label: "Y +90°",
      action: () => exec("旋转Y", () => transform.mutateAsync({ modelId, operation: "rotate", axis: [0, 1, 0], angle_deg: 90 })),
    },
    {
      id: "rot_z", icon: <RotateCw size={14} />, label: "Z +90°",
      action: () => exec("旋转Z", () => transform.mutateAsync({ modelId, operation: "rotate", axis: [0, 0, 1], angle_deg: 90 })),
    },
  ];

  return (
    <div className="absolute left-3 top-1/2 -translate-y-1/2 z-10">
      <motion.div
        initial={{ opacity: 0, x: -12 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex flex-col gap-0.5 p-1 rounded-lg bg-bg-secondary/80 backdrop-blur-sm border border-border/50 shadow-lg"
      >
        {isLoading && (
          <div className="flex items-center justify-center py-1">
            <Loader2 size={12} className="animate-spin text-accent" />
          </div>
        )}
        {tools.map((tool) => (
          <div key={tool.id}>
            {tool.divider && <div className="h-px bg-border/50 my-0.5" />}
            <button
              onClick={tool.action}
              disabled={isLoading}
              className={cn(
                "p-1.5 rounded hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors group relative",
                isLoading && "opacity-40 cursor-not-allowed",
              )}
              title={tool.label}
            >
              {tool.icon}
              <span className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-0.5 rounded bg-bg-primary border border-border text-[9px] text-text-secondary whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-lg z-20">
                {tool.label}
              </span>
            </button>
          </div>
        ))}
      </motion.div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  Display Mode Switcher (top-left)                                  */
/* ═══════════════════════════════════════════════════════════════════ */

function DisplayModeSwitcher() {
  const [open, setOpen] = useState(false);
  const displayMode = useViewportStore((s) => s.displayMode);
  const setDisplayMode = useViewportStore((s) => s.setDisplayMode);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="absolute top-8 left-3 z-10">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 px-2 py-1 rounded bg-bg-secondary/80 backdrop-blur-sm border border-border/50 text-[10px] text-text-muted hover:text-text-primary transition-colors"
      >
        <Palette size={10} />
        <span>材质: {DISPLAY_MODE_LABELS[displayMode]}</span>
        <ChevronDown
          size={9}
          className={cn("transition-transform", open && "rotate-180")}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="mt-1 p-1 rounded-md bg-bg-secondary/95 backdrop-blur-sm border border-border/60 shadow-lg min-w-[100px]"
          >
            {(Object.keys(DISPLAY_MODE_LABELS) as DisplayMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => { setDisplayMode(mode); setOpen(false); }}
                className={cn(
                  "w-full text-left px-2 py-1 rounded text-[10px] transition-colors",
                  displayMode === mode
                    ? "bg-accent/20 text-accent"
                    : "text-text-muted hover:bg-bg-hover hover:text-text-primary",
                )}
              >
                {DISPLAY_MODE_LABELS[mode]}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  Scale Unit Switcher (top-right)                                   */
/* ═══════════════════════════════════════════════════════════════════ */

function ScaleUnitSwitcher() {
  const [open, setOpen] = useState(false);
  const gridUnit = useViewportStore((s) => s.gridUnit);
  const setGridUnit = useViewportStore((s) => s.setGridUnit);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const labels: Record<GridUnit, string> = {
    mm: "1格 = 1mm",
    cm: "1格 = 1cm",
    m: "1格 = 1m",
    inch: "1格 = 1inch",
  };

  return (
    <div ref={ref} className="absolute top-3 right-3 z-10">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 px-2 py-1 rounded bg-bg-secondary/80 backdrop-blur-sm border border-border/50 text-[10px] text-text-muted hover:text-text-primary transition-colors"
      >
        <Ruler size={10} />
        <span>{labels[gridUnit]}</span>
        <ChevronDown
          size={9}
          className={cn("transition-transform", open && "rotate-180")}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="mt-1 p-1 rounded-md bg-bg-secondary/95 backdrop-blur-sm border border-border/60 shadow-lg"
          >
            {(Object.keys(labels) as GridUnit[]).map((unit) => (
              <button
                key={unit}
                onClick={() => { setGridUnit(unit); setOpen(false); }}
                className={cn(
                  "w-full text-left px-2 py-1 rounded text-[10px] transition-colors",
                  gridUnit === unit
                    ? "bg-accent/20 text-accent"
                    : "text-text-muted hover:bg-bg-hover hover:text-text-primary",
                )}
              >
                {labels[unit]}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  Heatmap Legend                                                     */
/* ═══════════════════════════════════════════════════════════════════ */

function HeatmapLegend() {
  const field = useSimStore((s) => s.heatmapField);
  const visData = useSimStore((s) => s.visualizationData);
  const progress = useSimStore((s) => s.animationProgress);

  const FIELD_LABELS: Record<string, { label: string; unit: string }> = {
    fill_time: { label: "充填时间", unit: "s" },
    pressure: { label: "压力", unit: "Pa" },
    velocity: { label: "流速", unit: "mm/s" },
    shear_rate: { label: "剪切率", unit: "1/s" },
    temperature: { label: "温度", unit: "°C" },
    cure_progress: { label: "固化进度", unit: "%" },
    thickness: { label: "壁厚", unit: "mm" },
  };

  const info = FIELD_LABELS[field] ?? { label: field, unit: "" };

  const maxVal = useMemo(() => {
    if (!visData) return 1;
    const m: Record<string, number> = {
      fill_time: visData.max_fill_time,
      pressure: visData.max_pressure,
      velocity: visData.max_velocity,
      shear_rate: visData.max_shear_rate,
      temperature: visData.temperature_range[1],
      cure_progress: 100,
      thickness: visData.max_thickness,
    };
    return m[field] ?? 1;
  }, [visData, field]);

  const minVal = useMemo(() => {
    if (!visData) return 0;
    if (field === "temperature") return visData.temperature_range[0];
    return 0;
  }, [visData, field]);

  return (
    <div className="absolute bottom-14 right-3 pointer-events-none">
      <div className="bg-bg-secondary/90 backdrop-blur-sm border border-border/60 rounded-lg px-3 py-2 text-[10px] min-w-[140px]">
        <div className="font-semibold text-text-secondary mb-1.5">{info.label}</div>
        <div
          className="h-3 rounded-sm mb-1"
          style={{
            background: "linear-gradient(90deg, #0d0d80, #0080cc, #1acc4d, #f2d90b, #e62619)",
          }}
        />
        <div className="flex justify-between text-text-muted">
          <span>{minVal.toFixed(field === "cure_progress" ? 0 : 1)}</span>
          <span>
            {maxVal.toFixed(field === "cure_progress" ? 0 : 1)} {info.unit}
          </span>
        </div>
        <div className="mt-1 pt-1 border-t border-border/50 text-text-muted">
          进度: {(progress * 100).toFixed(0)}%
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  3-D Helpers                                                       */
/* ═══════════════════════════════════════════════════════════════════ */

function DirectionArrow({ direction }: { direction: number[] }) {
  const points = useMemo(() => {
    const len = 100;
    const start: [number, number, number] = [0, 0, 0];
    const end: [number, number, number] = [
      direction[0] * len,
      direction[1] * len,
      direction[2] * len,
    ];
    return [start, end];
  }, [direction]);

  return <Line points={points} color="#f59e0b" lineWidth={3} dashed={false} />;
}

function PlaceholderModel() {
  return (
    <mesh position={[0, 25, 0]} castShadow>
      <boxGeometry args={[50, 50, 50]} />
      <meshStandardMaterial
        color="#6366f1"
        roughness={0.3}
        metalness={0.1}
        transparent
        opacity={0.3}
        wireframe
      />
    </mesh>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
/*  Viewport Overlay (hints + step badge)                             */
/* ═══════════════════════════════════════════════════════════════════ */

const STEP_HINTS: Record<WorkflowStep, string> = {
  import: "上传 3D 模型文件开始工作",
  repair: "检查并修复模型网格质量",
  orientation: "分析最佳脱模方向（黄色箭头）",
  mold: "生成分型面和多片模具壳体",
  insert: "生成内嵌支撑板并验证装配",
  gating: "设计浇注口、浇道和排气系统",
  simulation: "模拟灌注流动并自动优化",
  export: "导出模型、模具和支撑板文件",
};

const STEP_LABELS: Record<WorkflowStep, string> = {
  import: "导入",
  repair: "编辑",
  orientation: "方向",
  mold: "模具",
  insert: "支撑板",
  gating: "浇注",
  simulation: "仿真",
  export: "导出",
};

function ViewportOverlay() {
  const currentStep = useAppStore((s) => s.currentStep);
  const modelLoaded = useAppStore((s) => s.modelLoaded);

  return (
    <>
      {/* Keyboard hints (top, centered) */}
      <div className="absolute top-2 left-1/2 -translate-x-1/2 pointer-events-none">
        <div className="text-[9px] text-text-muted/40 whitespace-nowrap">
          鼠标左键: 旋转 | 右键: 平移 | 滚轮: 缩放 | Ctrl+1~8: 切换步骤
        </div>
      </div>

      {/* Current step badge (bottom-left) */}
      <div className="absolute bottom-3 left-3 pointer-events-none">
        <div className="px-2.5 py-1.5 rounded-md bg-bg-secondary/80 backdrop-blur-sm border border-border/50 text-[10px] text-text-secondary">
          <span className="text-accent font-medium mr-1.5">
            {STEP_LABELS[currentStep]}
          </span>
          {STEP_HINTS[currentStep]}
        </div>
      </div>

      {/* No-model prompt */}
      {!modelLoaded && currentStep !== "import" && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none text-center">
          <div className="text-text-muted/30 text-sm">请先导入模型</div>
        </div>
      )}
    </>
  );
}
