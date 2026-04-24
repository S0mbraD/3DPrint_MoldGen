import { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Download,
  RefreshCw,
  CheckCircle,
  Loader2,
  AlertCircle,
  ArrowUpCircle,
  X,
} from "lucide-react";
import { cn } from "../../lib/utils";

interface UpdateInfo {
  available: boolean;
  version?: string;
  date?: string;
  body?: string;
}

interface DownloadProgress {
  total: number;
  downloaded: number;
  percent: number;
}

type UpdateStatus =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "installing"
  | "up-to-date"
  | "error";

export function UpdateChecker() {
  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [progress, setProgress] = useState<DownloadProgress>({ total: 0, downloaded: 0, percent: 0 });
  const [error, setError] = useState<string | null>(null);

  const checkForUpdate = useCallback(async () => {
    setStatus("checking");
    setError(null);

    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();

      if (update) {
        setUpdateInfo({
          available: true,
          version: update.version,
          date: update.date ?? undefined,
          body: update.body ?? undefined,
        });
        setStatus("available");
      } else {
        setUpdateInfo({ available: false });
        setStatus("up-to-date");
      }
    } catch (e) {
      setError(String(e));
      setStatus("error");
    }
  }, []);

  const downloadAndInstall = useCallback(async () => {
    setStatus("downloading");
    setProgress({ total: 0, downloaded: 0, percent: 0 });

    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (!update) return;

      let downloaded = 0;
      await update.downloadAndInstall((event) => {
        switch (event.event) {
          case "Started":
            setProgress({ total: event.data.contentLength ?? 0, downloaded: 0, percent: 0 });
            break;
          case "Progress":
            downloaded += event.data.chunkLength;
            setProgress((prev) => ({
              total: prev.total,
              downloaded,
              percent: prev.total > 0 ? Math.round((downloaded / prev.total) * 100) : 0,
            }));
            break;
          case "Finished":
            setProgress((prev) => ({ ...prev, percent: 100 }));
            setStatus("installing");
            break;
        }
      });

      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch (e) {
      setError(String(e));
      setStatus("error");
    }
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ArrowUpCircle size={14} className="text-accent" />
          <span className="text-[11px] font-semibold text-text-secondary">应用更新</span>
        </div>
        <button
          onClick={checkForUpdate}
          disabled={status === "checking" || status === "downloading"}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] transition-colors",
            status === "checking"
              ? "text-text-muted cursor-wait"
              : "text-accent hover:bg-accent/10 border border-accent/30",
          )}
        >
          {status === "checking" ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <RefreshCw size={11} />
          )}
          检查更新
        </button>
      </div>

      <AnimatePresence mode="wait">
        {status === "up-to-date" && (
          <motion.div
            key="up-to-date"
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 p-2.5 rounded-lg bg-green-500/10 text-green-400"
          >
            <CheckCircle size={14} />
            <span className="text-[11px]">当前已是最新版本</span>
          </motion.div>
        )}

        {status === "available" && updateInfo && (
          <motion.div
            key="available"
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="p-3 rounded-lg border border-accent/30 bg-accent/5 space-y-2"
          >
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-accent">
                发现新版本: v{updateInfo.version}
              </span>
              {updateInfo.date && (
                <span className="text-[12px] text-text-muted">
                  {new Date(updateInfo.date).toLocaleDateString("zh-CN")}
                </span>
              )}
            </div>
            {updateInfo.body && (
              <p className="text-[12px] text-text-secondary leading-relaxed max-h-20 overflow-y-auto">
                {updateInfo.body}
              </p>
            )}
            <button
              onClick={downloadAndInstall}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-accent text-white text-[11px] hover:bg-accent-hover transition-colors"
            >
              <Download size={12} />
              下载并安装更新
            </button>
          </motion.div>
        )}

        {status === "downloading" && (
          <motion.div
            key="downloading"
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="p-3 rounded-lg bg-bg-secondary space-y-2"
          >
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-text-secondary">下载更新中...</span>
              <span className="text-text-muted font-mono">{progress.percent}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-bg-primary overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-accent"
                initial={{ width: 0 }}
                animate={{ width: `${progress.percent}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
            {progress.total > 0 && (
              <span className="text-[12px] text-text-muted">
                {(progress.downloaded / 1024 / 1024).toFixed(1)} / {(progress.total / 1024 / 1024).toFixed(1)} MB
              </span>
            )}
          </motion.div>
        )}

        {status === "installing" && (
          <motion.div
            key="installing"
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 p-2.5 rounded-lg bg-accent/10 text-accent"
          >
            <Loader2 size={14} className="animate-spin" />
            <span className="text-[11px]">正在安装更新，应用将自动重启...</span>
          </motion.div>
        )}

        {status === "error" && error && (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex items-start gap-2 p-2.5 rounded-lg bg-red-500/10 text-red-400"
          >
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <div className="flex-1">
              <span className="text-[11px]">更新检查失败</span>
              <p className="text-[12px] opacity-75 mt-0.5">{error.slice(0, 150)}</p>
            </div>
            <button onClick={() => setStatus("idle")} className="shrink-0">
              <X size={12} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function UpdateNotification() {
  const [show, setShow] = useState(false);
  const [version, setVersion] = useState("");

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const { check } = await import("@tauri-apps/plugin-updater");
        const update = await check();
        if (update) {
          setVersion(update.version);
          setShow(true);
        }
      } catch {
        // updater not available (dev mode or web)
      }
    }, 10000);
    return () => clearTimeout(timer);
  }, []);

  if (!show) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.95 }}
        className="fixed bottom-20 right-4 z-50 bg-bg-panel border border-accent/30 rounded-lg shadow-lg p-3 max-w-[280px]"
      >
        <div className="flex items-start gap-2">
          <ArrowUpCircle size={16} className="text-accent mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="text-[11px] font-semibold text-text-primary">发现新版本 v{version}</p>
            <p className="text-[12px] text-text-muted mt-0.5">请前往 设置 → 关于 查看更新</p>
          </div>
          <button
            onClick={() => setShow(false)}
            className="text-text-muted hover:text-text-primary shrink-0"
          >
            <X size={12} />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
