import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Key,
  Cpu,
  Box,
  FlaskConical,
  Layers,
  Palette,
  Info,
  CheckCircle,
  Loader2,
  Wifi,
  WifiOff,
  Network,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../../stores/appStore";
import { cn } from "../../lib/utils";

type SettingsTab = "api" | "mold" | "simulation" | "insert" | "gpu" | "ui" | "about";

const TABS: { id: SettingsTab; label: string; icon: typeof Key }[] = [
  { id: "api", label: "AI API", icon: Key },
  { id: "mold", label: "模具参数", icon: Box },
  { id: "simulation", label: "仿真参数", icon: FlaskConical },
  { id: "insert", label: "支撑板", icon: Layers },
  { id: "gpu", label: "GPU", icon: Cpu },
  { id: "ui", label: "界面", icon: Palette },
  { id: "about", label: "关于", icon: Info },
];

export function SettingsDialog() {
  const { settingsOpen, setSettingsOpen } = useAppStore();
  const [tab, setTab] = useState<SettingsTab>("api");

  useEffect(() => {
    if (!settingsOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setSettingsOpen(false);
      }
    };
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [settingsOpen, setSettingsOpen]);

  return (
    <AnimatePresence>
      {settingsOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60"
            onClick={() => setSettingsOpen(false)}
          />

          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
          >
            <div className="bg-bg-panel border border-border rounded-xl shadow-2xl w-[780px] max-h-[600px] flex overflow-hidden pointer-events-auto">
              <div className="w-[180px] bg-bg-secondary border-r border-border py-3 shrink-0">
                <div className="px-4 mb-3">
                  <h2 className="text-sm font-bold text-text-primary">设置</h2>
                </div>
                <nav className="space-y-0.5 px-2">
                  {TABS.map((t) => {
                    const Icon = t.icon;
                    return (
                      <button
                        key={t.id}
                        onClick={() => setTab(t.id)}
                        className={cn(
                          "w-full flex items-center gap-2 px-3 py-1.5 rounded-md text-xs transition-colors text-left",
                          tab === t.id
                            ? "bg-accent/15 text-accent"
                            : "text-text-secondary hover:bg-bg-hover hover:text-text-primary",
                        )}
                      >
                        <Icon size={13} />
                        {t.label}
                      </button>
                    );
                  })}
                </nav>
              </div>

              <div className="flex-1 flex flex-col min-w-0">
                <div className="flex items-center justify-between px-5 h-11 border-b border-border shrink-0">
                  <span className="text-xs font-semibold text-text-secondary">
                    {TABS.find((t) => t.id === tab)?.label}
                  </span>
                  <button
                    onClick={() => setSettingsOpen(false)}
                    className="p-1 rounded hover:bg-bg-hover text-text-muted"
                  >
                    <X size={14} />
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto p-5 space-y-5">
                  {tab === "api" && <ApiSettings />}
                  {tab === "mold" && <MoldSettings />}
                  {tab === "simulation" && <SimSettings />}
                  {tab === "insert" && <InsertSettings />}
                  {tab === "gpu" && <GpuSettings />}
                  {tab === "ui" && <UiSettings />}
                  {tab === "about" && <AboutSection />}
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// ── API Settings with Connectivity Verification + Topology ───────────

interface ServiceStatus {
  service: string;
  reachable: boolean;
  status_code: number;
  authenticated: boolean;
  latency_ms: number;
  error: string | null;
}

interface TopologyNode {
  id: string;
  label: string;
  type: string;
  status: string;
  detail?: string;
}

interface TopologyEdge {
  from: string;
  to: string;
  label: string;
}

function ApiSettings() {
  const [keys, setKeys] = useState({
    deepseek: "",
    qwen: "",
    kimi: "",
    wanxiang: "",
    tripo: "",
  });

  const [statuses, setStatuses] = useState<Record<string, ServiceStatus>>({});
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [testingAll, setTestingAll] = useState(false);
  const [topology, setTopology] = useState<{ nodes: TopologyNode[]; edges: TopologyEdge[] } | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const checkBackend = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/system/health");
      setBackendOnline(res.ok);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  const fetchTopology = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/system/topology");
      if (res.ok) {
        const data = await res.json();
        if (statuses) {
          data.nodes = data.nodes.map((n: TopologyNode) => {
            const s = statuses[n.id];
            if (s) {
              return { ...n, status: s.reachable ? (s.authenticated ? "online" : "reachable") : "offline" };
            }
            return n;
          });
        }
        setTopology(data);
      }
    } catch { /* ignore */ }
  }, [statuses]);

  useEffect(() => {
    checkBackend();
    fetchTopology();
  }, [checkBackend, fetchTopology]);

  const testSingle = async (service: string) => {
    setTesting((p) => ({ ...p, [service]: true }));
    try {
      const res = await fetch("/api/v1/system/connectivity/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service, api_key: keys[service as keyof typeof keys] || "" }),
      });
      if (res.ok) {
        const data: ServiceStatus = await res.json();
        setStatuses((p) => ({ ...p, [service]: data }));
      }
    } catch { /* ignore */ }
    setTesting((p) => ({ ...p, [service]: false }));
  };

  const testAll = async () => {
    setTestingAll(true);
    try {
      const res = await fetch("/api/v1/system/connectivity/check-all", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(keys),
      });
      if (res.ok) {
        const data = await res.json();
        const map: Record<string, ServiceStatus> = {};
        for (const s of data.services) {
          map[s.service] = s;
        }
        setStatuses(map);
      }
    } catch { /* ignore */ }
    setTestingAll(false);
    fetchTopology();
  };

  const services = [
    { key: "deepseek", label: "DeepSeek API Key", placeholder: "sk-..." },
    { key: "qwen", label: "通义千问 (Qwen) API Key", placeholder: "sk-..." },
    { key: "kimi", label: "Kimi (Moonshot) API Key", placeholder: "sk-..." },
    { key: "wanxiang", label: "通义万相 API Key", placeholder: "sk-..." },
    { key: "tripo", label: "Tripo3D API Key", placeholder: "tsk_..." },
  ];

  return (
    <div className="space-y-5">
      {/* Backend status */}
      <div className="flex items-center gap-2 p-2.5 rounded-lg bg-bg-secondary">
        <div className={cn("w-2 h-2 rounded-full", backendOnline === true ? "bg-green-400" : backendOnline === false ? "bg-red-400" : "bg-yellow-400")} />
        <span className="text-[11px] text-text-secondary">
          后端服务: {backendOnline === true ? "在线" : backendOnline === false ? "离线" : "检测中..."}
        </span>
        <button onClick={checkBackend} className="ml-auto text-[10px] text-accent hover:underline">刷新</button>
      </div>

      <p className="text-[11px] text-text-muted">
        配置 AI 服务 API Key。密钥仅存储在本地，不会上传至云端。
      </p>

      {services.map((svc) => {
        const status = statuses[svc.key];
        const isTesting = testing[svc.key];
        return (
          <div key={svc.key} className="space-y-1">
            <div className="flex items-center gap-2">
              <label className="text-[11px] text-text-secondary font-medium flex-1">{svc.label}</label>
              {status && (
                <StatusBadge status={status} />
              )}
              <button
                onClick={() => testSingle(svc.key)}
                disabled={isTesting}
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded border transition-colors",
                  isTesting
                    ? "border-border text-text-muted cursor-wait"
                    : "border-accent/30 text-accent hover:bg-accent/10",
                )}
              >
                {isTesting ? <Loader2 size={10} className="animate-spin inline" /> : "测试"}
              </button>
            </div>
            <input
              type="password"
              placeholder={svc.placeholder}
              value={keys[svc.key as keyof typeof keys]}
              onChange={(e) => setKeys({ ...keys, [svc.key]: e.target.value })}
              className="w-full text-xs bg-bg-secondary border border-border rounded-md px-3 py-1.5 text-text-primary placeholder:text-text-muted outline-none focus:ring-1 focus:ring-accent"
            />
          </div>
        );
      })}

      <div className="flex gap-2 justify-end">
        <button
          onClick={testAll}
          disabled={testingAll}
          className="px-3 py-1.5 rounded-md border border-accent/30 text-accent text-xs hover:bg-accent/10 transition-colors disabled:opacity-50 flex items-center gap-1.5"
        >
          {testingAll ? <Loader2 size={11} className="animate-spin" /> : <Wifi size={11} />}
          全部测试
        </button>
        <button
          onClick={async () => {
            try {
              const res = await fetch("/api/v1/system/api-keys/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(keys),
              });
              if (res.ok) {
                const data = await res.json();
                setSaveStatus(`已保存 ${data.saved} 个密钥`);
                setTimeout(() => setSaveStatus(null), 3000);
              } else {
                setSaveStatus("保存失败");
              }
            } catch {
              setSaveStatus("保存失败：无法连接后端");
            }
          }}
          className="px-4 py-1.5 rounded-md bg-accent text-white text-xs hover:bg-accent-hover transition-colors flex items-center gap-1.5"
        >
          <CheckCircle size={11} />
          保存
        </button>
        {saveStatus && (
          <span className="text-[10px] text-green-400 self-center ml-1">{saveStatus}</span>
        )}
      </div>

      {/* Topology Diagram */}
      <div className="border-t border-border pt-4">
        <div className="flex items-center gap-1.5 mb-3">
          <Network size={13} className="text-text-muted" />
          <span className="text-[11px] font-semibold text-text-secondary">后端链路拓扑</span>
          <button onClick={fetchTopology} className="ml-auto text-[10px] text-accent hover:underline">刷新</button>
        </div>
        {topology ? (
          <TopologyDiagram nodes={topology.nodes} edges={topology.edges} statuses={statuses} backendOnline={backendOnline} />
        ) : (
          <div className="text-center text-[11px] text-text-muted py-6">加载拓扑中...</div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: ServiceStatus }) {
  if (status.authenticated) {
    return (
      <span className="flex items-center gap-1 text-[10px] text-green-400">
        <CheckCircle size={10} /> {status.latency_ms}ms
      </span>
    );
  }
  if (status.reachable) {
    return (
      <span className="flex items-center gap-1 text-[10px] text-yellow-400">
        <Wifi size={10} /> 可达({status.status_code}) {status.latency_ms}ms
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-[10px] text-red-400">
      <WifiOff size={10} /> 不可达
    </span>
  );
}

/* ── Topology Diagram (SVG) ──────────────────────────────────────────── */

const NODE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  client:     { bg: "#1e293b", border: "#3b82f6", text: "#93c5fd" },
  server:     { bg: "#1e293b", border: "#22c55e", text: "#86efac" },
  hardware:   { bg: "#1e293b", border: "#f59e0b", text: "#fcd34d" },
  library:    { bg: "#1e293b", border: "#8b5cf6", text: "#c4b5fd" },
  ai_service: { bg: "#1e293b", border: "#ec4899", text: "#f9a8d4" },
};

const STATUS_COLORS: Record<string, string> = {
  online: "#22c55e",
  reachable: "#f59e0b",
  offline: "#ef4444",
  unknown: "#6b7280",
};

function TopologyDiagram({
  nodes,
  edges,
  statuses,
  backendOnline,
}: {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  statuses: Record<string, ServiceStatus>;
  backendOnline: boolean | null;
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  const resolvedNodes = nodes.map((n) => {
    let status = n.status;
    if (n.id === "frontend") status = "online";
    if (n.id === "backend") status = backendOnline ? "online" : "offline";
    const s = statuses[n.id];
    if (s) status = s.reachable ? (s.authenticated ? "online" : "reachable") : "offline";
    return { ...n, status };
  });

  // Layout: 3 tiers (left = frontend, center = backend+gpu+engine, right = AI services)
  const W = 540, H = 310;
  const positions: Record<string, { x: number; y: number }> = {};

  // Left tier
  positions["frontend"] = { x: 60, y: H / 2 };

  // Center tier
  positions["backend"] = { x: 220, y: 80 };
  positions["gpu"]     = { x: 220, y: 175 };
  positions["trimesh"] = { x: 220, y: 260 };

  // Right tier (AI services)
  const aiNodes = resolvedNodes.filter((n) => n.type === "ai_service");
  const aiStartY = 40;
  const aiGap = (H - 80) / Math.max(aiNodes.length - 1, 1);
  aiNodes.forEach((n, i) => {
    positions[n.id] = { x: 430, y: aiStartY + i * aiGap };
  });

  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 280 }}>
      <defs>
        <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="6" refY="2" orient="auto">
          <polygon points="0 0, 6 2, 0 4" fill="#475569" />
        </marker>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Edges */}
      {edges.map((e, i) => {
        const from = positions[e.from];
        const to = positions[e.to];
        if (!from || !to) return null;
        const mx = (from.x + to.x) / 2;
        const my = (from.y + to.y) / 2;
        return (
          <g key={i}>
            <line
              x1={from.x + 55} y1={from.y}
              x2={to.x - 55} y2={to.y}
              stroke="#334155"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              markerEnd="url(#arrowhead)"
            />
            <text x={mx} y={my - 6} textAnchor="middle" fontSize={8} fill="#64748b">
              {e.label}
            </text>
          </g>
        );
      })}

      {/* Nodes */}
      {resolvedNodes.map((n) => {
        const pos = positions[n.id];
        if (!pos) return null;
        const colors = NODE_COLORS[n.type] || NODE_COLORS.ai_service;
        const statusColor = STATUS_COLORS[n.status] || STATUS_COLORS.unknown;
        return (
          <g key={n.id}>
            <rect
              x={pos.x - 50} y={pos.y - 18}
              width={100} height={36}
              rx={6}
              fill={colors.bg}
              stroke={colors.border}
              strokeWidth={1.5}
              opacity={0.9}
            />
            {/* Status dot */}
            <circle cx={pos.x + 38} cy={pos.y - 8} r={3.5} fill={statusColor} filter="url(#glow)" />
            <text x={pos.x} y={pos.y + 2} textAnchor="middle" fontSize={10} fill={colors.text} fontWeight="600">
              {n.label}
            </text>
            {n.detail && (
              <text x={pos.x} y={pos.y + 13} textAnchor="middle" fontSize={7} fill="#64748b">
                {n.detail}
              </text>
            )}
          </g>
        );
      })}

      {/* Legend */}
      <g transform={`translate(10, ${H - 28})`}>
        {[
          { color: STATUS_COLORS.online, label: "在线" },
          { color: STATUS_COLORS.reachable, label: "可达" },
          { color: STATUS_COLORS.offline, label: "离线" },
          { color: STATUS_COLORS.unknown, label: "未知" },
        ].map((item, i) => (
          <g key={i} transform={`translate(${i * 60}, 0)`}>
            <circle cx={0} cy={0} r={3} fill={item.color} />
            <text x={7} y={3} fontSize={8} fill="#94a3b8">{item.label}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}

// ── Other Settings Tabs ──────────────────────────────────────────────

function MoldSettings() {
  const [cfg, setCfg] = useState({
    wallThickness: 4.0,
    clearance: 0.3,
    shellType: "box",
    addPins: true,
    addPourHole: true,
    addVentHoles: true,
    fibonacciSamples: 100,
  });

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-text-muted">模具生成默认参数</p>
      <SettingSlider label="壁厚 (mm)" min={1} max={10} step={0.5}
        value={cfg.wallThickness} onChange={(v) => setCfg({ ...cfg, wallThickness: v })} />
      <SettingSlider label="间隙 (mm)" min={0.1} max={1.0} step={0.1}
        value={cfg.clearance} onChange={(v) => setCfg({ ...cfg, clearance: v })} />
      <SettingSelect label="默认壳类型" value={cfg.shellType}
        options={[{ value: "box", label: "方形壳体" }, { value: "conformal", label: "随形壳体" }]}
        onChange={(v) => setCfg({ ...cfg, shellType: v })} />
      <SettingSlider label="Fibonacci 采样数" min={50} max={500} step={10}
        value={cfg.fibonacciSamples} onChange={(v) => setCfg({ ...cfg, fibonacciSamples: v })} />
      <SettingToggle label="添加定位销" checked={cfg.addPins}
        onChange={(v) => setCfg({ ...cfg, addPins: v })} />
      <SettingToggle label="添加浇注口" checked={cfg.addPourHole}
        onChange={(v) => setCfg({ ...cfg, addPourHole: v })} />
      <SettingToggle label="添加排气孔" checked={cfg.addVentHoles}
        onChange={(v) => setCfg({ ...cfg, addVentHoles: v })} />
    </div>
  );
}

function SimSettings() {
  const [cfg, setCfg] = useState({
    defaultLevel: 1,
    voxelResolution: 64,
    maxOptIterations: 5,
    targetFillFraction: 0.99,
    defaultMaterial: "silicone_a30",
    useGpu: true,
  });

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-text-muted">仿真与优化默认参数</p>
      <SettingSelect label="默认仿真级别" value={String(cfg.defaultLevel)}
        options={[{ value: "1", label: "L1 启发式 (快速)" }, { value: "2", label: "L2 达西流 (精确)" }]}
        onChange={(v) => setCfg({ ...cfg, defaultLevel: parseInt(v) })} />
      <SettingSlider label="体素分辨率" min={32} max={256} step={16}
        value={cfg.voxelResolution} onChange={(v) => setCfg({ ...cfg, voxelResolution: v })} />
      <SettingSlider label="最大优化迭代" min={1} max={20} step={1}
        value={cfg.maxOptIterations} onChange={(v) => setCfg({ ...cfg, maxOptIterations: v })} />
      <SettingSlider label="目标充填率" min={0.9} max={1.0} step={0.01}
        value={cfg.targetFillFraction} onChange={(v) => setCfg({ ...cfg, targetFillFraction: v })} />
      <SettingSelect label="默认材料" value={cfg.defaultMaterial}
        options={[
          { value: "silicone_a10", label: "硅胶 Shore A10" },
          { value: "silicone_a30", label: "硅胶 Shore A30" },
          { value: "silicone_a50", label: "硅胶 Shore A50" },
          { value: "polyurethane", label: "聚氨酯" },
          { value: "epoxy_resin", label: "环氧树脂" },
        ]}
        onChange={(v) => setCfg({ ...cfg, defaultMaterial: v })} />
      <SettingToggle label="GPU 加速" checked={cfg.useGpu}
        onChange={(v) => setCfg({ ...cfg, useGpu: v })} />
    </div>
  );
}

function InsertSettings() {
  const [cfg, setCfg] = useState({
    defaultThickness: 2.0,
    edgeChamfer: 0.5,
    margin: 1.5,
    defaultAnchor: "mesh_holes",
    anchorDensity: 0.3,
    featureSize: 2.0,
  });

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-text-muted">支撑板生成默认参数</p>
      <SettingSlider label="默认板厚 (mm)" min={0.5} max={5} step={0.5}
        value={cfg.defaultThickness} onChange={(v) => setCfg({ ...cfg, defaultThickness: v })} />
      <SettingSlider label="边缘倒角 (mm)" min={0} max={2} step={0.1}
        value={cfg.edgeChamfer} onChange={(v) => setCfg({ ...cfg, edgeChamfer: v })} />
      <SettingSlider label="边界裕量 (mm)" min={0.5} max={5} step={0.5}
        value={cfg.margin} onChange={(v) => setCfg({ ...cfg, margin: v })} />
      <SettingSelect label="默认锚固类型" value={cfg.defaultAnchor}
        options={[
          { value: "mesh_holes", label: "网孔" },
          { value: "bumps", label: "凸起" },
          { value: "grooves", label: "沟槽" },
          { value: "dovetail", label: "燕尾" },
          { value: "diamond", label: "菱形纹" },
        ]}
        onChange={(v) => setCfg({ ...cfg, defaultAnchor: v })} />
      <SettingSlider label="锚固密度" min={0.1} max={0.8} step={0.05}
        value={cfg.anchorDensity} onChange={(v) => setCfg({ ...cfg, anchorDensity: v })} />
      <SettingSlider label="特征尺寸 (mm)" min={0.5} max={5} step={0.5}
        value={cfg.featureSize} onChange={(v) => setCfg({ ...cfg, featureSize: v })} />
    </div>
  );
}

function GpuSettings() {
  const gpu = useAppStore((s) => s.gpu);
  const [liveGpu, setLiveGpu] = useState<{
    used_mb: number; free_mb: number; total_mb: number; utilization: number;
  } | null>(null);
  const [gpuAccel, setGpuAccel] = useState(true);
  const [autoFallback, setAutoFallback] = useState(true);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const res = await fetch("/api/v1/system/gpu");
        if (res.ok && active) {
          const data = await res.json();
          setLiveGpu(data);
        }
      } catch { /* ignore */ }
    };
    poll();
    const timer = setInterval(poll, 5000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  const vramUsed = liveGpu?.used_mb ?? gpu?.vram_used_mb ?? 0;
  const vramTotal = liveGpu?.total_mb ?? gpu?.vram_total_mb ?? 1;
  const vramPct = vramTotal > 0 ? Math.round((vramUsed / vramTotal) * 100) : 0;

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-text-muted">GPU 状态与设置（每 5 秒自动刷新）</p>
      <div className="p-3 rounded-lg bg-bg-secondary space-y-2">
        <InfoRow label="状态" value={gpu?.available ? "可用" : "不可用"}
          valueClass={gpu?.available ? "text-green-400" : "text-red-400"} />
        <InfoRow label="设备" value={gpu?.device_name ?? "—"} />
        <InfoRow label="计算能力" value={gpu?.compute_capability ?? "—"} />
        <InfoRow label="CUDA 版本" value={gpu?.cuda_version ?? "—"} />
        <InfoRow label="驱动版本" value={gpu?.driver_version ?? "—"} />
        <InfoRow label="Numba CUDA" value={gpu?.numba_cuda ? "可用" : "不可用"}
          valueClass={gpu?.numba_cuda ? "text-green-400" : "text-text-muted"} />
        <InfoRow label="CuPy" value={gpu?.cupy ? "可用" : "不可用"}
          valueClass={gpu?.cupy ? "text-green-400" : "text-text-muted"} />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-text-secondary">VRAM 使用</span>
          <span className="text-text-muted font-mono">{vramUsed} / {vramTotal} MB ({vramPct}%)</span>
        </div>
        <div className="h-2 rounded-full bg-bg-secondary overflow-hidden">
          <motion.div
            className={cn(
              "h-full rounded-full transition-colors",
              vramPct > 90 ? "bg-red-500" : vramPct > 70 ? "bg-yellow-500" : "bg-green-500",
            )}
            initial={{ width: 0 }}
            animate={{ width: `${vramPct}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>
      </div>

      <SettingToggle label="启用 GPU 加速仿真" checked={gpuAccel} onChange={setGpuAccel} />
      <SettingToggle label="GPU OOM 时自动降级 CPU" checked={autoFallback} onChange={setAutoFallback} />
    </div>
  );
}

function UiSettings() {
  return (
    <div className="space-y-4">
      <p className="text-[11px] text-text-muted">界面偏好设置</p>
      <SettingToggle label="显示网格辅助线" checked={true} onChange={() => {}} />
      <SettingToggle label="显示方向箭头" checked={true} onChange={() => {}} />
      <SettingToggle label="显示坐标轴" checked={true} onChange={() => {}} />
      <SettingToggle label="启用模型自动旋转" checked={false} onChange={() => {}} />
      <SettingSelect label="语言" value="zh" options={[
        { value: "zh", label: "中文" }, { value: "en", label: "English" },
      ]} onChange={() => {}} />
    </div>
  );
}

function AboutSection() {
  return (
    <div className="space-y-4">
      <div className="text-center py-4">
        <h3 className="text-lg font-bold text-accent mb-1">MoldGen</h3>
        <p className="text-xs text-text-muted">AI 驱动的医学教具智能模具生成工作站</p>
        <p className="text-[10px] text-text-muted mt-2">v0.1.0-dev</p>
      </div>
      <div className="p-3 rounded-lg bg-bg-secondary space-y-1 text-[11px]">
        <InfoRow label="框架" value="Tauri 2.0 + React + Three.js" />
        <InfoRow label="后端" value="Python / FastAPI / trimesh" />
        <InfoRow label="AI" value="DeepSeek / Qwen / Kimi / 万相 / Tripo3D" />
        <InfoRow label="加速" value="CUDA / Numba / CuPy" />
      </div>
      <div className="text-center">
        <p className="text-[10px] text-text-muted">面向临床教学与手术教具开发</p>
      </div>
    </div>
  );
}

// ── Reusable Setting Controls ────────────────────────────────────────

function SettingSlider({
  label, min, max, step, value, onChange,
}: {
  label: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-text-secondary">{label}</span>
      <div className="flex items-center gap-2">
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))} className="w-24 accent-accent" />
        <span className="text-[10px] text-text-muted w-12 text-right font-mono">
          {value % 1 === 0 ? value : value.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

function SettingSelect({
  label, value, options, onChange,
}: {
  label: string; value: string; options: { value: string; label: string }[]; onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-text-secondary">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="text-[11px] bg-bg-secondary border border-border rounded px-2 py-1 text-text-primary">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function SettingToggle({
  label, checked, onChange,
}: {
  label: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-text-secondary">{label}</span>
      <button
        onClick={() => onChange(!checked)}
        className={cn(
          "w-8 h-4 rounded-full transition-colors relative",
          checked ? "bg-accent" : "bg-border",
        )}
      >
        <div className={cn(
          "w-3 h-3 rounded-full bg-white absolute top-0.5 transition-transform",
          checked ? "translate-x-4" : "translate-x-0.5",
        )} />
      </button>
    </div>
  );
}

function InfoRow({
  label, value, valueClass,
}: {
  label: string; value: string; valueClass?: string;
}) {
  return (
    <div className="flex justify-between text-[11px]">
      <span className="text-text-muted">{label}</span>
      <span className={valueClass ?? "text-text-primary"}>{value}</span>
    </div>
  );
}
