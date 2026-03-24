import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, Upload, Settings, Loader2, Scissors, Maximize2, RotateCcw, Compass, SplitSquareVertical, Box, Droplets, Zap, RefreshCw, Pin, CheckCircle2, Download, Package, Grid3x3, FlipVertical, ArrowUpDown, RotateCw, ZoomIn, ZoomOut, FileText, Play, Pause, RotateCcw as Rewind, Eye, EyeOff, Layers, ThermometerSun, Activity, Timer, Gauge, Slice, ChevronDown, ChevronUp, BarChart3, Lightbulb } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../../stores/appStore";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useSimStore } from "../../stores/simStore";
import { useInsertStore } from "../../stores/insertStore";
import { useUploadModel, useSimplifyModel, useSubdivideModel, useTransformModel, useRepairModel } from "../../hooks/useModelApi";
import { useOrientationAnalysis, usePartingGeneration, useMoldGeneration } from "../../hooks/useMoldApi";
import { useGatingDesign, useRunSimulation, useRunOptimization, useFetchVisualization, useFetchCrossSection, useFetchSurfaceMap, useRunFEA, useFetchFEAVisualization } from "../../hooks/useSimApi";
import type { HeatmapField } from "../../stores/simStore";
import { useAnalyzePositions, useGenerateInserts, useValidateAssembly } from "../../hooks/useInsertApi";
import { useExportModel, useExportMold, useExportInsert, useExportAll } from "../../hooks/useExportApi";
import { StepToolbar } from "./StepToolbar";
import { cn } from "../../lib/utils";
import { toastSuccess, toastError, toastInfo } from "../../stores/toastStore";

export function LeftPanel() {
  const { leftPanelOpen, toggleLeftPanel, currentStep } = useAppStore();

  return (
    <AnimatePresence initial={false}>
      {leftPanelOpen && (
        <motion.div
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 280, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="h-full bg-bg-panel border-r border-border overflow-hidden flex flex-col"
        >
          <div className="flex items-center justify-between px-3 h-9 border-b border-border shrink-0">
            <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              参数面板
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => useAppStore.getState().toggleSettings()}
                className="p-1 rounded hover:bg-bg-hover text-text-muted"
                title="设置"
              >
                <Settings size={13} />
              </button>
              <button onClick={toggleLeftPanel} className="p-1 rounded hover:bg-bg-hover text-text-muted">
                <ChevronLeft size={14} />
              </button>
            </div>
          </div>

          {/* Step-specific toolbar — wired to panel actions */}
          <StepToolbar step={currentStep} onAction={(id) => {
            window.dispatchEvent(new CustomEvent("moldgen:toolbar-action", { detail: id }));
          }} />

          <div className="flex-1 overflow-y-auto p-3 space-y-4">
            {currentStep === "import" && <ImportPanel />}
            {currentStep === "repair" && <EditPanel />}
            {currentStep === "orientation" && <OrientationPanel />}
            {currentStep === "mold" && <MoldPanel />}
            {currentStep === "insert" && <InsertPanel />}
            {currentStep === "gating" && <GatingPanel />}
            {currentStep === "simulation" && <SimPanel />}
            {currentStep === "export" && <ExportPanel />}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function ImportPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadModel();
  const { setModel } = useModelStore();
  const { setStep, setModelInfo } = useAppStore();
  const [isDragging, setIsDragging] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      try {
        const data = await upload.mutateAsync(file);
        setModel(data.model_id, data.filename, data.mesh_info);
        setModelInfo(data.filename, data.mesh_info.face_count);
        setStep("repair");
        toastSuccess("模型已导入", `${data.filename} — ${data.mesh_info.face_count.toLocaleString()} 面`);
      } catch (e) {
        toastError("导入失败", (e as Error)?.message ?? "未知错误");
      }
    },
    [upload, setModel, setModelInfo, setStep],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  return (
    <div className="space-y-3">
      <Section title="模型导入">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          disabled={upload.isPending}
          className={cn(
            "w-full flex flex-col items-center justify-center gap-2 py-6 rounded-lg border-2 border-dashed transition-all",
            upload.isPending
              ? "border-accent/50 text-accent/50"
              : isDragging
                ? "border-accent bg-accent/10 text-accent scale-[1.02]"
                : "border-border hover:border-accent text-text-secondary hover:text-accent",
          )}
        >
          {upload.isPending ? (
            <Loader2 size={24} className="animate-spin" />
          ) : isDragging ? (
            <Download size={24} />
          ) : (
            <Upload size={24} />
          )}
          <span className="text-sm">
            {upload.isPending ? "加载中..." : isDragging ? "释放以导入" : "拖拽或点击上传模型"}
          </span>
          {!upload.isPending && !isDragging && (
            <span className="text-[10px] text-text-muted">
              最大 200MB
            </span>
          )}
        </motion.button>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept=".stl,.obj,.fbx,.3mf,.ply,.step,.stp,.gltf,.glb,.amf,.dae,.off"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
        {upload.isError && (
          <p className="text-[10px] text-danger mt-1">
            上传失败: {(upload.error as Error)?.message}
          </p>
        )}
      </Section>

      <Section title="支持格式">
        <div className="grid grid-cols-2 gap-1">
          {[
            { ext: "STL", desc: "FDM 打印标准" },
            { ext: "OBJ", desc: "通用网格" },
            { ext: "FBX", desc: "Autodesk" },
            { ext: "3MF", desc: "现代3D打印" },
            { ext: "STEP", desc: "CAD 工程格式" },
            { ext: "PLY", desc: "点云/网格" },
            { ext: "glTF", desc: "Web 3D" },
            { ext: "DAE", desc: "COLLADA" },
          ].map((f) => (
            <div key={f.ext} className="flex items-center gap-1.5 p-1 rounded bg-bg-secondary text-[10px]">
              <span className="text-accent font-mono font-bold w-8">{f.ext}</span>
              <span className="text-text-muted">{f.desc}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="快速开始">
        <div className="p-2 rounded border border-border bg-bg-secondary/50 text-[10px] text-text-muted space-y-1.5">
          <p><span className="text-text-secondary font-medium">1.</span> 上传或拖拽 3D 模型文件</p>
          <p><span className="text-text-secondary font-medium">2.</span> 编辑面板中修复/简化模型</p>
          <p><span className="text-text-secondary font-medium">3.</span> 自动分析脱模方向，生成模具</p>
          <p><span className="text-text-secondary font-medium">4.</span> 运行仿真优化，导出生产文件</p>
          <p className="pt-1 border-t border-border/50 text-accent">
            也可通过 AI 助手对话自动完成全流程
          </p>
        </div>
      </Section>
    </div>
  );
}

function EditPanel() {
  const modelId = useModelStore((s) => s.modelId);
  const meshInfo = useModelStore((s) => s.meshInfo);
  const bumpGlb = useModelStore((s) => s.bumpGlbRevision);
  const updateInfo = useModelStore((s) => s.updateMeshInfo);
  const repair = useRepairModel();
  const simplify = useSimplifyModel();
  const subdivide = useSubdivideModel();
  const transform = useTransformModel();
  const [targetRatio, setTargetRatio] = useState(0.5);
  const [subdivIter, setSubdivIter] = useState(1);
  const [scaleVal, setScaleVal] = useState(1.0);

  const toolbarRef = useRef<(id: string) => void>(() => {});

  const handleAction = async (label: string, action: () => Promise<{ mesh_info?: unknown }>) => {
    try {
      const data = await action();
      if (data && (data as { mesh_info?: unknown }).mesh_info) {
        updateInfo((data as { mesh_info: typeof meshInfo }).mesh_info!);
        bumpGlb();
      }
      toastSuccess(`${label}完成`);
    } catch (e) {
      toastError(`${label}失败`, (e as Error)?.message);
    }
  };

  toolbarRef.current = (id: string) => {
    if (!modelId) return;
    const actions: Record<string, () => void> = {
      auto_repair: () => handleAction("自动修复", () => repair.mutateAsync(modelId)),
      simplify: () => handleAction("简化", () => simplify.mutateAsync({ modelId, ratio: targetRatio })),
      subdivide: () => handleAction("细分", () => subdivide.mutateAsync({ modelId, iterations: subdivIter })),
      center: () => handleAction("居中", () => transform.mutateAsync({ modelId, operation: "center" })),
      d_transform: () => handleAction("居中", () => transform.mutateAsync({ modelId, operation: "center" })),
      rotate: () => handleAction("旋转", () => transform.mutateAsync({ modelId, operation: "rotate", axis: [0, 1, 0], angle_deg: 90 })),
      scale_up: () => handleAction("放大", () => transform.mutateAsync({ modelId, operation: "scale", factor: 1.5 })),
      scale_down: () => handleAction("缩小", () => transform.mutateAsync({ modelId, operation: "scale", factor: 0.67 })),
      flip: () => handleAction("翻转", () => transform.mutateAsync({ modelId, operation: "mirror", plane_normal: [0, 0, 1] })),
      mirror: () => handleAction("镜像", () => transform.mutateAsync({ modelId, operation: "mirror", plane_normal: [1, 0, 0] })),
      d_measure: () => toastInfo("测量功能 — 请查看右侧面板中的尺寸信息"),
    };
    actions[id]?.();
  };

  useEffect(() => {
    const handler = (e: Event) => {
      toolbarRef.current((e as CustomEvent).detail as string);
    };
    window.addEventListener("moldgen:toolbar-action", handler);
    return () => window.removeEventListener("moldgen:toolbar-action", handler);
  }, []);

  if (!modelId) return null;

  return (
    <div className="space-y-4">
      <Section title="修复">
        <ActionButton
          icon={<RotateCcw size={13} />}
          label="自动修复"
          loading={repair.isPending}
          onClick={() => handleAction("自动修复", () => repair.mutateAsync(modelId))}
        />
      </Section>

      <Section title="简化">
        <div className="flex items-center gap-2 mb-2">
          <input
            type="range"
            min={0.05}
            max={1}
            step={0.05}
            value={targetRatio}
            onChange={(e) => setTargetRatio(parseFloat(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-[10px] text-text-muted w-8">{Math.round(targetRatio * 100)}%</span>
        </div>
        <ActionButton
          icon={<Scissors size={13} />}
          label={`简化到 ${meshInfo ? Math.round(meshInfo.face_count * targetRatio).toLocaleString() : "?"} 面`}
          loading={simplify.isPending}
          onClick={() => handleAction("简化", () => simplify.mutateAsync({ modelId, ratio: targetRatio }))}
        />
      </Section>

      <Section title="细分">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[10px] text-text-muted shrink-0">迭代</span>
          <input
            type="range"
            min={1}
            max={4}
            step={1}
            value={subdivIter}
            onChange={(e) => setSubdivIter(parseInt(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-[10px] text-text-muted w-4">{subdivIter}</span>
        </div>
        <ActionButton
          icon={<Grid3x3 size={13} />}
          label={`Loop 细分 ×${subdivIter}`}
          loading={subdivide.isPending}
          onClick={() => handleAction("细分", () => subdivide.mutateAsync({ modelId, iterations: subdivIter }))}
        />
      </Section>

      <Section title="变换">
        <div className="grid grid-cols-2 gap-1.5">
          <ActionButton
            icon={<Maximize2 size={13} />}
            label="居中"
            loading={transform.isPending}
            onClick={() => handleAction("居中", () => transform.mutateAsync({ modelId, operation: "center" }))}
          />
          <ActionButton
            label="落地"
            loading={transform.isPending}
            onClick={() => handleAction("落地", () => transform.mutateAsync({ modelId, operation: "align_to_floor" }))}
          />
          <ActionButton
            icon={<FlipVertical size={13} />}
            label="翻转 Z"
            loading={transform.isPending}
            onClick={() => handleAction("翻转", () => transform.mutateAsync({ modelId, operation: "mirror", plane_normal: [0, 0, 1] }))}
          />
          <ActionButton
            icon={<ArrowUpDown size={13} />}
            label="镜像 X"
            loading={transform.isPending}
            onClick={() => handleAction("镜像", () => transform.mutateAsync({ modelId, operation: "mirror", plane_normal: [1, 0, 0] }))}
          />
        </div>
      </Section>

      <Section title="旋转">
        <div className="grid grid-cols-3 gap-1.5">
          {([
            { key: "x", vec: [1, 0, 0] },
            { key: "y", vec: [0, 1, 0] },
            { key: "z", vec: [0, 0, 1] },
          ] as const).map(({ key, vec }) => (
            <ActionButton
              key={key}
              icon={<RotateCw size={13} />}
              label={`${key.toUpperCase()} +90°`}
              loading={transform.isPending}
              onClick={() => handleAction(`旋转${key.toUpperCase()}`, () => transform.mutateAsync({ modelId, operation: "rotate", axis: [...vec], angle_deg: 90 }))}
            />
          ))}
        </div>
      </Section>

      <Section title="缩放">
        <div className="flex items-center gap-2 mb-2">
          <ZoomOut size={11} className="text-text-muted shrink-0" />
          <input
            type="range"
            min={0.1}
            max={5}
            step={0.1}
            value={scaleVal}
            onChange={(e) => setScaleVal(parseFloat(e.target.value))}
            className="flex-1 accent-accent"
          />
          <ZoomIn size={11} className="text-text-muted shrink-0" />
          <span className="text-[10px] text-text-muted w-10 text-right">{scaleVal.toFixed(1)}×</span>
        </div>
        <ActionButton
          icon={<Maximize2 size={13} />}
          label={`缩放 ${scaleVal.toFixed(1)}×`}
          loading={transform.isPending}
          onClick={() => handleAction("缩放", () => transform.mutateAsync({ modelId, operation: "scale", factor: scaleVal }))}
        />
      </Section>

      <Section title="测量 (只读)">
        {meshInfo && (
          <div className="p-2 rounded bg-bg-secondary text-[10px] space-y-1">
            <div className="flex justify-between">
              <span className="text-text-muted">顶点数</span>
              <span className="font-mono">{meshInfo.vertex_count.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">面数</span>
              <span className="font-mono">{meshInfo.face_count.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">尺寸 (mm)</span>
              <span className="font-mono">
                {meshInfo.extents?.[0]?.toFixed(1)} × {meshInfo.extents?.[1]?.toFixed(1)} × {meshInfo.extents?.[2]?.toFixed(1)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">表面积</span>
              <span className="font-mono">{meshInfo.surface_area?.toFixed(1)} mm²</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">体积</span>
              <span className="font-mono">{meshInfo.volume ? `${meshInfo.volume.toFixed(1)} mm³` : "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">水密</span>
              <span className={meshInfo.is_watertight ? "text-success" : "text-warning"}>
                {meshInfo.is_watertight ? "✓ 是" : "✗ 否"}
              </span>
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}

function OrientationPanel() {
  const modelId = useModelStore((s) => s.modelId);
  const { orientationResult, isAnalyzing, selectedCandidateIdx } = useMoldStore();
  const setSelectedCandidate = useMoldStore((s) => s.setSelectedCandidate);
  const setOrientationResult = useMoldStore((s) => s.setOrientationResult);
  const orientation = useOrientationAnalysis();
  const [nSamples, setNSamples] = useState(100);
  const [nFinal, setNFinal] = useState(5);
  const [manualDir, setManualDir] = useState([0, 0, 1]);

  if (!modelId) {
    return (
      <div className="text-center text-text-muted text-xs py-8">
        请先导入模型
      </div>
    );
  }

  const applyCandidate = (idx: number) => {
    if (!orientationResult) return;
    const c = orientationResult.top_candidates[idx];
    if (!c) return;
    setSelectedCandidate(idx);
    setOrientationResult({
      ...orientationResult,
      best_direction: c.direction,
      best_score: c,
    });
    toastInfo(`已应用候选方向 #${idx + 1}`);
  };

  return (
    <div className="space-y-4">
      <Section title="采样参数">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">Fibonacci 采样数</span>
            <div className="flex items-center gap-1">
              <input type="range" min={50} max={500} step={50} value={nSamples}
                onChange={(e) => setNSamples(parseInt(e.target.value))} className="w-20 accent-accent" />
              <span className="text-[10px] text-text-muted w-8 text-right">{nSamples}</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">精细候选数</span>
            <input type="number" min={3} max={20} value={nFinal}
              onChange={(e) => setNFinal(parseInt(e.target.value) || 5)}
              className="w-14 text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary text-right" />
          </div>
        </div>
      </Section>

      <Section title="分析">
        <ActionButton
          icon={<Compass size={13} />}
          label={isAnalyzing ? "分析中..." : "分析最优脱模方向"}
          loading={isAnalyzing}
          onClick={() => orientation.mutate({ modelId, nSamples, nFinal }, {
            onSuccess: (r) => toastSuccess("方向分析完成", `评分 ${(r.best_score.total_score * 100).toFixed(0)}%`),
            onError: (e) => toastError("分析失败", (e as Error).message),
          })}
        />
      </Section>

      {orientationResult && (
        <>
          <Section title="最佳方向">
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
              className="p-2 rounded bg-bg-secondary text-[10px] space-y-1.5">
              <div className="flex justify-between">
                <span className="text-text-muted">方向向量</span>
                <span className="text-text-primary font-mono">
                  [{orientationResult.best_direction.map((v) => v.toFixed(3)).join(", ")}]
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">综合评分</span>
                <span className="text-accent font-bold">
                  {(orientationResult.best_score.total_score * 100).toFixed(1)}%
                </span>
              </div>
              <div className="h-px bg-border" />
              <div className="flex justify-between">
                <span className="text-text-muted">可见率</span>
                <span>{(orientationResult.best_score.visibility_ratio * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">倒扣率</span>
                <span className={orientationResult.best_score.undercut_ratio > 0.1 ? "text-danger" : "text-success"}>
                  {(orientationResult.best_score.undercut_ratio * 100).toFixed(1)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">平坦度</span>
                <span>{(orientationResult.best_score.flatness * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">最小拔模角</span>
                <span>{orientationResult.best_score.min_draft_angle.toFixed(1)}°</span>
              </div>
              {orientationResult.best_score.mean_draft_angle != null && (
                <div className="flex justify-between">
                  <span className="text-text-muted">平均拔模角</span>
                  <span>{orientationResult.best_score.mean_draft_angle.toFixed(1)}°</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-text-muted">对称性</span>
                <span>{(orientationResult.best_score.symmetry * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">稳定性</span>
                <span>{(orientationResult.best_score.stability * 100).toFixed(1)}%</span>
              </div>
            </motion.div>
          </Section>

          <Section title={`候选方向 — 点击应用 (${orientationResult.top_candidates.length})`}>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {orientationResult.top_candidates.map((c, i) => (
                <motion.button key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  onClick={() => applyCandidate(i)}
                  className={cn(
                    "w-full flex items-center justify-between p-1.5 rounded text-[10px] transition-colors",
                    selectedCandidateIdx === i
                      ? "bg-accent/15 ring-1 ring-accent/40"
                      : "bg-bg-secondary hover:bg-bg-hover",
                  )}>
                  <span className={selectedCandidateIdx === i ? "text-accent font-bold" : "text-text-muted"}>#{i + 1}</span>
                  <span className="font-mono text-text-secondary text-[9px]">
                    [{c.direction.map((v) => v.toFixed(2)).join(", ")}]
                  </span>
                  <div className="flex items-center gap-1">
                    <span className="text-text-muted">{c.min_draft_angle.toFixed(1)}°</span>
                    <span className={cn(
                      "font-semibold",
                      c.total_score > 0.8 ? "text-success" : c.total_score > 0.5 ? "text-accent" : "text-warning",
                    )}>
                      {(c.total_score * 100).toFixed(0)}%
                    </span>
                  </div>
                </motion.button>
              ))}
            </div>
          </Section>

          <Section title="手动方向输入">
            <div className="flex items-center gap-1 mb-1.5">
              {(["X", "Y", "Z"] as const).map((axis, ai) => (
                <div key={axis} className="flex-1">
                  <label className="text-[9px] text-text-muted">{axis}</label>
                  <input
                    type="number" step={0.1} min={-1} max={1}
                    value={manualDir[ai]}
                    onChange={(e) => {
                      const nd = [...manualDir];
                      nd[ai] = parseFloat(e.target.value) || 0;
                      setManualDir(nd);
                    }}
                    className="w-full text-[10px] bg-bg-secondary border border-border rounded px-1 py-0.5 text-text-primary text-center"
                  />
                </div>
              ))}
            </div>
            <ActionButton
              icon={<RotateCw size={13} />}
              label="应用自定义方向"
              loading={false}
              onClick={() => {
                if (!orientationResult) return;
                const norm = Math.sqrt(manualDir[0] ** 2 + manualDir[1] ** 2 + manualDir[2] ** 2);
                if (norm < 0.01) { toastError("方向向量不能为零"); return; }
                const d = manualDir.map((v) => v / norm);
                setOrientationResult({
                  ...orientationResult,
                  best_direction: d,
                  best_score: { ...orientationResult.best_score, direction: d },
                });
                setSelectedCandidate(null);
                toastInfo("已应用自定义方向");
              }}
            />
          </Section>

          <div className="p-2 rounded border border-accent/20 bg-accent/5 text-[10px] text-text-secondary">
            <p className="font-medium text-accent mb-1">提示</p>
            <p>点击候选方向可直接切换。方向已自动应用到3D视口中（黄色箭头）。下一步请前往"模具"步骤生成分型面和壳体。</p>
          </div>
        </>
      )}
    </div>
  );
}

function MoldPanel() {
  const modelId = useModelStore((s) => s.modelId);
  const { orientationResult, partingResult, moldResult, isAnalyzing, isGeneratingParting, isGeneratingMold } = useMoldStore();
  const orientation = useOrientationAnalysis();
  const parting = usePartingGeneration();
  const moldGen = useMoldGeneration();
  const [wallThickness, setWallThickness] = useState(4.0);
  const [shellType, setShellType] = useState("box");
  const [partingStyle, setPartingStyle] = useState("flat");
  const [addFlanges, setAddFlanges] = useState(false);
  const [flangeCount, setFlangeCount] = useState(4);

  if (!modelId) {
    return (
      <div className="text-center text-text-muted text-xs py-8">
        请先导入模型
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Section title="1. 脱模方向分析">
        <ActionButton
          icon={<Compass size={13} />}
          label={isAnalyzing ? "分析中..." : "分析最优方向"}
          loading={isAnalyzing}
          onClick={() => orientation.mutate({ modelId }, {
            onSuccess: (r) => toastSuccess("方向分析完成", `评分 ${(r.best_score.total_score * 100).toFixed(0)}%`),
            onError: (e) => toastError("方向分析失败", (e as Error).message),
          })}
        />
        {orientationResult && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1"
          >
            <div className="flex justify-between">
              <span className="text-text-muted">最佳方向</span>
              <span className="text-text-primary font-mono">
                [{orientationResult.best_direction.map((v) => v.toFixed(2)).join(", ")}]
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">综合评分</span>
              <span className="text-accent font-semibold">
                {(orientationResult.best_score.total_score * 100).toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">可见率</span>
              <span>{(orientationResult.best_score.visibility_ratio * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">倒扣率</span>
              <span className={orientationResult.best_score.undercut_ratio > 0.1 ? "text-danger" : ""}>
                {(orientationResult.best_score.undercut_ratio * 100).toFixed(1)}%
              </span>
            </div>
            <div className="text-text-muted mt-1">
              候选方向: {orientationResult.top_candidates.length} 个
            </div>
          </motion.div>
        )}
      </Section>

      <Section title="2. 分型面生成">
        <ActionButton
          icon={<SplitSquareVertical size={13} />}
          label={isGeneratingParting ? "生成中..." : "生成分型面"}
          loading={isGeneratingParting}
          onClick={() => parting.mutate({ modelId }, {
            onSuccess: () => toastSuccess("分型面已生成"),
            onError: (e) => toastError("分型面生成失败", (e as Error).message),
          })}
        />
        {partingResult && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1"
          >
            <div className="flex justify-between">
              <span className="text-text-muted">分型线数</span>
              <span>{partingResult.parting_lines.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">上模面数</span>
              <span>{partingResult.n_upper_faces}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">下模面数</span>
              <span>{partingResult.n_lower_faces}</span>
            </div>
          </motion.div>
        )}
      </Section>

      <Section title="3. 模具壳体生成">
        <div className="space-y-2 mb-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">壁厚</span>
            <div className="flex items-center gap-1">
              <input
                type="range"
                min={2}
                max={8}
                step={0.5}
                value={wallThickness}
                onChange={(e) => setWallThickness(parseFloat(e.target.value))}
                className="w-20 accent-accent"
              />
              <span className="text-[10px] text-text-muted w-10 text-right">{wallThickness}mm</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">壳类型</span>
            <select
              value={shellType}
              onChange={(e) => setShellType(e.target.value)}
              className="text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary"
            >
              <option value="box">方形壳体</option>
              <option value="conformal">随形壳体</option>
            </select>
          </div>

          {/* Parting style */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">分型面样式</span>
            <select
              value={partingStyle}
              onChange={(e) => setPartingStyle(e.target.value)}
              className="text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary"
            >
              <option value="flat">平面</option>
              <option value="dovetail">燕尾榫</option>
              <option value="zigzag">锯齿形</option>
              <option value="step">阶梯形</option>
              <option value="tongue_groove">榫槽</option>
            </select>
          </div>

          {/* Flanges */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">螺丝固定法兰</span>
            <button
              onClick={() => setAddFlanges(!addFlanges)}
              className={cn(
                "px-2 py-0.5 rounded text-[10px] transition-colors",
                addFlanges ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover",
              )}
            >
              {addFlanges ? "已启用" : "关闭"}
            </button>
          </div>
          {addFlanges && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-text-muted">法兰数量</span>
              <div className="flex items-center gap-1">
                {[2, 4, 6, 8].map((n) => (
                  <button key={n} onClick={() => setFlangeCount(n)}
                    className={cn(
                      "px-1.5 py-0.5 rounded text-[9px] transition-colors",
                      flangeCount === n ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover",
                    )}>
                    {n}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <ActionButton
          icon={<Box size={13} />}
          label={isGeneratingMold ? "生成中..." : "生成模具"}
          loading={isGeneratingMold}
          onClick={() =>
            moldGen.mutate({
              modelId,
              wallThickness,
              shellType,
              partingStyle,
              addFlanges,
              nFlanges: flangeCount,
              direction: orientationResult?.best_direction,
            }, {
              onSuccess: ({ result }) => toastSuccess("模具已生成", `${result.n_shells} 片壳体`),
              onError: (e) => toastError("模具生成失败", (e as Error).message),
            })
          }
        />
        {moldResult && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mt-2 space-y-2"
          >
            <div className="p-2 rounded bg-bg-secondary text-[10px] space-y-1">
              <div className="flex justify-between">
                <span className="text-text-muted">壳体数量</span>
                <span className="text-accent font-semibold">{moldResult.n_shells}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">型腔体积</span>
                <span>{moldResult.cavity_volume.toFixed(1)} mm³</span>
              </div>
            </div>

            {/* Shells detail */}
            <div className="p-2 rounded bg-bg-secondary text-[10px] space-y-1">
              <div className="text-text-muted font-semibold mb-1">壳体详情</div>
              {moldResult.shells.map((sh) => (
                <div key={sh.shell_id} className="flex justify-between items-center border-t border-border/30 pt-1 mt-1">
                  <span className="text-text-muted">壳 #{sh.shell_id}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-text-secondary">{sh.face_count.toLocaleString()} 面</span>
                    <span className={cn(
                      "px-1 py-0.5 rounded text-[8px] font-medium",
                      sh.is_printable ? "bg-success/10 text-success" : "bg-warning/10 text-warning",
                    )}>
                      {sh.is_printable ? "可打印" : `拔模角 ${sh.min_draft_angle?.toFixed(1) ?? "0"}°`}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Pour hole v3 */}
            {moldResult.pour_hole && (
              <div className="p-2 rounded bg-bg-secondary text-[10px] space-y-1">
                <div className="text-text-muted font-semibold mb-1">浇筑口 (v3 智能放置)</div>
                {typeof moldResult.pour_hole === "object" && !Array.isArray(moldResult.pour_hole) ? (
                  <>
                    <div className="flex justify-between">
                      <span className="text-text-muted">评分</span>
                      <span className="text-accent font-bold">{((moldResult.pour_hole as { score?: number }).score ?? 0 * 100).toFixed(1)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-muted">直径</span>
                      <span>{(moldResult.pour_hole as { diameter?: number }).diameter?.toFixed(1) ?? "15"} mm</span>
                    </div>
                    <div className="text-[9px] text-text-muted mt-1 leading-relaxed">
                      基于高度(40%) + 中心性(25%) + 可及性(20%) + 厚度(15%) 综合优化
                    </div>
                  </>
                ) : (
                  <div className="text-text-secondary">位置已确定</div>
                )}
              </div>
            )}

            {/* Vent holes v3 */}
            {moldResult.vent_holes.length > 0 && (
              <div className="p-2 rounded bg-bg-secondary text-[10px] space-y-1">
                <div className="text-text-muted font-semibold mb-1">排气口 ({moldResult.vent_holes.length} 个, BFS仿真)</div>
                {moldResult.vent_holes.map((v, i) => {
                  const isObj = typeof v === "object" && !Array.isArray(v);
                  return (
                    <div key={i} className="flex justify-between border-t border-border/30 pt-0.5 mt-0.5">
                      <span className="text-text-muted">排气 #{i + 1}</span>
                      {isObj ? (
                        <span className="text-accent">{(((v as { score?: number }).score ?? 0) * 100).toFixed(1)}%</span>
                      ) : (
                        <span className="text-text-secondary">已放置</span>
                      )}
                    </div>
                  );
                })}
                <div className="text-[9px] text-text-muted mt-1 leading-relaxed">
                  基于重力流前BFS模拟 + 气穴检测 + 最远点采样
                </div>
              </div>
            )}

            {/* Alignment */}
            {moldResult.alignment_features && moldResult.alignment_features.length > 0 && (
              <div className="p-2 rounded bg-bg-secondary text-[10px] space-y-1">
                <div className="text-text-muted font-semibold mb-1">对齐特征</div>
                <div className="flex justify-between">
                  <span className="text-text-muted">定位销</span>
                  <span>{moldResult.alignment_features.filter(f => f.type === "pin").length} 个</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">配合孔</span>
                  <span>{moldResult.alignment_features.filter(f => f.type === "hole").length} 个</span>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </Section>
    </div>
  );
}

function InsertPanel() {
  const modelId = useModelStore((s) => s.modelId);
  const moldId = useMoldStore((s) => s.moldId);
  const { positions, insertId, plates, assemblyValid, validationMessages, isAnalyzing, isGenerating } = useInsertStore();
  const analyzePos = useAnalyzePositions();
  const generate = useGenerateInserts();
  const validate = useValidateAssembly();
  const [organType, setOrganType] = useState("general");
  const [insertType, setInsertType] = useState("flat");
  const [anchorType, setAnchorType] = useState("mesh_holes");
  const [nPlates, setNPlates] = useState(1);
  const [thickness, setThickness] = useState(2.0);

  if (!modelId) {
    return (
      <div className="text-center text-text-muted text-xs py-8">
        请先导入模型
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Section title="器官类型">
        <select
          value={organType}
          onChange={(e) => setOrganType(e.target.value)}
          className="w-full text-xs bg-bg-secondary border border-border rounded px-2 py-1.5 text-text-primary"
        >
          <option value="general">通用</option>
          <option value="solid">实质性器官 (肝/肾/脑)</option>
          <option value="hollow">空腔器官 (胃/膀胱)</option>
          <option value="tubular">管道结构 (血管/肠道)</option>
          <option value="sheet">组织片 (皮肤/肌肉)</option>
        </select>
      </Section>

      <Section title="1. 位置分析">
        <ActionButton
          icon={<Compass size={13} />}
          label={isAnalyzing ? "分析中..." : "分析最佳位置"}
          loading={isAnalyzing}
          onClick={() => analyzePos.mutate({ model_id: modelId, organ_type: organType }, {
            onSuccess: () => toastSuccess("位置分析完成"),
            onError: (e) => toastError("位置分析失败", (e as Error).message),
          })}
        />
        {positions.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1">
            {positions.slice(0, 3).map((p, i) => (
              <div key={i} className="flex justify-between">
                <span className="text-text-muted">{p.reason}</span>
                <span className="text-accent">{(p.score * 100).toFixed(0)}%</span>
              </div>
            ))}
          </motion.div>
        )}
      </Section>

      <Section title="2. 支撑板参数">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">板型</span>
            <select value={insertType} onChange={(e) => setInsertType(e.target.value)}
              className="text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary">
              <option value="flat">平板</option>
              <option value="conformal">仿形板</option>
              <option value="ribbed">加强筋板</option>
              <option value="lattice">格栅结构</option>
            </select>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">板厚</span>
            <div className="flex items-center gap-1">
              <input type="range" min={1} max={5} step={0.5} value={thickness}
                onChange={(e) => setThickness(parseFloat(e.target.value))} className="w-20 accent-accent" />
              <span className="text-[10px] text-text-muted w-10 text-right">{thickness}mm</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">数量</span>
            <input type="number" min={1} max={4} value={nPlates}
              onChange={(e) => setNPlates(parseInt(e.target.value) || 1)}
              className="w-14 text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary text-right" />
          </div>
          {insertType === "conformal" && (
            <div className="p-1.5 rounded bg-bg-secondary/50 space-y-1.5">
              <div className="text-[9px] text-accent font-medium">仿形参数</div>
              <div className="flex items-center justify-between">
                <span className="text-[9px] text-text-muted">偏移距离</span>
                <span className="text-[9px] text-text-muted">3.0mm</span>
              </div>
            </div>
          )}
          {insertType === "ribbed" && (
            <div className="p-1.5 rounded bg-bg-secondary/50 space-y-1.5">
              <div className="text-[9px] text-accent font-medium">加强筋参数</div>
              <div className="flex items-center justify-between">
                <span className="text-[9px] text-text-muted">筋高/间距</span>
                <span className="text-[9px] text-text-muted">3.0mm / 8.0mm</span>
              </div>
            </div>
          )}
          {insertType === "lattice" && (
            <div className="p-1.5 rounded bg-bg-secondary/50 space-y-1.5">
              <div className="text-[9px] text-accent font-medium">格栅参数</div>
              <div className="flex items-center justify-between">
                <span className="text-[9px] text-text-muted">胞元尺寸</span>
                <span className="text-[9px] text-text-muted">5.0mm</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[9px] text-text-muted">杆径</span>
                <span className="text-[9px] text-text-muted">1.2mm</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[9px] text-text-muted">拓扑</span>
                <span className="text-[9px] text-text-muted">BCC 体心立方</span>
              </div>
            </div>
          )}
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">锚固类型</span>
            <select value={anchorType} onChange={(e) => setAnchorType(e.target.value)}
              className="text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary">
              <option value="mesh_holes">网孔</option>
              <option value="bumps">凸起</option>
              <option value="grooves">沟槽</option>
              <option value="dovetail">燕尾</option>
              <option value="diamond">菱形纹</option>
            </select>
          </div>
        </div>
      </Section>

      <Section title="3. 生成支撑板">
        <ActionButton
          icon={<Pin size={13} />}
          label={isGenerating ? "生成中..." : "生成支撑板"}
          loading={isGenerating}
          onClick={() => generate.mutate({
            model_id: modelId, organ_type: organType, anchor_type: anchorType,
            insert_type: insertType,
            n_plates: nPlates, thickness, mold_id: moldId ?? undefined,
          }, {
            onSuccess: () => toastSuccess("支撑板已生成", `${nPlates} 块 ${
              insertType === "flat" ? "平板" : insertType === "conformal" ? "仿形板" :
              insertType === "ribbed" ? "加强筋板" : "格栅板"
            }`),
            onError: (e) => toastError("支撑板生成失败", (e as Error).message),
          })}
        />
        {plates.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1">
            {plates.map((p, i) => (
              <div key={i} className="border-b border-border/50 pb-1 mb-1 last:border-0">
                <div className="flex justify-between">
                  <span className="text-text-muted">板 #{i + 1}</span>
                  <span className="text-accent">{
                    p.insert_type === "conformal" ? "仿形" :
                    p.insert_type === "ribbed" ? "加强筋" :
                    p.insert_type === "lattice" ? "格栅" : "平板"
                  }</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">面数</span>
                  <span>{p.face_count.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">锚固</span>
                  <span>{p.anchor ? `${p.anchor.type} ×${p.anchor.count}` : "无"}</span>
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </Section>

      <Section title="4. 装配验证">
        <ActionButton
          icon={<CheckCircle2 size={13} />}
          label="验证装配"
          loading={validate.isPending}
          onClick={() => insertId && validate.mutate({ model_id: modelId, insert_id: insertId, mold_id: moldId ?? undefined }, {
            onSuccess: () => toastInfo("装配验证完成"),
            onError: (e) => toastError("验证失败", (e as Error).message),
          })}
        />
        {validationMessages.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1">
            <div className="flex items-center gap-1 mb-1">
              <span className={assemblyValid ? "text-green-400" : "text-warning"}>
                {assemblyValid ? "✓ 验证通过" : "⚠ 存在问题"}
              </span>
            </div>
            {validationMessages.map((m, i) => (
              <div key={i} className="text-text-muted">{m}</div>
            ))}
          </motion.div>
        )}
      </Section>
    </div>
  );
}

function GatingPanel() {
  const modelId = useModelStore((s) => s.modelId);
  const moldId = useMoldStore((s) => s.moldId);
  const { gatingId, gatingResult, isDesigningGating, selectedMaterial, setMaterial } = useSimStore();
  const gatingDesign = useGatingDesign();
  const [gateDiam, setGateDiam] = useState(6.0);
  const [runnerWidth, setRunnerWidth] = useState(4.0);
  const [nVents, setNVents] = useState(3);

  if (!modelId || !moldId) {
    return (
      <div className="text-center text-text-muted text-xs py-8">
        请先生成模具（步骤: 模具）
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Section title="材料">
        <select value={selectedMaterial} onChange={(e) => setMaterial(e.target.value)}
          className="w-full text-xs bg-bg-secondary border border-border rounded px-2 py-1.5 text-text-primary">
          <option value="silicone_a10">硅胶 Shore A10 (软)</option>
          <option value="silicone_a30">硅胶 Shore A30 (中)</option>
          <option value="silicone_a50">硅胶 Shore A50 (硬)</option>
          <option value="polyurethane">聚氨酯</option>
          <option value="epoxy_resin">环氧树脂</option>
          <option value="abs_injection">ABS 注塑</option>
          <option value="pp_injection">PP 注塑</option>
        </select>
      </Section>

      <Section title="浇口参数">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">浇口直径</span>
            <div className="flex items-center gap-1">
              <input type="range" min={2} max={12} step={0.5} value={gateDiam}
                onChange={(e) => setGateDiam(parseFloat(e.target.value))} className="w-20 accent-accent" />
              <span className="text-[10px] text-text-muted w-12 text-right">{gateDiam}mm</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">浇道宽度</span>
            <div className="flex items-center gap-1">
              <input type="range" min={2} max={10} step={0.5} value={runnerWidth}
                onChange={(e) => setRunnerWidth(parseFloat(e.target.value))} className="w-20 accent-accent" />
              <span className="text-[10px] text-text-muted w-12 text-right">{runnerWidth}mm</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">排气孔数</span>
            <input type="number" min={1} max={8} value={nVents}
              onChange={(e) => setNVents(parseInt(e.target.value) || 3)}
              className="w-14 text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary text-right" />
          </div>
        </div>
      </Section>

      <Section title="设计">
        <ActionButton
          icon={<Droplets size={13} />}
          label={isDesigningGating ? "设计中..." : "自动设计浇注系统"}
          loading={isDesigningGating}
          onClick={() => gatingDesign.mutate({
            modelId, moldId,
            gateDiameter: gateDiam,
            nVents,
          }, {
            onSuccess: () => toastSuccess("浇注系统设计完成"),
            onError: (e) => toastError("设计失败", (e as Error).message),
          })}
        />
      </Section>

      {gatingResult && (
        <Section title="设计结果">
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            className="p-2 rounded bg-bg-secondary text-[10px] space-y-1.5">
            <div className="flex justify-between">
              <span className="text-text-muted">浇口评分</span>
              <span className="text-accent font-bold">{(gatingResult.gate.score * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">流道平衡</span>
              <span>{(gatingResult.gate.flow_balance * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">可达性</span>
              <span>{(gatingResult.gate.accessibility * 100).toFixed(1)}%</span>
            </div>
            <div className="h-px bg-border" />
            <div className="flex justify-between">
              <span className="text-text-muted">浇口直径</span>
              <span>{gatingResult.gate_diameter.toFixed(1)}mm</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">浇道宽度</span>
              <span>{gatingResult.runner_width.toFixed(1)}mm</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">排气孔</span>
              <span>{gatingResult.vents.length} 个</span>
            </div>
            <div className="h-px bg-border" />
            <div className="flex justify-between">
              <span className="text-text-muted">型腔体积</span>
              <span>{gatingResult.cavity_volume.toFixed(0)} mm³</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">预计材料量</span>
              <span>{gatingResult.estimated_material_volume.toFixed(0)} mm³</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">预计充填时间</span>
              <span>{gatingResult.estimated_fill_time.toFixed(1)} s</span>
            </div>
          </motion.div>
        </Section>
      )}

      {gatingId && (
        <div className="p-2 rounded border border-accent/20 bg-accent/5 text-[10px] text-text-secondary">
          <p className="font-medium text-accent mb-1">下一步</p>
          <p>浇注系统已就绪。前往"仿真"步骤运行灌注仿真和自动优化。</p>
        </div>
      )}
    </div>
  );
}

function SimPanel() {
  const modelId = useModelStore((s) => s.modelId);
  const moldId = useMoldStore((s) => s.moldId);
  const {
    selectedMaterial, gatingId, gatingResult, simId, simResult,
    optimizationResult, isDesigningGating, isSimulating, isOptimizing,
    setMaterial, visualizationData, isLoadingVisualization,
    heatmapField, heatmapVisible, heatmapOpacity, pointSize,
    streamlinesVisible, streamlineCount, particleDensity,
    animationPlaying, animationProgress, animationSpeed, animationLoop,
    crossSectionAxis, crossSectionPosition,
    crossSectionData, analysisExpanded,
    setHeatmapField, setHeatmapVisible, setHeatmapOpacity, setPointSize,
    setStreamlinesVisible, setStreamlineCount, setParticleDensity,
    setAnimationPlaying, setAnimationProgress, setAnimationSpeed, setAnimationLoop,
    setCrossSectionAxis, setCrossSectionPosition,
    setAnalysisExpanded,
    surfaceMapData, surfaceMapVisible, surfaceMapLoading,
    setSurfaceMapVisible,
    feaId, feaResult, feaVisualizationData, feaRunning, feaField, feaVisible,
    setFEAField, setFEAVisible,
  } = useSimStore();
  const gatingDesign = useGatingDesign();
  const runSim = useRunSimulation();
  const runOpt = useRunOptimization();
  const fetchVis = useFetchVisualization();
  const fetchCrossSection = useFetchCrossSection();
  const fetchSurfaceMap = useFetchSurfaceMap();
  const runFEA = useRunFEA();
  const fetchFEAVis = useFetchFEAVisualization();
  const [simLevel, setSimLevel] = useState(2);
  const [feaMaterial, setFeaMaterial] = useState("pla");

  if (!modelId || !moldId) {
    return (
      <div className="text-center text-text-muted text-xs py-8">
        请先生成模具（步骤: 模具）
      </div>
    );
  }

  const FIELD_OPTIONS: { value: HeatmapField; label: string; icon: React.ReactNode }[] = [
    { value: "fill_time", label: "充填时间", icon: <Timer size={11} /> },
    { value: "pressure", label: "压力场", icon: <Gauge size={11} /> },
    { value: "velocity", label: "流速场", icon: <Activity size={11} /> },
    { value: "shear_rate", label: "剪切率", icon: <Zap size={11} /> },
    { value: "temperature", label: "温度场", icon: <ThermometerSun size={11} /> },
    { value: "cure_progress", label: "固化进度", icon: <Layers size={11} /> },
    { value: "thickness", label: "壁厚分布", icon: <Slice size={11} /> },
  ];

  return (
    <div className="space-y-4">
      {/* 1. Material */}
      <Section title="1. 材料选择">
        <select
          value={selectedMaterial}
          onChange={(e) => setMaterial(e.target.value)}
          className="w-full text-xs bg-bg-secondary border border-border rounded px-2 py-1.5 text-text-primary"
        >
          <option value="silicone_a10">硅胶 Shore A10 (软)</option>
          <option value="silicone_a30">硅胶 Shore A30 (中)</option>
          <option value="silicone_a50">硅胶 Shore A50 (硬)</option>
          <option value="polyurethane">聚氨酯</option>
          <option value="epoxy_resin">环氧树脂</option>
          <option value="abs_injection">ABS 注塑</option>
          <option value="pp_injection">PP 注塑</option>
        </select>
      </Section>

      {/* 2. Gating */}
      <Section title="2. 浇注系统">
        <ActionButton
          icon={<Droplets size={13} />}
          label={isDesigningGating ? "设计中..." : "设计浇注系统"}
          loading={isDesigningGating}
          onClick={() => gatingDesign.mutate({ modelId, moldId }, {
            onSuccess: () => toastSuccess("浇注系统设计完成"),
            onError: (e) => toastError("浇注系统设计失败", (e as Error).message),
          })}
        />
        {gatingResult && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1">
            <div className="flex justify-between">
              <span className="text-text-muted">浇口评分</span>
              <span className="text-accent">{(gatingResult.gate.score * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">排气孔</span>
              <span>{gatingResult.vents.length} 个</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">型腔体积</span>
              <span>{gatingResult.cavity_volume.toFixed(0)} mm³</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">预计充填</span>
              <span>{gatingResult.estimated_fill_time.toFixed(1)} s</span>
            </div>
          </motion.div>
        )}
      </Section>

      {/* 3. Simulation */}
      <Section title="3. 灌注仿真">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] text-text-muted">仿真级别</span>
          <div className="flex items-center gap-1">
            {[
              { v: 1, label: "L1 启发式", tip: "快速 ~1s" },
              { v: 2, label: "L2 达西流", tip: "精确 ~5s, 含可视化" },
            ].map((opt) => (
              <button key={opt.v} onClick={() => setSimLevel(opt.v)}
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] transition-colors",
                  simLevel === opt.v
                    ? "bg-accent text-white"
                    : "bg-bg-secondary text-text-muted hover:bg-bg-hover",
                )} title={opt.tip}>
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <ActionButton
          icon={<Zap size={13} />}
          label={isSimulating ? "仿真中..." : `运行仿真 (L${simLevel})`}
          loading={isSimulating}
          onClick={() => gatingId && runSim.mutate({ modelId, gatingId, level: simLevel }, {
            onSuccess: ({ simId: newSimId, result: r }) => {
              toastSuccess("仿真完成", `充填率 ${(r.fill_fraction * 100).toFixed(1)}%`);
              if (r.has_visualization && newSimId) {
                fetchVis.mutate(newSimId);
              }
            },
            onError: (e) => toastError("仿真失败", (e as Error).message),
          })}
        />
        {simResult && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1">
            <div className="flex justify-between">
              <span className="text-text-muted">充填率</span>
              <span className={simResult.fill_fraction < 0.99 ? "text-warning" : "text-success"}>
                {(simResult.fill_fraction * 100).toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">充填时间</span>
              <span>{simResult.fill_time_seconds.toFixed(1)} s</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">最大压力</span>
              <span>{simResult.max_pressure.toFixed(0)} Pa</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">缺陷数</span>
              <span className={simResult.defects.length > 0 ? "text-warning" : "text-success"}>
                {simResult.defects.length}
              </span>
            </div>
            {simResult.defects.map((d, i) => (
              <div key={i} className="text-warning/80 border-t border-border/50 pt-1">
                <span className="font-medium">{d.type}</span>: {d.description}
                <span className="ml-1 text-text-muted">(严重度 {(d.severity * 100).toFixed(0)}%)</span>
              </div>
            ))}
          </motion.div>
        )}
      </Section>

      {/* 4. Heatmap Visualization */}
      {simResult && (
        <Section title="4. 热力图可视化">
          {!visualizationData && !isLoadingVisualization && simResult.has_visualization && simId && (
            <ActionButton
              icon={<BarChart3 size={13} />}
              label="加载可视化数据"
              loading={false}
              onClick={() => fetchVis.mutate(simId)}
            />
          )}
          {isLoadingVisualization && (
            <div className="flex items-center gap-2 text-[10px] text-text-muted py-2">
              <Loader2 size={12} className="animate-spin" />
              加载可视化数据中...
            </div>
          )}
          {visualizationData && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2.5">
              {/* Visibility toggle */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-text-muted">热力图</span>
                <button onClick={() => setHeatmapVisible(!heatmapVisible)}
                  className={cn("p-1 rounded transition-colors", heatmapVisible ? "bg-accent/20 text-accent" : "bg-bg-secondary text-text-muted")}>
                  {heatmapVisible ? <Eye size={12} /> : <EyeOff size={12} />}
                </button>
              </div>

              {/* Field selector */}
              <div className="space-y-1">
                <span className="text-[10px] text-text-muted">显示场</span>
                <div className="grid grid-cols-2 gap-1">
                  {FIELD_OPTIONS.map((opt) => (
                    <button key={opt.value} onClick={() => setHeatmapField(opt.value)}
                      className={cn(
                        "flex items-center gap-1 px-1.5 py-1 rounded text-[9px] transition-colors",
                        heatmapField === opt.value
                          ? "bg-accent/20 text-accent ring-1 ring-accent/30"
                          : "bg-bg-secondary text-text-muted hover:bg-bg-hover",
                      )}>
                      {opt.icon}
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Opacity */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-text-muted">透明度</span>
                <div className="flex items-center gap-1">
                  <input type="range" min={0.1} max={1} step={0.05} value={heatmapOpacity}
                    onChange={(e) => setHeatmapOpacity(parseFloat(e.target.value))}
                    className="w-16 accent-accent" />
                  <span className="text-[10px] text-text-muted w-8 text-right">{Math.round(heatmapOpacity * 100)}%</span>
                </div>
              </div>

              {/* Point size */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-text-muted">点大小</span>
                <div className="flex items-center gap-1">
                  <input type="range" min={1} max={8} step={0.5} value={pointSize}
                    onChange={(e) => setPointSize(parseFloat(e.target.value))}
                    className="w-16 accent-accent" />
                  <span className="text-[10px] text-text-muted w-6 text-right">{pointSize}</span>
                </div>
              </div>

              {/* Particle density */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-text-muted">粒子密度</span>
                <div className="flex items-center gap-1">
                  {[1, 2, 3].map((d) => (
                    <button key={d} onClick={() => setParticleDensity(d)}
                      className={cn(
                        "px-1.5 py-0.5 rounded text-[9px] transition-colors",
                        particleDensity === d ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover",
                      )}>
                      {d}×
                    </button>
                  ))}
                </div>
              </div>

              {/* Streamlines */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-text-muted">流线显示</span>
                <div className="flex items-center gap-1.5">
                  <button onClick={() => setStreamlinesVisible(!streamlinesVisible)}
                    className={cn("p-1 rounded transition-colors", streamlinesVisible ? "bg-accent/20 text-accent" : "bg-bg-secondary text-text-muted")}>
                    {streamlinesVisible ? <Eye size={12} /> : <EyeOff size={12} />}
                  </button>
                </div>
              </div>
              {streamlinesVisible && (
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-text-muted">流线数量</span>
                  <div className="flex items-center gap-1">
                    <input type="range" min={10} max={80} step={5} value={streamlineCount}
                      onChange={(e) => setStreamlineCount(parseInt(e.target.value))}
                      className="w-16 accent-accent" />
                    <span className="text-[10px] text-text-muted w-6 text-right">{streamlineCount}</span>
                  </div>
                </div>
              )}

              {/* Stats */}
              <div className="text-[9px] text-text-muted">
                {(visualizationData.n_points * particleDensity).toLocaleString()} 粒子 ({visualizationData.n_points.toLocaleString()} 体素) | 缺陷标记 {visualizationData.defect_positions.length}
              </div>
            </motion.div>
          )}
          {!simResult.has_visualization && (
            <div className="text-[10px] text-text-muted p-2 bg-bg-secondary rounded">
              L1 启发式仿真不产生体素数据。请使用 L2 达西流获取完整可视化。
            </div>
          )}
        </Section>
      )}

      {/* 5. Fill Animation Player */}
      {visualizationData && (
        <Section title="5. 充填动画">
          <div className="space-y-2">
            {/* Playback controls */}
            <div className="flex items-center gap-1.5">
              <button onClick={() => { setAnimationProgress(0); setAnimationPlaying(true); }}
                className="p-1 rounded bg-bg-secondary hover:bg-bg-hover text-text-muted" title="从头播放">
                <Rewind size={12} />
              </button>
              <button onClick={() => setAnimationPlaying(!animationPlaying)}
                className={cn("p-1.5 rounded transition-colors", animationPlaying ? "bg-accent text-white" : "bg-bg-secondary hover:bg-bg-hover text-text-muted")}
                title={animationPlaying ? "暂停" : "播放"}>
                {animationPlaying ? <Pause size={12} /> : <Play size={12} />}
              </button>
              <div className="flex-1">
                <input type="range" min={0} max={1} step={0.01} value={animationProgress}
                  onChange={(e) => { setAnimationProgress(parseFloat(e.target.value)); setAnimationPlaying(false); }}
                  className="w-full accent-accent" />
              </div>
              <span className="text-[10px] text-text-muted w-10 text-right tabular-nums">
                {(animationProgress * 100).toFixed(0)}%
              </span>
            </div>

            {/* Speed & loop */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-text-muted">速度</span>
                {[0.5, 1, 2, 4].map((s) => (
                  <button key={s} onClick={() => setAnimationSpeed(s)}
                    className={cn(
                      "px-1.5 py-0.5 rounded text-[9px] transition-colors",
                      animationSpeed === s ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover",
                    )}>
                    {s}×
                  </button>
                ))}
              </div>
              <button onClick={() => setAnimationLoop(!animationLoop)}
                className={cn(
                  "px-1.5 py-0.5 rounded text-[9px] transition-colors",
                  animationLoop ? "bg-accent/20 text-accent" : "bg-bg-secondary text-text-muted",
                )}>
                循环
              </button>
            </div>

            {/* Time info */}
            {simResult && (
              <div className="text-[9px] text-text-muted">
                当前时刻: {(animationProgress * simResult.fill_time_seconds).toFixed(2)}s
                / {simResult.fill_time_seconds.toFixed(2)}s
              </div>
            )}
          </div>
        </Section>
      )}

      {/* 6. Cross-Section */}
      {visualizationData && simId && (
        <Section title="6. 截面分析">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-text-muted">截面轴</span>
              <div className="flex items-center gap-1">
                {(["x", "y", "z"] as const).map((ax) => (
                  <button key={ax} onClick={() => setCrossSectionAxis(ax)}
                    className={cn(
                      "px-2 py-0.5 rounded text-[10px] transition-colors",
                      crossSectionAxis === ax ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover",
                    )}>
                    {ax.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-text-muted">位置</span>
              <div className="flex items-center gap-1">
                <input type="range" min={0} max={1} step={0.02} value={crossSectionPosition}
                  onChange={(e) => setCrossSectionPosition(parseFloat(e.target.value))}
                  className="w-20 accent-accent" />
                <span className="text-[10px] text-text-muted w-8 text-right">{(crossSectionPosition * 100).toFixed(0)}%</span>
              </div>
            </div>
            <ActionButton
              icon={<Slice size={13} />}
              label="生成截面热力图"
              loading={fetchCrossSection.isPending}
              onClick={() => fetchCrossSection.mutate({
                simId, axis: crossSectionAxis, position: crossSectionPosition, field: heatmapField,
              })}
            />
            {crossSectionData && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-2">
                <CrossSectionCanvas data={crossSectionData} />
                <div className="text-[9px] text-text-muted mt-1">
                  {crossSectionData.field} | {crossSectionData.axis.toUpperCase()}轴
                  | 值域 [{crossSectionData.value_range[0].toFixed(2)}, {crossSectionData.value_range[1].toFixed(2)}]
                </div>
              </motion.div>
            )}
          </div>
        </Section>
      )}

      {/* 7. Analysis Report */}
      {simResult?.analysis && (
        <Section title="7. 综合分析报告">
          <button onClick={() => setAnalysisExpanded(!analysisExpanded)}
            className="w-full flex items-center justify-between p-2 rounded bg-bg-secondary text-[10px] text-text-secondary hover:bg-bg-hover transition-colors">
            <div className="flex items-center gap-1.5">
              <BarChart3 size={12} className="text-accent" />
              <span>质量评分: <span className="text-accent font-bold">{(simResult.analysis.fill_quality_score * 100).toFixed(1)}%</span></span>
            </div>
            {analysisExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>

          <AnimatePresence>
            {analysisExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="p-2 rounded bg-bg-secondary text-[10px] space-y-1.5 mt-1">
                  <div className="text-text-muted font-semibold">均匀性指标</div>
                  <AnalysisBar label="充填均匀" value={simResult.analysis.fill_uniformity_index} />
                  <AnalysisBar label="压力均匀" value={simResult.analysis.pressure_uniformity_index} />
                  <AnalysisBar label="速度均匀" value={simResult.analysis.velocity_uniformity_index} />
                  <AnalysisBar label="充填平衡" value={simResult.analysis.fill_balance_score} />

                  <div className="text-text-muted font-semibold mt-2">剪切 & 温度</div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">最大剪切率</span>
                    <span>{simResult.analysis.max_shear_rate.toFixed(1)} 1/s</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">平均剪切率</span>
                    <span>{simResult.analysis.avg_shear_rate.toFixed(1)} 1/s</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">温度范围</span>
                    <span>{simResult.analysis.temperature_range[0].toFixed(1)}~{simResult.analysis.temperature_range[1].toFixed(1)} °C</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">平均固化进度</span>
                    <span>{(simResult.analysis.avg_cure_progress * 100).toFixed(1)}%</span>
                  </div>

                  <div className="text-text-muted font-semibold mt-2">壁厚分析</div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">壁厚范围</span>
                    <span>{simResult.analysis.min_thickness.toFixed(1)}~{simResult.analysis.max_thickness.toFixed(1)} mm</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">薄壁占比</span>
                    <span className={simResult.analysis.thin_wall_fraction > 0.1 ? "text-warning" : ""}>
                      {(simResult.analysis.thin_wall_fraction * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">厚壁占比</span>
                    <span className={simResult.analysis.thick_wall_fraction > 0.1 ? "text-warning" : ""}>
                      {(simResult.analysis.thick_wall_fraction * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div className="text-text-muted font-semibold mt-2">其他指标</div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">流长比</span>
                    <span>{simResult.analysis.flow_length_ratio.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">浇口效率</span>
                    <span>{(simResult.analysis.gate_efficiency * 100).toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">滞流区</span>
                    <span className={simResult.analysis.n_stagnation_zones > 3 ? "text-warning" : ""}>
                      {simResult.analysis.n_stagnation_zones}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">高剪切区</span>
                    <span className={simResult.analysis.n_high_shear_zones > 2 ? "text-warning" : ""}>
                      {simResult.analysis.n_high_shear_zones}
                    </span>
                  </div>
                </div>

                {/* Recommendations */}
                {simResult.analysis.recommendations.length > 0 && (
                  <div className="p-2 rounded border border-accent/20 bg-accent/5 text-[10px] text-text-secondary mt-1.5 space-y-1">
                    <div className="flex items-center gap-1 font-medium text-accent">
                      <Lightbulb size={11} />
                      优化建议
                    </div>
                    {simResult.analysis.recommendations.map((rec, i) => (
                      <div key={i} className="pl-3 text-text-muted leading-relaxed">• {rec}</div>
                    ))}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </Section>
      )}

      {/* 8. Auto Optimization */}
      <Section title={simResult?.analysis ? "8. 自动优化" : "4. 自动优化"}>
        <ActionButton
          icon={<RefreshCw size={13} />}
          label={isOptimizing ? "优化中..." : "自动优化"}
          loading={isOptimizing}
          onClick={() => gatingId && runOpt.mutate({ modelId, moldId, gatingId }, {
            onSuccess: () => toastSuccess("优化完成"),
            onError: (e) => toastError("优化失败", (e as Error).message),
          })}
        />
        {optimizationResult && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1">
            <div className="flex justify-between">
              <span className="text-text-muted">收敛</span>
              <span className={optimizationResult.converged ? "text-success" : "text-warning"}>
                {optimizationResult.converged ? "是" : "否"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">迭代次数</span>
              <span>{optimizationResult.iterations}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">充填率</span>
              <span>
                {(optimizationResult.initial_fill_fraction * 100).toFixed(1)}%
                {" → "}
                <span className="text-accent">{(optimizationResult.final_fill_fraction * 100).toFixed(1)}%</span>
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">缺陷数</span>
              <span>
                {optimizationResult.initial_defects} → <span className="text-accent">{optimizationResult.final_defects}</span>
              </span>
            </div>
          </motion.div>
        )}
      </Section>

      {/* 9. Surface Overlay */}
      {visualizationData && simId && (
        <Section title="9. 表面叠加显示">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-text-muted">模型表面映射</span>
              <button onClick={() => setSurfaceMapVisible(!surfaceMapVisible)}
                className={cn("p-1 rounded transition-colors", surfaceMapVisible ? "bg-accent/20 text-accent" : "bg-bg-secondary text-text-muted")}>
                {surfaceMapVisible ? <Eye size={12} /> : <EyeOff size={12} />}
              </button>
            </div>
            {!surfaceMapData && (
              <ActionButton
                icon={<Layers size={13} />}
                label={surfaceMapLoading ? "加载中..." : "生成表面热力图"}
                loading={surfaceMapLoading}
                onClick={() => fetchSurfaceMap.mutate({
                  simId, modelId, field: heatmapField,
                })}
              />
            )}
            {surfaceMapData && (
              <div className="text-[9px] text-text-muted">
                表面映射已加载 — 模拟数据已叠加于模型表面
              </div>
            )}
          </div>
        </Section>
      )}

      {/* 10. FEA Structural Analysis */}
      <Section title={visualizationData ? "10. 有限元分析 (FEA)" : "4. 有限元分析 (FEA)"}>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">材料</span>
            <select
              value={feaMaterial}
              onChange={(e) => setFeaMaterial(e.target.value)}
              className="text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary"
            >
              <option value="pla">PLA</option>
              <option value="abs">ABS</option>
              <option value="petg">PETG</option>
              <option value="nylon">尼龙</option>
              <option value="silicone">硅胶</option>
              <option value="resin">树脂</option>
              <option value="aluminum">铝合金</option>
              <option value="steel">钢</option>
            </select>
          </div>
          <ActionButton
            icon={<Activity size={13} />}
            label={feaRunning ? "分析中..." : "运行结构分析"}
            loading={feaRunning}
            onClick={() => runFEA.mutate({ modelId, materialPreset: feaMaterial }, {
              onSuccess: ({ feaId: fid }) => {
                toastSuccess("FEA 分析完成");
                fetchFEAVis.mutate(fid);
              },
              onError: (e) => toastError("FEA 分析失败", (e as Error).message),
            })}
          />
          {feaResult && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
              className="mt-2 p-2 rounded bg-bg-secondary text-[10px] space-y-1">
              <div className="flex justify-between">
                <span className="text-text-muted">最大位移</span>
                <span className="text-accent">{(feaResult as Record<string, number>).max_displacement_mm?.toFixed(4)} mm</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">最大应力</span>
                <span className={(feaResult as Record<string, number>).min_safety_factor < 1.5 ? "text-danger" : ""}>
                  {(feaResult as Record<string, number>).max_stress_mpa?.toFixed(2)} MPa
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">最小安全系数</span>
                <span className={cn(
                  (feaResult as Record<string, number>).min_safety_factor < 1.0 ? "text-danger font-bold" :
                    (feaResult as Record<string, number>).min_safety_factor < 2.0 ? "text-warning" : "text-success"
                )}>
                  {(feaResult as Record<string, number>).min_safety_factor?.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">平均应力</span>
                <span>{(feaResult as Record<string, number>).avg_stress_mpa?.toFixed(3)} MPa</span>
              </div>
            </motion.div>
          )}

          {feaVisualizationData && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2 mt-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-text-muted">FEA 可视化</span>
                <button onClick={() => setFEAVisible(!feaVisible)}
                  className={cn("p-1 rounded transition-colors", feaVisible ? "bg-accent/20 text-accent" : "bg-bg-secondary text-text-muted")}>
                  {feaVisible ? <Eye size={12} /> : <EyeOff size={12} />}
                </button>
              </div>
              <div className="grid grid-cols-2 gap-1">
                {([
                  { v: "von_mises" as const, label: "Von Mises 应力" },
                  { v: "displacement" as const, label: "位移" },
                  { v: "safety_factor" as const, label: "安全系数" },
                  { v: "strain_energy" as const, label: "应变能" },
                ]).map((opt) => (
                  <button key={opt.v} onClick={() => setFEAField(opt.v)}
                    className={cn(
                      "px-1.5 py-1 rounded text-[9px] transition-colors",
                      feaField === opt.v
                        ? "bg-accent/20 text-accent ring-1 ring-accent/30"
                        : "bg-bg-secondary text-text-muted hover:bg-bg-hover",
                    )}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </div>
      </Section>
    </div>
  );
}

function AnalysisBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-success" : pct >= 40 ? "bg-accent" : "bg-warning";
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-text-muted">
        <span>{label}</span>
        <span className={pct >= 70 ? "text-success" : pct >= 40 ? "text-accent" : "text-warning"}>{pct}%</span>
      </div>
      <div className="h-1 rounded-full bg-bg-hover">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className={cn("h-full rounded-full", color)}
        />
      </div>
    </div>
  );
}

function CrossSectionCanvas({ data }: { data: { width: number; height: number; pixels: number[][] } }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height, pixels } = data;
    canvas.width = width;
    canvas.height = height;

    const imageData = ctx.createImageData(width, height);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const val = pixels[y]?.[x] ?? -1;
        const idx = (y * width + x) * 4;
        if (val < 0) {
          imageData.data[idx] = 19;
          imageData.data[idx + 1] = 19;
          imageData.data[idx + 2] = 26;
          imageData.data[idx + 3] = 255;
        } else {
          const [r, g, b] = heatmapColor(val);
          imageData.data[idx] = r;
          imageData.data[idx + 1] = g;
          imageData.data[idx + 2] = b;
          imageData.data[idx + 3] = 255;
        }
      }
    }
    ctx.putImageData(imageData, 0, 0);
  }, [data]);

  useCallback(() => draw, [draw]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useState(() => { setTimeout(draw, 0); });

  return (
    <canvas
      ref={canvasRef}
      className="w-full rounded border border-border/50"
      style={{ imageRendering: "pixelated", aspectRatio: `${data.width}/${data.height}` }}
    />
  );
}

function heatmapColor(t: number): [number, number, number] {
  t = Math.max(0, Math.min(1, t));
  let r: number, g: number, b: number;
  if (t < 0.25) {
    const s = t / 0.25;
    r = 13 + (0 - 13) * s;
    g = 13 + (128 - 13) * s;
    b = 128 + (204 - 128) * s;
  } else if (t < 0.5) {
    const s = (t - 0.25) / 0.25;
    r = 0 + 26 * s;
    g = 128 + (204 - 128) * s;
    b = 204 + (77 - 204) * s;
  } else if (t < 0.75) {
    const s = (t - 0.5) / 0.25;
    r = 26 + (242 - 26) * s;
    g = 204 + (217 - 204) * s;
    b = 77 + (28 - 77) * s;
  } else {
    const s = (t - 0.75) / 0.25;
    r = 242 + (230 - 242) * s;
    g = 217 + (38 - 217) * s;
    b = 28 + (25 - 28) * s;
  }
  return [Math.round(r), Math.round(g), Math.round(b)];
}

function ExportPanel() {
  const FORMAT_TIPS: Record<string, string> = {
    stl: "STL 为三角网格行业标准，适合 FDM/光固化切片与课堂快速分发。",
    obj: "OBJ 通用性好，便于与其他 DCC 工具交换；体积通常比二进制 STL 大。",
    ply: "PLY 适合点云与带属性的网格；科研与扫描数据常用。",
    glb: "glTF 二进制适合预览与 Web；单文件、加载快，打印前常在切片软件中转。",
    "3mf": "3MF 支持元数据与现代打印特性，适合多材料与生产级流程。",
  };

  function estimateExportBytes(
    formatKey: string,
    meshFaceCount: number | undefined,
    moldShellFaces: number | undefined,
    insertFaceCount: number | undefined,
  ): number {
    const faces =
      (meshFaceCount ?? 0) +
      (moldShellFaces ?? 0) +
      (insertFaceCount ?? 0);
    if (faces <= 0) return 0;
    const perFace =
      formatKey === "stl"
        ? 52
        : formatKey === "obj"
          ? 96
          : formatKey === "ply"
            ? 72
            : formatKey === "glb"
              ? 28
              : formatKey === "3mf"
                ? 40
                : 52;
    return Math.round(faces * perFace + 2048);
  }

  const modelId = useModelStore((s) => s.modelId);
  const filename = useModelStore((s) => s.filename);
  const meshInfo = useModelStore((s) => s.meshInfo);
  const moldId = useMoldStore((s) => s.moldId);
  const moldResult = useMoldStore((s) => s.moldResult);
  const insertId = useInsertStore((s) => s.insertId);
  const plates = useInsertStore((s) => s.plates);
  const exportModel = useExportModel();
  const exportMold = useExportMold();
  const exportInsert = useExportInsert();
  const exportAll = useExportAll();
  const [format, setFormat] = useState("stl");
  const [lastExport, setLastExport] = useState<{
    label: string;
    ok: boolean;
    at: number;
    detail?: string;
  } | null>(null);

  const moldShellFaceTotal =
    moldResult?.shells?.reduce((acc, s) => acc + (s.face_count ?? 0), 0) ?? 0;
  const insertFaceTotal =
    plates?.reduce((acc, p) => acc + (p.face_count ?? 0), 0) ?? 0;

  const estBytes = estimateExportBytes(
    format,
    meshInfo?.face_count,
    moldId ? moldShellFaceTotal : 0,
    insertId ? insertFaceTotal : 0,
  );

  const anyPending =
    exportModel.isPending ||
    exportMold.isPending ||
    exportInsert.isPending ||
    exportAll.isPending;

  const formatTip = FORMAT_TIPS[format] ?? FORMAT_TIPS.stl;

  return (
    <div className="space-y-4">
      <Section title="可导出数据概览">
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-lg border border-border/80 bg-bg-secondary/40 p-2.5 space-y-2 text-[10px]"
        >
          <div className="flex gap-2">
            <FileText size={14} className="text-accent shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <div>
                <span className="text-text-muted">模型</span>
                {modelId ? (
                  <div className="text-text-primary mt-0.5">
                    <span className="font-medium truncate block">
                      {filename ?? modelId}
                    </span>
                    {meshInfo && (
                      <span className="text-text-muted">
                        {meshInfo.face_count.toLocaleString()} 面 ·{" "}
                        {meshInfo.vertex_count.toLocaleString()} 顶点
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="text-warning mt-0.5">未加载模型</div>
                )}
              </div>
              <div className="border-t border-border/50 pt-1.5">
                <span className="text-text-muted">模具</span>
                {moldId ? (
                  <div className="text-text-primary mt-0.5">
                    已生成壳体
                    {moldResult != null && (
                      <span className="text-text-muted">
                        {" "}
                        · {moldResult.n_shells} 件 · 约{" "}
                        {moldShellFaceTotal.toLocaleString()} 面
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="text-text-muted mt-0.5">暂无模具数据</div>
                )}
              </div>
              <div className="border-t border-border/50 pt-1.5">
                <span className="text-text-muted">支撑 / 镶件</span>
                {insertId ? (
                  <div className="text-text-primary mt-0.5">
                    支撑板已就绪
                    {plates.length > 0 && (
                      <span className="text-text-muted">
                        {" "}
                        · {plates.length} 板 · 约{" "}
                        {insertFaceTotal.toLocaleString()} 面
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="text-text-muted mt-0.5">暂无镶件数据</div>
                )}
              </div>
            </div>
          </div>
          <div className="flex justify-between items-center border-t border-border/50 pt-2 text-[10px]">
            <span className="text-text-muted">估算导出体积（当前格式）</span>
            <span className="tabular-nums text-text-secondary font-medium">
              {estBytes > 0
                ? estBytes < 1024
                  ? `${estBytes} B`
                  : estBytes < 1024 * 1024
                    ? `${(estBytes / 1024).toFixed(1)} KB`
                    : `${(estBytes / (1024 * 1024)).toFixed(2)} MB`
                : "—"}
            </span>
          </div>
        </motion.div>
      </Section>

      <Section title="导出格式">
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          className="w-full text-xs bg-bg-secondary border border-border rounded px-2 py-1.5 text-text-primary"
        >
          <option value="stl">STL (FDM 打印推荐)</option>
          <option value="obj">OBJ (通用)</option>
          <option value="ply">PLY</option>
          <option value="glb">glTF Binary</option>
          <option value="3mf">3MF (现代3D打印)</option>
        </select>
        <motion.p
          key={format}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-2 text-[10px] text-text-muted leading-relaxed"
        >
          {formatTip}
        </motion.p>
      </Section>

      <Section title="单独导出">
        <div className="space-y-1.5">
          <ActionButton
            icon={<Download size={13} />}
            label="导出模型"
            loading={exportModel.isPending}
            onClick={() =>
              modelId &&
              exportModel.mutate(
                { model_id: modelId, format },
                {
                  onSuccess: () => {
                    toastSuccess("模型已导出", `${format.toUpperCase()} 格式`);
                    setLastExport({
                      label: "模型",
                      ok: true,
                      at: Date.now(),
                      detail: format.toUpperCase(),
                    });
                  },
                  onError: (e) => {
                    toastError("导出失败", (e as Error).message);
                    setLastExport({
                      label: "模型",
                      ok: false,
                      at: Date.now(),
                      detail: (e as Error).message,
                    });
                  },
                },
              )
            }
          />
          {moldId && (
            <ActionButton
              icon={<Box size={13} />}
              label="导出模具壳体 (ZIP)"
              loading={exportMold.isPending}
              onClick={() =>
                exportMold.mutate(
                  {
                    mold_id: moldId,
                    format,
                    include_model: true,
                    model_id: modelId ?? undefined,
                  },
                  {
                    onSuccess: () => {
                      toastSuccess("模具壳体已导出");
                      setLastExport({
                        label: "模具壳体 (ZIP)",
                        ok: true,
                        at: Date.now(),
                      });
                    },
                    onError: (e) => {
                      toastError("导出失败", (e as Error).message);
                      setLastExport({
                        label: "模具壳体",
                        ok: false,
                        at: Date.now(),
                        detail: (e as Error).message,
                      });
                    },
                  },
                )
              }
            />
          )}
          {insertId && (
            <ActionButton
              icon={<Pin size={13} />}
              label="导出支撑板 (ZIP)"
              loading={exportInsert.isPending}
              onClick={() =>
                exportInsert.mutate(
                  { insert_id: insertId, format },
                  {
                    onSuccess: () => {
                      toastSuccess("支撑板已导出");
                      setLastExport({
                        label: "支撑板 (ZIP)",
                        ok: true,
                        at: Date.now(),
                      });
                    },
                    onError: (e) => {
                      toastError("导出失败", (e as Error).message);
                      setLastExport({
                        label: "支撑板",
                        ok: false,
                        at: Date.now(),
                        detail: (e as Error).message,
                      });
                    },
                  },
                )
              }
            />
          )}
        </div>
      </Section>

      <Section title="一键导出">
        <ActionButton
          icon={<Package size={13} />}
          label="导出全部 (ZIP)"
          loading={exportAll.isPending}
          onClick={() =>
            exportAll.mutate(
              {
                model_id: modelId ?? undefined,
                mold_id: moldId ?? undefined,
                insert_id: insertId ?? undefined,
                format,
              },
              {
                onSuccess: () => {
                  toastSuccess("全部导出完成", "ZIP 包已下载");
                  setLastExport({
                    label: "全部 (ZIP)",
                    ok: true,
                    at: Date.now(),
                  });
                },
                onError: (e) => {
                  toastError("导出失败", (e as Error).message);
                  setLastExport({
                    label: "全部导出",
                    ok: false,
                    at: Date.now(),
                    detail: (e as Error).message,
                  });
                },
              },
            )
          }
        />
        <div className="mt-2 text-[10px] text-text-muted space-y-0.5">
          <div>
            包含:{" "}
            {[modelId && "模型", moldId && "模具壳体", insertId && "支撑板"]
              .filter(Boolean)
              .join(" + ") || "无数据"}
          </div>
          <div>格式: {format.toUpperCase()}</div>
        </div>
      </Section>

      {(anyPending || lastExport) && (
        <Section title="导出状态">
          {anyPending && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2 rounded-md border border-border/60 bg-bg-secondary/50 px-2.5 py-2 text-[10px] text-text-muted"
            >
              <Loader2 size={14} className="animate-spin text-accent shrink-0" />
              <span>正在准备下载…</span>
            </motion.div>
          )}
          {!anyPending && lastExport && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              className={cn(
                "rounded-md border px-2.5 py-2 text-[10px] space-y-1",
                lastExport.ok
                  ? "border-success/40 bg-success/5 text-text-secondary"
                  : "border-danger/40 bg-danger/5 text-danger",
              )}
            >
              <div className="flex items-center gap-1.5 font-medium">
                {lastExport.ok ? (
                  <CheckCircle2 size={14} className="text-success shrink-0" />
                ) : (
                  <span className="text-danger">✕</span>
                )}
                <span>
                  {lastExport.ok ? "上次导出成功" : "上次导出失败"} ·{" "}
                  {lastExport.label}
                </span>
              </div>
              <div className="text-text-muted pl-5">
                {new Date(lastExport.at).toLocaleString()}
                {lastExport.detail && (
                  <span className="block mt-0.5 break-words">
                    {lastExport.detail}
                  </span>
                )}
              </div>
            </motion.div>
          )}
        </Section>
      )}

      {(exportModel.isError || exportMold.isError || exportInsert.isError || exportAll.isError) && (
        <p className="text-[10px] text-danger">导出失败，请重试</p>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2">{title}</h4>
      {children}
    </div>
  );
}

function ActionButton({
  icon,
  label,
  loading,
  onClick,
}: {
  icon?: React.ReactNode;
  label: string;
  loading: boolean;
  onClick: () => void;
}) {
  return (
    <motion.button
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      disabled={loading}
      onClick={onClick}
      className="w-full flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md bg-bg-secondary hover:bg-bg-hover text-xs text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50"
    >
      {loading ? <Loader2 size={13} className="animate-spin" /> : icon}
      {label}
    </motion.button>
  );
}
