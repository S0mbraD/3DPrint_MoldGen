import { useEffect } from "react";
import { Toolbar } from "./components/layout/Toolbar";
import { StatusBar } from "./components/layout/StatusBar";
import { LeftPanel } from "./components/layout/LeftPanel";
import { RightPanel } from "./components/layout/RightPanel";
import { Viewport } from "./components/viewer/Viewport";
import { ChatBubble } from "./components/ai/ChatBubble";
import { AgentWorkstation } from "./components/ai/AgentWorkstation";
import { SettingsDialog } from "./components/settings/SettingsDialog";
import { ToastContainer } from "./components/ui/ToastContainer";
import { useSystemInfo } from "./hooks/useSystemInfo";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { PanelLeftOpen, PanelRightOpen, Settings } from "lucide-react";
import { useAppStore } from "./stores/appStore";
import { toastSuccess, toastWarning } from "./stores/toastStore";

export default function App() {
  const { leftPanelOpen, rightPanelOpen, toggleLeftPanel, toggleRightPanel, toggleSettings } =
    useAppStore();
  const { data: sysInfo } = useSystemInfo();
  useKeyboardShortcuts();

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
    <div className="h-screen flex flex-col bg-bg-primary">
      {/* Title Bar */}
      <div className="flex items-center h-9 px-3 bg-bg-secondary border-b border-border select-none shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-accent">MoldGen</span>
          <span className="text-[10px] text-text-muted">
            AI 医学教具模具工作站
          </span>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1">
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

      {/* Toolbar */}
      <Toolbar />

      {/* Main Content */}
      <div className="flex-1 flex min-h-0">
        <LeftPanel />
        <Viewport />
        <RightPanel />
      </div>

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
    </div>
  );
}
