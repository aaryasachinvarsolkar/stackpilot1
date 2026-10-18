"use client";

import { useEffect, useState } from "react";
import { fetchHealth, fetchSystemInfo, HealthResponse, InfoResponse } from "@/services/api";

export function useHealth(pollIntervalMs = 5000) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [info, setInfo] = useState<InfoResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadStatus() {
      const [h, i] = await Promise.all([fetchHealth(), fetchSystemInfo()]);
      if (isMounted) {
        setHealth(h);
        setInfo(i);
        setIsLoading(false);
      }
    }

    loadStatus();
    const interval = setInterval(loadStatus, pollIntervalMs);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [pollIntervalMs]);

  return { health, info, isLoading };
}
