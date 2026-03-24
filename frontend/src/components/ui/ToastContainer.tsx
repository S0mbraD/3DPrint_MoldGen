import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  Loader2,
  X,
} from "lucide-react";
import { useToastStore, type ToastType } from "../../stores/toastStore";
import { cn } from "../../lib/utils";

const ICON_MAP: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
  loading: Loader2,
};

const COLOR_MAP: Record<ToastType, string> = {
  success: "border-success/40 bg-success/10",
  error: "border-danger/40 bg-danger/10",
  warning: "border-warning/40 bg-warning/10",
  info: "border-accent/40 bg-accent/10",
  loading: "border-accent/40 bg-accent/10",
};

const ICON_COLOR_MAP: Record<ToastType, string> = {
  success: "text-success",
  error: "text-danger",
  warning: "text-warning",
  info: "text-accent",
  loading: "text-accent",
};

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  return (
    <div className="fixed top-14 right-4 z-[100] flex flex-col gap-2 pointer-events-none max-w-sm">
      <AnimatePresence mode="popLayout">
        {toasts.map((t) => {
          const Icon = ICON_MAP[t.type];
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, x: 80, scale: 0.9 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 80, scale: 0.9 }}
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
              className={cn(
                "pointer-events-auto flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border backdrop-blur-md shadow-xl",
                COLOR_MAP[t.type],
              )}
            >
              <Icon
                size={16}
                className={cn(
                  "shrink-0 mt-0.5",
                  ICON_COLOR_MAP[t.type],
                  t.type === "loading" && "animate-spin",
                )}
              />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-text-primary leading-tight">
                  {t.title}
                </p>
                {t.message && (
                  <p className="text-[10px] text-text-secondary mt-0.5 leading-snug">
                    {t.message}
                  </p>
                )}
              </div>
              {t.type !== "loading" && (
                <button
                  onClick={() => removeToast(t.id)}
                  className="p-0.5 rounded hover:bg-bg-hover text-text-muted shrink-0"
                >
                  <X size={12} />
                </button>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
