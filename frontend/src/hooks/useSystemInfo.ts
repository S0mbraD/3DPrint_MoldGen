import { useQuery } from "@tanstack/react-query";
import { useAppStore } from "../stores/appStore";
import { useEffect } from "react";

interface SystemInfo {
  version: string;
  gpu: {
    available: boolean;
    device_name: string;
    vram_total_mb: number;
    vram_used_mb: number;
    vram_free_mb: number;
    compute_capability: string;
    cuda_version: string;
    driver_version: string;
    numba_cuda: boolean;
    cupy: boolean;
  };
}

export function useSystemInfo() {
  const setGpu = useAppStore((s) => s.setGpu);

  const query = useQuery<SystemInfo>({
    queryKey: ["system-info"],
    queryFn: async () => {
      const res = await fetch("/api/v1/system/info");
      if (!res.ok) throw new Error("Failed to fetch system info");
      return res.json();
    },
    staleTime: 30_000,
  });

  useEffect(() => {
    if (query.data?.gpu) {
      setGpu(query.data.gpu);
    }
  }, [query.data, setGpu]);

  return query;
}
