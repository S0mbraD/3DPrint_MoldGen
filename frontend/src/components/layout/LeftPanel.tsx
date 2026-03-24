import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, Upload, Settings, Loader2, Scissors, Maximize2, RotateCcw, Compass, SplitSquareVertical, Box, Droplets, Zap, RefreshCw, Pin, CheckCircle2, Download, Package, Grid3x3, FlipVertical, ArrowUpDown, RotateCw, ZoomIn, FileText, Layers, Activity, Slice, ChevronDown, BarChart3, Lightbulb, Ruler, Anchor } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../../stores/appStore";
import { useModelStore } from "../../stores/modelStore";
import { useMoldStore } from "../../stores/moldStore";
import { useSimStore } from "../../stores/simStore";
import { useInsertStore } from "../../stores/insertStore";
import { useUploadModel, useSimplifyModel, useSubdivideModel, useTransformModel, useRepairModel } from "../../hooks/useModelApi";
import { useOrientationAnalysis, usePartingGeneration, useMoldGeneration } from "../../hooks/useMoldApi";
import { useGatingDesign, useRunSimulation, useRunOptimization, useFetchVisualization, useFetchCrossSection, useFetchSurfaceMap, useRunFEA, useFetchFEAVisualization } from "../../hooks/useSimApi";
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

  const setStep = useAppStore((s) => s.setStep);

  if (!modelId) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-text-muted">
        <Scissors size={28} className="opacity-30" />
        <p className="text-xs">请先导入模型</p>
        <button onClick={() => setStep("import")} className="text-[10px] text-accent hover:underline">前往导入</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Section title="修复" icon={<RotateCcw size={11} />}>
        <ActionButton
          icon={<RotateCcw size={13} />}
          label="自动修复"
          loading={repair.isPending}
          variant="primary"
          onClick={() => handleAction("自动修复", () => repair.mutateAsync(modelId))}
        />
      </Section>

      <Section title="简化" icon={<Scissors size={11} />}>
        <ParamSlider label="保留比例" value={targetRatio} onChange={setTargetRatio} min={0.05} max={1} step={0.05} unit="" width="w-16" />
        <ActionButton
          icon={<Scissors size={13} />}
          label={`简化到 ${meshInfo ? Math.round(meshInfo.face_count * targetRatio).toLocaleString() : "?"} 面`}
          loading={simplify.isPending}
          onClick={() => handleAction("简化", () => simplify.mutateAsync({ modelId, ratio: targetRatio }))}
        />
      </Section>

      <Section title="细分" icon={<Grid3x3 size={11} />}>
        <ParamSlider label="迭代次数" value={subdivIter} onChange={(v) => setSubdivIter(Math.round(v))} min={1} max={4} step={1} unit="×" width="w-16" />
        <ActionButton
          icon={<Grid3x3 size={13} />}
          label={`Loop 细分 ×${subdivIter}`}
          loading={subdivide.isPending}
          onClick={() => handleAction("细分", () => subdivide.mutateAsync({ modelId, iterations: subdivIter }))}
        />
      </Section>

      <Section title="变换" icon={<Maximize2 size={11} />}>
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

      <Section title="旋转" icon={<RotateCw size={11} />}>
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

      <Section title="缩放" icon={<ZoomIn size={11} />}>
        <ParamSlider label="缩放倍率" value={scaleVal} onChange={setScaleVal} min={0.1} max={5} step={0.1} unit="×" width="w-16" />
        <ActionButton
          icon={<Maximize2 size={13} />}
          label={`缩放 ${scaleVal.toFixed(1)}×`}
          loading={transform.isPending}
          onClick={() => handleAction("缩放", () => transform.mutateAsync({ modelId, operation: "scale", factor: scaleVal }))}
        />
      </Section>

      <Section title="网格信息" icon={<Ruler size={11} />}>
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

      <StepHint
        text="模型编辑完成后，前往「方向」步骤分析最佳脱模方向。"
        action={() => setStep("orientation")}
        actionLabel="前往方向分析 →"
      />
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

  const setStep = useAppStore((s) => s.setStep);

  if (!modelId) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-text-muted">
        <Compass size={28} className="opacity-30" />
        <p className="text-xs">请先导入模型</p>
        <button onClick={() => setStep("import")} className="text-[10px] text-accent hover:underline">前往导入</button>
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
      <Section title="采样参数" icon={<Settings size={11} />}>
        <div className="space-y-2">
          <ParamSlider label="Fibonacci 采样" value={nSamples} onChange={(v) => setNSamples(Math.round(v))} min={50} max={500} step={50} />
          <ParamSlider label="精细候选数" value={nFinal} onChange={(v) => setNFinal(Math.round(v))} min={3} max={20} step={1} />
        </div>
      </Section>

      <Section title="方向分析" icon={<Compass size={11} />}>
        <ActionButton
          icon={<Compass size={13} />}
          label={isAnalyzing ? "分析中..." : "分析最优脱模方向"}
          loading={isAnalyzing}
          variant="primary"
          onClick={() => orientation.mutate({ modelId, nSamples, nFinal }, {
            onSuccess: (r) => toastSuccess("方向分析完成", `评分 ${(r.best_score.total_score * 100).toFixed(0)}%`),
            onError: (e) => toastError("分析失败", (e as Error).message),
          })}
        />
      </Section>

      {orientationResult && (
        <>
          <Section title="最佳方向" icon={<CheckCircle2 size={11} />}>
            <ResultCard>
              <ResultRow label="方向向量" value={`[${orientationResult.best_direction.map((v) => v.toFixed(3)).join(", ")}]`} />
              <ResultRow label="综合评分" value={`${(orientationResult.best_score.total_score * 100).toFixed(1)}%`} color="text-accent font-bold" />
              <div className="h-px bg-border my-0.5" />
              <ResultRow label="可见率" value={`${(orientationResult.best_score.visibility_ratio * 100).toFixed(1)}%`} />
              <ResultRow label="倒扣率" value={`${(orientationResult.best_score.undercut_ratio * 100).toFixed(1)}%`}
                color={orientationResult.best_score.undercut_ratio > 0.1 ? "text-danger" : "text-success"} />
              <ResultRow label="平坦度" value={`${(orientationResult.best_score.flatness * 100).toFixed(1)}%`} />
              <ResultRow label="最小拔模角" value={`${orientationResult.best_score.min_draft_angle.toFixed(1)}°`} />
              {orientationResult.best_score.mean_draft_angle != null && (
                <ResultRow label="平均拔模角" value={`${orientationResult.best_score.mean_draft_angle.toFixed(1)}°`} />
              )}
              <ResultRow label="对称性" value={`${(orientationResult.best_score.symmetry * 100).toFixed(1)}%`} />
              <ResultRow label="稳定性" value={`${(orientationResult.best_score.stability * 100).toFixed(1)}%`} />
            </ResultCard>
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

          <StepHint
            text="点击候选方向可直接切换。方向已自动应用到3D视口中（黄色箭头）。下一步请前往「模具」步骤。"
            action={() => setStep("mold")}
            actionLabel="前往模具 →"
          />
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
  const setStep = useAppStore((s) => s.setStep);
  const [wallThickness, setWallThickness] = useState(4.0);
  const [shellType, setShellType] = useState("box");
  const [partingStyle, setPartingStyle] = useState("flat");
  const [addFlanges, setAddFlanges] = useState(false);
  const [flangeCount, setFlangeCount] = useState(4);

  if (!modelId) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-text-muted">
        <Box size={28} className="opacity-30" />
        <p className="text-xs">请先导入模型</p>
        <button onClick={() => setStep("import")} className="text-[10px] text-accent hover:underline">前往导入</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Workflow status */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <StatusBadge ok={!!orientationResult} label="方向" />
        <StatusBadge ok={!!partingResult} label="分型面" />
        <StatusBadge ok={!!moldResult} label="壳体" />
      </div>

      <Section title="1. 脱模方向分析" icon={<Compass size={11} />}
        badge={orientationResult ? <span className="text-[8px] text-success font-medium">✓</span> : undefined}>
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
                      <span className="text-accent font-bold">{(((moldResult.pour_hole as { score?: number }).score ?? 0) * 100).toFixed(1)}%</span>
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
                <ResultRow label="定位销" value={`${moldResult.alignment_features.filter(f => f.type === "pin").length} 个`} />
                <ResultRow label="配合孔" value={`${moldResult.alignment_features.filter(f => f.type === "hole").length} 个`} />
              </div>
            )}
          </motion.div>
        )}
      </Section>

      {moldResult && (
        <StepHint
          text="模具已生成。可前往「内骨骼」步骤生成内部骨架结构，或前往「浇注」步骤设计浇注系统。"
          action={() => setStep("insert")}
          actionLabel="前往内骨骼 →"
        />
      )}
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
  const setStep = useAppStore((s) => s.setStep);

  const [organType, setOrganType] = useState("general");
  const [insertType, setInsertType] = useState("flat");
  const [thickness, setThickness] = useState(2.0);
  const [internalOffset, setInternalOffset] = useState(5.0);
  const [plateScale, setPlateScale] = useState(0.55);
  const [conformalOffset, setConformalOffset] = useState(3.0);
  // Feature toggles
  const [addMeshHoles, setAddMeshHoles] = useState(false);
  const [meshHoleSize, setMeshHoleSize] = useState(2.0);
  const [addRibs, setAddRibs] = useState(false);
  const [ribHeight, setRibHeight] = useState(3.0);
  const [ribSpacing, setRibSpacing] = useState(8.0);
  const [addInterlocking, setAddInterlocking] = useState<string | null>(null);
  const [interlockSize, setInterlockSize] = useState(2.0);
  // Pillars
  const [pillarDiameter, setPillarDiameter] = useState(2.0);
  const [pillarCount, setPillarCount] = useState(4);
  const [pillarSide, setPillarSide] = useState("auto");

  if (!modelId) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-text-muted">
        <Box size={28} className="opacity-30" />
        <p className="text-xs">请先导入模型</p>
        <button onClick={() => setStep("import")} className="text-[10px] text-accent hover:underline">前往导入</button>
      </div>
    );
  }

  const INSERT_TYPE_LABELS: Record<string, string> = {
    flat: "平板", conformal: "仿形板",
  };

  return (
    <div className="space-y-4">
      <div className="p-2 rounded-lg bg-accent/5 border border-accent/15">
        <p className="text-[10px] text-text-secondary leading-relaxed">
          内嵌支撑板置于硅胶教具内部，通过锚固特征与硅胶牢固结合，
          通过细小立柱穿过模具壁定位。为教具提供骨骼/组织的真实触感。
        </p>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <StatusBadge ok={!!modelId} label="模型" />
        <StatusBadge ok={!!moldId} label="模具" />
        <StatusBadge ok={positions.length > 0} label="分析" />
        <StatusBadge ok={plates.length > 0} label="支撑板" />
        <StatusBadge ok={assemblyValid} label="验证" />
      </div>

      <Section title="器官/模型类型" icon={<Layers size={11} />}>
        <select value={organType} onChange={(e) => setOrganType(e.target.value)}
          className="w-full text-xs bg-bg-secondary border border-border rounded px-2 py-1.5 text-text-primary">
          <option value="general">通用</option>
          <option value="solid">实质性器官 (肝/肾/脑)</option>
          <option value="hollow">空腔器官 (胃/膀胱)</option>
          <option value="tubular">管道结构 (血管/肠道)</option>
          <option value="limb">四肢/骨骼结构</option>
          <option value="sheet">组织片 (皮肤/肌肉)</option>
        </select>
      </Section>

      <Section title="1. 截面位置分析" icon={<Compass size={11} />}
        badge={positions.length > 0 ? <span className="text-[9px] text-accent">{positions.length} 个候选</span> : undefined}>
        <ActionButton
          icon={<Compass size={13} />}
          label={isAnalyzing ? "分析中..." : "分析截面位置"}
          loading={isAnalyzing}
          onClick={() => analyzePos.mutate({ model_id: modelId, organ_type: organType }, {
            onSuccess: () => toastSuccess("截面分析完成"),
            onError: (e) => toastError("截面分析失败", (e as Error).message),
          })}
        />
        {positions.length > 0 && (
          <ResultCard className="mt-2">
            {positions.slice(0, 5).map((p, i) => (
              <div key={i} className="flex justify-between items-center py-0.5">
                <div className="flex items-center gap-1">
                  <span className="text-text-muted w-4">#{i+1}</span>
                  <span className="text-text-secondary">{p.reason}</span>
                </div>
                <span className={cn("font-semibold", p.score > 0.6 ? "text-success" : p.score > 0.3 ? "text-accent" : "text-warning")}>
                  {(p.score * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </ResultCard>
        )}
      </Section>

      <Section title="2. 板型与参数" icon={<Settings size={11} />}>
        <div className="space-y-2">
          <ParamSelect label="基础板型" value={insertType} onChange={setInsertType}
            options={[
              { value: "flat", label: "平板 — 截面挤出" },
              { value: "conformal", label: "仿形板 — 跟随曲面" },
            ]} />
          <ParamSlider label="板厚" value={thickness} onChange={setThickness} min={1} max={5} step={0.5} unit="mm" />
          <ParamSlider label="内嵌深度" value={internalOffset} onChange={setInternalOffset} min={2} max={15} step={0.5} unit="mm" />
          <ParamSlider label="板面比例" value={plateScale} onChange={setPlateScale} min={0.2} max={0.8} step={0.05} unit="" />

          {insertType === "conformal" && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
              className="p-2 rounded-lg border border-accent/15 bg-accent/5 space-y-2">
              <div className="text-[9px] text-accent font-semibold uppercase tracking-wider">仿形参数</div>
              <ParamSlider label="曲面偏移" value={conformalOffset} onChange={setConformalOffset} min={1} max={8} step={0.5} unit="mm" />
            </motion.div>
          )}
        </div>
      </Section>

      <Section title="3. 板面特征 (可选)" icon={<Anchor size={11} />}>
        <div className="space-y-2.5">
          {/* Mesh Holes Toggle */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-secondary">表面网孔</span>
            <button onClick={() => setAddMeshHoles(!addMeshHoles)}
              className={cn("px-2.5 py-1 rounded text-[10px] font-medium transition-colors",
                addMeshHoles ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover")}>
              {addMeshHoles ? "已启用" : "关闭"}
            </button>
          </div>
          {addMeshHoles && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
              className="pl-2 border-l-2 border-accent/30 space-y-1.5">
              <ParamSlider label="孔径" value={meshHoleSize} onChange={setMeshHoleSize} min={1} max={4} step={0.5} unit="mm" />
              <div className="text-[9px] text-text-muted">硅胶渗透通孔，增强板-硅胶结合力</div>
            </motion.div>
          )}

          {/* Ribs Toggle */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-secondary">加强筋</span>
            <button onClick={() => setAddRibs(!addRibs)}
              className={cn("px-2.5 py-1 rounded text-[10px] font-medium transition-colors",
                addRibs ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover")}>
              {addRibs ? "已启用" : "关闭"}
            </button>
          </div>
          {addRibs && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
              className="pl-2 border-l-2 border-accent/30 space-y-1.5">
              <ParamSlider label="筋高度" value={ribHeight} onChange={setRibHeight} min={1} max={6} step={0.5} unit="mm" />
              <ParamSlider label="筋间距" value={ribSpacing} onChange={setRibSpacing} min={3} max={15} step={1} unit="mm" />
              <div className="text-[9px] text-text-muted">交叉肋条增强板面刚性</div>
            </motion.div>
          )}

          {/* Interlocking Toggle */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-secondary">啮合固定</span>
            <select value={addInterlocking ?? "none"}
              onChange={(e) => setAddInterlocking(e.target.value === "none" ? null : e.target.value)}
              className="text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary">
              <option value="none">关闭</option>
              <option value="dovetail">燕尾榫</option>
              <option value="bumps">凸起互锁</option>
              <option value="grooves">沟槽结合</option>
              <option value="diamond">菱形纹</option>
            </select>
          </div>
          {addInterlocking && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
              className="pl-2 border-l-2 border-accent/30 space-y-1.5">
              <ParamSlider label="特征尺寸" value={interlockSize} onChange={setInterlockSize} min={1} max={4} step={0.5} unit="mm" />
              <div className="text-[9px] text-text-muted">板面边缘/表面的机械咬合结构</div>
            </motion.div>
          )}
        </div>
      </Section>

      <Section title="4. 支撑立柱" icon={<Pin size={11} />}>
        <div className="space-y-2">
          <ParamSlider label="立柱直径" value={pillarDiameter} onChange={setPillarDiameter} min={1} max={4} step={0.5} unit="mm" />
          <ParamRow label="立柱数量">
            <div className="flex items-center gap-1">
              {[2, 3, 4, 6].map((n) => (
                <button key={n} onClick={() => setPillarCount(n)}
                  className={cn("w-6 h-6 rounded text-[10px] font-medium transition-colors",
                    pillarCount === n ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover")}>
                  {n}
                </button>
              ))}
            </div>
          </ParamRow>
          <ParamSelect label="立柱方位" value={pillarSide} onChange={setPillarSide}
            options={[
              { value: "auto", label: "自动 (最短轴)" },
              { value: "bottom", label: "底部 (-Y)" },
              { value: "top", label: "顶部 (+Y)" },
              { value: "back", label: "背面 (-Z)" },
              { value: "front", label: "正面 (+Z)" },
              { value: "left", label: "左侧 (-X)" },
              { value: "right", label: "右侧 (+X)" },
            ]} />
        </div>
      </Section>

      <Section title="5. 生成支撑板" icon={<Box size={11} />}>
        <ActionButton
          icon={<Box size={13} />}
          label={isGenerating ? "生成中..." : `生成${INSERT_TYPE_LABELS[insertType] ?? "支撑板"}`}
          loading={isGenerating}
          variant="primary"
          onClick={() => generate.mutate({
            model_id: modelId,
            organ_type: organType,
            insert_type: insertType,
            thickness,
            internal_offset: internalOffset,
            plate_scale: plateScale,
            conformal_offset: conformalOffset,
            add_mesh_holes: addMeshHoles,
            mesh_hole_size: meshHoleSize,
            add_ribs: addRibs,
            rib_height: ribHeight,
            rib_spacing: ribSpacing,
            add_interlocking: addInterlocking,
            interlock_feature_size: interlockSize,
            pillar_diameter: pillarDiameter,
            pillar_count: pillarCount,
            pillar_side: pillarSide,
            n_plates: 1,
            mold_id: moldId ?? undefined,
          } as Record<string, unknown>, {
            onSuccess: () => toastSuccess("支撑板已生成", INSERT_TYPE_LABELS[insertType]),
            onError: (e) => toastError("支撑板生成失败", (e as Error).message),
          })}
        />
        {plates.length > 0 && (
          <ResultCard className="mt-2">
            {plates.map((p, i) => (
              <div key={i} className="space-y-1 py-1 border-b border-border/30 last:border-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-accent font-bold">板{i+1}</span>
                    <span className="px-1 py-0.5 rounded bg-accent/10 text-accent text-[8px] font-medium">
                      {INSERT_TYPE_LABELS[p.insert_type ?? ""] ?? insertType}
                    </span>
                    {p.anchor && (
                      <span className="px-1 py-0.5 rounded bg-success/10 text-success text-[8px]">
                        {p.anchor.type ?? "锚固"}
                      </span>
                    )}
                  </div>
                  <span className="text-text-muted">{p.face_count.toLocaleString()} 面</span>
                </div>
                {p.n_pillars > 0 && (
                  <div className="text-[10px] text-text-muted">
                    支撑立柱: {p.n_pillars} 根
                  </div>
                )}
              </div>
            ))}
          </ResultCard>
        )}
      </Section>

      <Section title="6. 装配验证" icon={<CheckCircle2 size={11} />}>
        <ActionButton
          icon={<CheckCircle2 size={13} />}
          label="验证装配"
          loading={validate.isPending}
          disabled={!insertId}
          onClick={() => insertId && validate.mutate({ model_id: modelId, insert_id: insertId, mold_id: moldId ?? undefined }, {
            onSuccess: () => toastInfo("装配验证完成"),
            onError: (e) => toastError("验证失败", (e as Error).message),
          })}
        />
        {validationMessages.length > 0 && (
          <ResultCard className={cn("mt-2", assemblyValid ? "ring-1 ring-success/30" : "ring-1 ring-warning/30")}>
            <div className="flex items-center gap-1.5 mb-1">
              {assemblyValid
                ? <CheckCircle2 size={12} className="text-success" />
                : <span className="text-warning text-sm">⚠</span>}
              <span className={assemblyValid ? "text-success font-medium" : "text-warning font-medium"}>
                {assemblyValid ? "验证通过" : "存在问题"}
              </span>
            </div>
            {validationMessages.map((m, i) => (
              <div key={i} className="text-text-muted pl-5">{m}</div>
            ))}
          </ResultCard>
        )}
      </Section>

      {plates.length > 0 && (
        <StepHint
          text="支撑板已生成。板片嵌入硅胶内部，通过锚固特征结合，立柱穿过模具壁定位。可前往「浇注」步骤。"
          action={() => setStep("gating")}
          actionLabel="前往浇注系统 →"
        />
      )}
    </div>
  );
}

function GatingPanel() {
  const modelId = useModelStore((s) => s.modelId);
  const moldId = useMoldStore((s) => s.moldId);
  const { gatingId, gatingResult, isDesigningGating, selectedMaterial, setMaterial } = useSimStore();
  const gatingDesign = useGatingDesign();
  const setStep = useAppStore((s) => s.setStep);
  const [gateDiam, setGateDiam] = useState(6.0);
  const [runnerWidth, setRunnerWidth] = useState(4.0);
  const [nVents, setNVents] = useState(3);

  if (!modelId || !moldId) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-text-muted">
        <Droplets size={28} className="opacity-30" />
        <p className="text-xs">请先生成模具</p>
        <button onClick={() => setStep("mold")} className="text-[10px] text-accent hover:underline">前往模具步骤</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Section title="灌注材料" icon={<Layers size={11} />}>
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

      <Section title="浇口参数" icon={<Settings size={11} />}>
        <div className="space-y-2">
          <ParamSlider label="浇口直径" value={gateDiam} onChange={setGateDiam} min={2} max={12} step={0.5} unit="mm" />
          <ParamSlider label="浇道宽度" value={runnerWidth} onChange={setRunnerWidth} min={2} max={10} step={0.5} unit="mm" />
          <ParamRow label="排气孔数">
            <div className="flex items-center gap-1">
              {[1, 2, 3, 4, 6, 8].map((n) => (
                <button key={n} onClick={() => setNVents(n)}
                  className={cn("w-6 h-6 rounded text-[10px] font-medium transition-colors",
                    nVents === n ? "bg-accent text-white" : "bg-bg-secondary text-text-muted hover:bg-bg-hover")}>
                  {n}
                </button>
              ))}
            </div>
          </ParamRow>
        </div>
      </Section>

      <Section title="设计" icon={<Droplets size={11} />}>
        <ActionButton
          icon={<Droplets size={13} />}
          label={isDesigningGating ? "设计中..." : "自动设计浇注系统"}
          loading={isDesigningGating}
          variant="primary"
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
        <Section title="设计结果" icon={<CheckCircle2 size={11} />}>
          <ResultCard>
            <ResultRow label="浇口评分" value={`${(gatingResult.gate.score * 100).toFixed(1)}%`} color="text-accent font-bold" />
            <ResultRow label="流道平衡" value={`${(gatingResult.gate.flow_balance * 100).toFixed(1)}%`} />
            <ResultRow label="可达性" value={`${(gatingResult.gate.accessibility * 100).toFixed(1)}%`} />
            <div className="h-px bg-border my-0.5" />
            <ResultRow label="浇口直径" value={`${gatingResult.gate_diameter.toFixed(1)}mm`} />
            <ResultRow label="浇道宽度" value={`${gatingResult.runner_width.toFixed(1)}mm`} />
            <ResultRow label="排气孔" value={`${gatingResult.vents.length} 个`} />
            <div className="h-px bg-border my-0.5" />
            <ResultRow label="型腔体积" value={`${gatingResult.cavity_volume.toFixed(0)} mm³`} />
            <ResultRow label="预计材料" value={`${gatingResult.estimated_material_volume.toFixed(0)} mm³`} />
            <ResultRow label="预计充填" value={`${gatingResult.estimated_fill_time.toFixed(1)} s`} />
          </ResultCard>
        </Section>
      )}

      {gatingId && (
        <StepHint
          text="浇注系统已就绪。前往「仿真」步骤运行灌注仿真和自动优化。"
          action={() => setStep("simulation")}
          actionLabel="前往仿真 →"
        />
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
    heatmapField,
    particleDensity,
    crossSectionAxis, crossSectionPosition,
    crossSectionData,
    setCrossSectionAxis, setCrossSectionPosition,
    surfaceMapData, surfaceMapLoading,
    feaResult, feaVisualizationData, feaRunning,
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

  const setStep = useAppStore((s) => s.setStep);

  if (!modelId || !moldId) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-text-muted">
        <Droplets size={28} className="opacity-30" />
        <p className="text-xs">请先生成模具</p>
        <button onClick={() => setStep("mold")} className="text-[10px] text-accent hover:underline">前往模具步骤</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Workflow status */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <StatusBadge ok={!!gatingId} label="浇注" />
        <StatusBadge ok={!!simResult} label="仿真" />
        <StatusBadge ok={!!visualizationData} label="可视化" />
        <StatusBadge ok={!!optimizationResult} label="优化" />
        <StatusBadge ok={!!feaResult} label="FEA" />
      </div>

      {/* 1. Material */}
      <Section title="1. 材料选择" icon={<Layers size={11} />}>
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
      <Section title="2. 浇注系统" icon={<Droplets size={11} />}
        badge={gatingId ? <span className="text-[8px] text-success font-medium">✓</span> : undefined}>
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
      <Section title="3. 灌注仿真" icon={<Zap size={11} />}
        badge={simResult ? <span className={cn("text-[8px] font-medium", simResult.fill_fraction >= 0.99 ? "text-success" : "text-warning")}>
          {(simResult.fill_fraction * 100).toFixed(0)}%
        </span> : undefined}>
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

      {/* 4. Visualization Data */}
      {simResult && (
        <Section title="4. 可视化" icon={<BarChart3 size={11} />}
          badge={visualizationData ? <span className="text-[8px] text-success font-medium">已加载</span> : undefined}>
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
            <div className="space-y-2">
              <div className="text-[9px] text-success p-1.5 bg-success/5 rounded">
                ✓ 已加载 {(visualizationData.n_points * particleDensity).toLocaleString()} 粒子
                · {visualizationData.defect_positions.length} 缺陷
              </div>
              <div className="text-[9px] text-text-muted p-1.5 bg-bg-secondary rounded">
                可视化控制已移至视口下方浮动工具栏
              </div>
            </div>
          )}
          {!simResult.has_visualization && (
            <div className="text-[10px] text-text-muted p-2 bg-bg-secondary rounded">
              L1 启发式仿真不产生体素数据。请使用 L2 达西流获取完整可视化。
            </div>
          )}
        </Section>
      )}

      {/* 5. Surface Overlay */}
      {visualizationData && simId && (
        <Section title="5. 表面叠加" icon={<Layers size={11} />}
          badge={surfaceMapData ? <span className="text-[8px] text-success font-medium">已加载</span> : undefined}>
          {!surfaceMapData && (
            <ActionButton
              icon={<Layers size={13} />}
              label={surfaceMapLoading ? "加载中..." : "生成表面热力图"}
              loading={surfaceMapLoading}
              onClick={() => fetchSurfaceMap.mutate({ simId, modelId, field: heatmapField })}
            />
          )}
          {surfaceMapData && (
            <div className="text-[9px] text-success p-1.5 bg-success/5 rounded">
              ✓ 表面映射已叠加于模型表面 — 可在浮动栏切换
            </div>
          )}
        </Section>
      )}

      {/* 6. Cross-Section */}
      {visualizationData && simId && (
        <CollapsibleSection title="6. 截面分析" icon={<Slice size={11} />} defaultOpen={false}>
          <div className="space-y-2">
            <ParamRow label="截面轴">
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
            </ParamRow>
            <ParamSlider label="位置" value={crossSectionPosition} onChange={setCrossSectionPosition} min={0} max={1} step={0.02} width="w-20" />
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
        </CollapsibleSection>
      )}

      {/* 7. Analysis Report */}
      {simResult?.analysis && (
        <CollapsibleSection title="7. 综合分析" icon={<BarChart3 size={11} />} defaultOpen={false}
          badge={<span className={cn("text-[8px] font-bold", simResult.analysis.fill_quality_score > 0.7 ? "text-success" : "text-warning")}>
            {(simResult.analysis.fill_quality_score * 100).toFixed(0)}%
          </span>}>
          <div className="p-2 rounded bg-bg-secondary text-[10px] space-y-1.5">
            <div className="text-text-muted font-semibold">均匀性指标</div>
            <AnalysisBar label="充填均匀" value={simResult.analysis.fill_uniformity_index} />
            <AnalysisBar label="压力均匀" value={simResult.analysis.pressure_uniformity_index} />
            <AnalysisBar label="速度均匀" value={simResult.analysis.velocity_uniformity_index} />
            <AnalysisBar label="充填平衡" value={simResult.analysis.fill_balance_score} />

            <div className="text-text-muted font-semibold mt-2">剪切 & 温度</div>
            <ResultRow label="最大剪切率" value={`${simResult.analysis.max_shear_rate.toFixed(1)} 1/s`} />
            <ResultRow label="平均剪切率" value={`${simResult.analysis.avg_shear_rate.toFixed(1)} 1/s`} />
            <ResultRow label="温度范围" value={`${simResult.analysis.temperature_range[0].toFixed(1)}~${simResult.analysis.temperature_range[1].toFixed(1)} °C`} />
            <ResultRow label="平均固化" value={`${(simResult.analysis.avg_cure_progress * 100).toFixed(1)}%`} />

            <div className="text-text-muted font-semibold mt-2">壁厚分析</div>
            <ResultRow label="壁厚范围" value={`${simResult.analysis.min_thickness.toFixed(1)}~${simResult.analysis.max_thickness.toFixed(1)} mm`} />
            <ResultRow label="薄壁占比" value={`${(simResult.analysis.thin_wall_fraction * 100).toFixed(1)}%`}
              color={simResult.analysis.thin_wall_fraction > 0.1 ? "text-warning" : undefined} />
            <ResultRow label="厚壁占比" value={`${(simResult.analysis.thick_wall_fraction * 100).toFixed(1)}%`}
              color={simResult.analysis.thick_wall_fraction > 0.1 ? "text-warning" : undefined} />

            <div className="text-text-muted font-semibold mt-2">效率指标</div>
            <ResultRow label="流长比" value={simResult.analysis.flow_length_ratio.toFixed(1)} />
            <ResultRow label="浇口效率" value={`${(simResult.analysis.gate_efficiency * 100).toFixed(1)}%`} />
            <ResultRow label="滞流区" value={simResult.analysis.n_stagnation_zones}
              color={simResult.analysis.n_stagnation_zones > 3 ? "text-warning" : undefined} />
            <ResultRow label="高剪切区" value={simResult.analysis.n_high_shear_zones}
              color={simResult.analysis.n_high_shear_zones > 2 ? "text-warning" : undefined} />
          </div>

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
        </CollapsibleSection>
      )}

      {/* 8. Auto Optimization */}
      <Section title="8. 自动优化" icon={<RefreshCw size={11} />}>
        <ActionButton
          icon={<RefreshCw size={13} />}
          label={isOptimizing ? "优化中..." : "自动优化"}
          loading={isOptimizing}
          variant="primary"
          disabled={!gatingId}
          onClick={() => gatingId && runOpt.mutate({ modelId, moldId, gatingId }, {
            onSuccess: () => toastSuccess("优化完成"),
            onError: (e) => toastError("优化失败", (e as Error).message),
          })}
        />
        {optimizationResult && (
          <ResultCard className="mt-2">
            <ResultRow label="收敛" value={optimizationResult.converged ? "是" : "否"}
              color={optimizationResult.converged ? "text-success" : "text-warning"} />
            <ResultRow label="迭代次数" value={optimizationResult.iterations} />
            <div className="flex justify-between">
              <span className="text-text-muted">充填率</span>
              <span>
                {(optimizationResult.initial_fill_fraction * 100).toFixed(1)}%
                <span className="text-text-muted mx-0.5">→</span>
                <span className="text-accent font-semibold">{(optimizationResult.final_fill_fraction * 100).toFixed(1)}%</span>
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">缺陷数</span>
              <span>
                {optimizationResult.initial_defects}
                <span className="text-text-muted mx-0.5">→</span>
                <span className="text-accent font-semibold">{optimizationResult.final_defects}</span>
              </span>
            </div>
          </ResultCard>
        )}
      </Section>


      {/* 9. FEA Structural Analysis */}
      <Section title="9. 有限元分析 (FEA)" icon={<Activity size={11} />}
        badge={feaResult ? <span className="text-[8px] text-success font-medium">完成</span> : undefined}>
        <div className="space-y-2">
          <ParamSelect label="材料" value={feaMaterial} onChange={setFeaMaterial}
            options={[
              { value: "pla", label: "PLA" },
              { value: "abs", label: "ABS" },
              { value: "petg", label: "PETG" },
              { value: "nylon", label: "尼龙" },
              { value: "silicone", label: "硅胶" },
              { value: "resin", label: "树脂" },
              { value: "aluminum", label: "铝合金" },
              { value: "steel", label: "钢" },
            ]} />
          <ActionButton
            icon={<Activity size={13} />}
            label={feaRunning ? "分析中..." : "运行结构分析"}
            loading={feaRunning}
            variant="primary"
            onClick={() => runFEA.mutate({ modelId, materialPreset: feaMaterial }, {
              onSuccess: ({ feaId: fid }) => {
                toastSuccess("FEA 分析完成");
                fetchFEAVis.mutate(fid);
              },
              onError: (e) => toastError("FEA 分析失败", (e as Error).message),
            })}
          />
          {feaResult && (() => {
            const r = feaResult as Record<string, number>;
            return (
              <ResultCard className="mt-1">
                <ResultRow label="最大位移" value={`${r.max_displacement_mm?.toFixed(4)} mm`} color="text-accent" />
                <ResultRow label="最大应力" value={`${r.max_stress_mpa?.toFixed(2)} MPa`}
                  color={r.min_safety_factor < 1.5 ? "text-danger" : undefined} />
                <ResultRow label="最小安全系数" value={r.min_safety_factor?.toFixed(2)}
                  color={r.min_safety_factor < 1.0 ? "text-danger font-bold" : r.min_safety_factor < 2.0 ? "text-warning" : "text-success"} />
                <ResultRow label="平均应力" value={`${r.avg_stress_mpa?.toFixed(3)} MPa`} />
              </ResultCard>
            );
          })()}
          {feaVisualizationData && (
            <div className="text-[9px] text-success p-1.5 bg-success/5 rounded mt-1">
              ✓ FEA可视化已就绪 — 在视口下方浮动栏切换显示场
            </div>
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

  useEffect(() => { draw(); }, [draw]);

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
                    内骨骼已就绪
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
              label="导出内骨骼 (ZIP)"
              loading={exportInsert.isPending}
              onClick={() =>
                exportInsert.mutate(
                  { insert_id: insertId, format },
                  {
                    onSuccess: () => {
                      toastSuccess("内骨骼已导出");
                      setLastExport({
                        label: "内骨骼 (ZIP)",
                        ok: true,
                        at: Date.now(),
                      });
                    },
                    onError: (e) => {
                      toastError("导出失败", (e as Error).message);
                      setLastExport({
                        label: "内骨骼",
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
            {[modelId && "模型", moldId && "模具壳体", insertId && "内骨骼"]
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

function Section({ title, children, icon, badge }: { title: string; children: React.ReactNode; icon?: React.ReactNode; badge?: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        {icon && <span className="text-text-muted">{icon}</span>}
        <h4 className="text-[10px] font-semibold text-text-muted uppercase tracking-wider flex-1">{title}</h4>
        {badge}
      </div>
      {children}
    </div>
  );
}

function CollapsibleSection({ title, children, icon, badge, defaultOpen = false }: {
  title: string; children: React.ReactNode; icon?: React.ReactNode; badge?: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 mb-1 group">
        {icon && <span className="text-text-muted">{icon}</span>}
        <h4 className="text-[10px] font-semibold text-text-muted uppercase tracking-wider flex-1 text-left group-hover:text-text-secondary transition-colors">{title}</h4>
        {badge}
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown size={11} className="text-text-muted" />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ActionButton({
  icon,
  label,
  loading,
  onClick,
  variant = "default",
  disabled = false,
}: {
  icon?: React.ReactNode;
  label: string;
  loading: boolean;
  onClick: () => void;
  variant?: "default" | "primary";
  disabled?: boolean;
}) {
  return (
    <motion.button
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      disabled={loading || disabled}
      onClick={onClick}
      className={cn(
        "w-full flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs transition-colors disabled:opacity-50",
        variant === "primary"
          ? "bg-accent hover:bg-accent/90 text-white"
          : "bg-bg-secondary hover:bg-bg-hover text-text-secondary hover:text-text-primary",
      )}
    >
      {loading ? <Loader2 size={13} className="animate-spin" /> : icon}
      {label}
    </motion.button>
  );
}

function StepHint({ icon, text, action, actionLabel }: {
  icon?: React.ReactNode; text: string; action?: () => void; actionLabel?: string;
}) {
  return (
    <div className="p-2.5 rounded-lg border border-accent/20 bg-accent/5 text-[10px] text-text-secondary space-y-1.5">
      <div className="flex items-start gap-1.5">
        <span className="text-accent mt-0.5 shrink-0">{icon ?? <Lightbulb size={12} />}</span>
        <p className="leading-relaxed">{text}</p>
      </div>
      {action && actionLabel && (
        <button onClick={action}
          className="w-full text-center py-1 rounded bg-accent/10 hover:bg-accent/20 text-accent text-[10px] font-medium transition-colors">
          {actionLabel}
        </button>
      )}
    </div>
  );
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={cn(
      "px-1.5 py-0.5 rounded text-[8px] font-medium",
      ok ? "bg-success/10 text-success" : "bg-bg-secondary text-text-muted",
    )}>
      {ok ? "✓" : "○"} {label}
    </span>
  );
}

function ParamRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-text-muted">{label}</span>
      {children}
    </div>
  );
}

function ParamSlider({ label, value, onChange, min, max, step, unit, width = "w-20" }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number; unit?: string; width?: string;
}) {
  return (
    <ParamRow label={label}>
      <div className="flex items-center gap-1">
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))} className={cn(width, "accent-accent")} />
        <span className="text-[10px] text-text-muted w-12 text-right tabular-nums">
          {value % 1 === 0 ? value : value.toFixed(1)}{unit ?? ""}
        </span>
      </div>
    </ParamRow>
  );
}

function ParamSelect({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <ParamRow label={label}>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="text-[10px] bg-bg-secondary border border-border rounded px-1.5 py-0.5 text-text-primary">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </ParamRow>
  );
}

function ResultCard({ children, className: cls }: { children: React.ReactNode; className?: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      className={cn("p-2 rounded-lg bg-bg-secondary text-[10px] space-y-1", cls)}>
      {children}
    </motion.div>
  );
}

function ResultRow({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-text-muted">{label}</span>
      <span className={color ?? "text-text-primary"}>{value}</span>
    </div>
  );
}
