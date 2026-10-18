"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  label: string;
  status: "healthy" | "connected" | "degraded" | "unreachable" | "unknown" | string;
  subtext?: string;
}

export function StatusBadge({ label, status, subtext }: StatusBadgeProps) {
  const isHealthy = status === "healthy" || status === "connected";
  const isDegraded = status === "degraded";
  const isDown = status === "unreachable" || status === "unknown" || status === "error";

  return (
    <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-surface/80 border border-slate-800/80 backdrop-blur-md shadow-sm">
      <span className="relative flex h-2.5 w-2.5">
        {isHealthy && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={cn(
            "relative inline-flex rounded-full h-2.5 w-2.5",
            isHealthy && "bg-emerald-500",
            isDegraded && "bg-amber-500",
            isDown && "bg-rose-500"
          )}
        />
      </span>
      <div className="flex flex-col text-left">
        <span className="text-[11px] font-medium text-slate-400 leading-tight">{label}</span>
        <span
          className={cn(
            "text-xs font-semibold uppercase tracking-wider leading-tight",
            isHealthy && "text-emerald-400",
            isDegraded && "text-amber-400",
            isDown && "text-rose-400"
          )}
        >
          {status} {subtext ? `(${subtext})` : ""}
        </span>
      </div>
    </div>
  );
}
