"use client";

import React from "react";
import { ShieldAlert } from "lucide-react";

export const RISK_CLASS: Record<string, string> = {
  high: "bg-rose-500/15 border-rose-400/40 text-rose-200",
  medium: "bg-amber-500/15 border-amber-400/40 text-amber-200",
  low: "bg-emerald-500/15 border-emerald-400/40 text-emerald-200",
};

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-slate-500";
  if (line.startsWith("@@")) return "text-cyan-400";
  if (line.startsWith("+")) return "bg-emerald-500/10 text-emerald-300";
  if (line.startsWith("-")) return "bg-rose-500/10 text-rose-300";
  return "text-slate-400";
}

/** A unified diff, coloured per line. The text is shown as plain text, never as HTML. */
export function DiffView({ diff, maxHeight = "max-h-64" }: { diff: string; maxHeight?: string }) {
  return (
    <pre className={`px-2 py-1.5 overflow-x-auto text-[10px] leading-snug font-mono bg-[#080c14] select-text overflow-y-auto ${maxHeight}`} data-testid="diff-view">
      {diff.split("\n").map((line, i) => (
        <div key={i} className={diffLineClass(line)}>
          {line || " "}
        </div>
      ))}
    </pre>
  );
}

export function RiskChip({ risk }: { risk: "low" | "medium" | "high" }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase ${RISK_CLASS[risk]}`} data-testid="impact-risk">
      <ShieldAlert className="h-3 w-3" /> {risk} risk
    </span>
  );
}
