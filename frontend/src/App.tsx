import { useEffect, Component, type ReactNode, type ErrorInfo } from "react";
import { StatusBar } from "./components/layout/StatusBar";
import { LeftPanel } from "./components/layout/LeftPanel";
import { RightPanel } from "./components/layout/RightPanel";
import { Viewport } from "./components/viewer/Viewport";
import { ChatBubble } from "./components/ai/ChatBubble";
import { AgentWorkstation } from "./components/ai/AgentWorkstation";
import { SettingsDialog } from "./components/settings/SettingsDialog";
import { ToastContainer } from "./components/ui/ToastContainer";
import { ConsolePanel } from "./components/ui/ConsolePanel";
import { useSystemInfo } from "./hooks/useSystemInfo";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useBackendStatus } from "./hooks/useBackendStatus";
import { UpdateNotification } from "./components/settings/UpdateChecker";
import { WorkflowPipeline } from "./components/layout/WorkflowPipeline";
import { StepToolbar as StepToolbarOverlay } from "./components/layout/StepToolbar";
import { PanelLeftOpen, PanelRightOpen, Settings, Terminal } from "lucide-react";
import { useAppStore } from "./stores/appStore";
import { toastSuccess, toastWarning, toastError } from "./stores/toastStore";

/* ── Global Error Boundary ───────────────────────────────────────── */

interface ErrorBoundaryState { hasError: boolean; error?: Error }

class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
    toastError("渲染错误", error.message);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen flex items-center justify-center bg-bg-primary text-text-primary">
          <div className="text-center p-8 max-w-lg">
            <h2 className="text-xl font-bold text-red-400 mb-2">应用渲染异常</h2>
            <p className="text-sm text-text-muted mb-4">{this.state.error?.message}</p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-accent text-white rounded hover:opacity-90"
            >
              重新加载
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/* ── Main App ────────────────────────────────────────────────────── */

export default function App() {
  const { leftPanelOpen, rightPanelOpen, toggleLeftPanel, toggleRightPanel, toggleSettings } =
    useAppStore();
  const consoleOpen = useAppStore((s) => s.consoleOpen);
  const toggleConsole = useAppStore((s) => s.toggleConsole);
  const { data: sysInfo } = useSystemInfo();
  const { status: backendStatus } = useBackendStatus();
  useKeyboardShortcuts();

  /* global unhandled error / promise rejection → toast */
  useEffect(() => {
    const onError = (e: ErrorEvent) => {
      toastError("JS 错误", e.message);
    };
    const onReject = (e: PromiseRejectionEvent) => {
      toastError("未捕获 Promise", String(e.reason));
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onReject);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onReject);
    };
  }, []);

  useEffect(() => {
    if (sysInfo) {
      console.log(
        `MoldGen v${sysInfo.version} | GPU: ${sysInfo.gpu.device_name} | VRAM: ${sysInfo.gpu.vram_total_mb}MB`,
      );
      if (sysInfo.gpu.available) {
        toastSuccess("GPU 已就绪", `${sysInfo.gpu.device_name} (${sysInfo.gpu.vram_total_mb}MB)`);
      } else {
        toastWarning("GPU 不可用", "将使用 CPU 模式运行");
      }
    }
  }, [sysInfo]);

  return (
    <ErrorBoundary>
      <div className="h-screen flex flex-col bg-bg-primary">
        {/* Title Bar */}
        <div className="flex items-center h-9 px-3 bg-bg-secondary border-b border-border select-none shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-accent">MoldGen</span>
            <span className="text-[10px] text-text-muted">
              AI 医学教具模具工作站
            </span>
            <div
              className={`w-1.5 h-1.5 rounded-full ml-1 ${
                backendStatus === "online"
                  ? "bg-green-400"
                  : backendStatus === "checking"
                    ? "bg-yellow-400 animate-pulse"
                    : "bg-red-400"
              }`}
              title={`后端: ${backendStatus === "online" ? "在线" : backendStatus === "checking" ? "检测中" : "离线"}`}
            />
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-1">
            <button
              onClick={toggleConsole}
              className={`p-1 rounded hover:bg-bg-hover ${consoleOpen ? "text-accent" : "text-text-muted"}`}
              title="控制台 (Ctrl+`)"
            >
              <Terminal size={14} />
            </button>
            <button
              onClick={toggleSettings}
              className="p-1 rounded hover:bg-bg-hover text-text-muted"
              title="设置 (Ctrl+,)"
            >
              <Settings size={14} />
            </button>
            {!leftPanelOpen && (
              <button
                onClick={toggleLeftPanel}
                className="p-1 rounded hover:bg-bg-hover text-text-muted"
                title="显示参数面板"
              >
                <PanelLeftOpen size={14} />
              </button>
            )}
            {!rightPanelOpen && (
              <button
                onClick={toggleRightPanel}
                className="p-1 rounded hover:bg-bg-hover text-text-muted"
                title="显示信息面板"
              >
                <PanelRightOpen size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Workflow Pipeline */}
        <WorkflowPipeline />

        {/* Main Content */}
        <div className="flex-1 flex min-h-0">
          <LeftPanel />
          <div className="flex-1 flex flex-col min-w-0">
            <StepToolbarOverlay />
            <Viewport />
          </div>
          <RightPanel />
        </div>

        {/* Console Panel */}
        {consoleOpen && <ConsolePanel />}

        {/* Status Bar */}
        <StatusBar />

        {/* AI Chat Bubble */}
        <ChatBubble />

        {/* Agent Workstation */}
        <AgentWorkstation />

        {/* Settings Dialog */}
        <SettingsDialog />

        {/* Toast Notifications */}
        <ToastContainer />

        {/* Update Notification */}
        <UpdateNotification />
      </div>
    </ErrorBoundary>
  );
}
