import { create } from "zustand";

export type ToastType = "success" | "error" | "warning" | "info" | "loading";

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

interface ToastState {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, "id">) => string;
  removeToast: (id: string) => void;
  updateToast: (id: string, updates: Partial<Omit<Toast, "id">>) => void;
  clearAll: () => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],

  addToast: (toast) => {
    const id = crypto.randomUUID();
    set((s) => ({ toasts: [...s.toasts, { ...toast, id }] }));

    if (toast.type !== "loading") {
      const dur = toast.duration ?? (toast.type === "error" ? 6000 : 3500);
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
      }, dur);
    }

    return id;
  },

  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  updateToast: (id, updates) =>
    set((s) => ({
      toasts: s.toasts.map((t) => (t.id === id ? { ...t, ...updates } : t)),
    })),

  clearAll: () => set({ toasts: [] }),
}));

export function toast(type: ToastType, title: string, message?: string) {
  return useToastStore.getState().addToast({ type, title, message });
}

export function toastSuccess(title: string, message?: string) {
  return toast("success", title, message);
}

export function toastError(title: string, message?: string) {
  return toast("error", title, message);
}

export function toastWarning(title: string, message?: string) {
  return toast("warning", title, message);
}

export function toastInfo(title: string, message?: string) {
  return toast("info", title, message);
}

export function toastLoading(title: string, message?: string) {
  return toast("loading", title, message);
}
