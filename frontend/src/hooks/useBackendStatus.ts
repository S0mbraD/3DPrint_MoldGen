import { useEffect, useState, useCallback } from "react";
import { useAppStore } from "../stores/appStore";
import type { BackendConnStatus } from "../stores/appStore";

export type BackendStatus = BackendConnStatus;

export function useBackendStatus(pollInterval = 10_000) {
  const [status, setStatus] = useState<BackendStatus>("checking");
  const [readiness, setReadiness] = useState<Record<string, unknown> | null>(null);
  const setBackendStatus = useAppStore((s) => s.setBackendStatus);

  const check = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/system/readiness", { signal: AbortSignal.timeout(5000) });
      if (res.ok) {
        setStatus("online");
        setBackendStatus("online");
        setReadiness(await res.json());
      } else {
        setStatus("offline");
        setBackendStatus("offline");
        setReadiness(null);
      }
    } catch {
      setStatus("offline");
      setBackendStatus("offline");
      setReadiness(null);
    }
  }, [setBackendStatus]);

  useEffect(() => {
    check();
    const timer = setInterval(check, pollInterval);
    return () => clearInterval(timer);
  }, [check, pollInterval]);

  return { status, readiness, check };
}
