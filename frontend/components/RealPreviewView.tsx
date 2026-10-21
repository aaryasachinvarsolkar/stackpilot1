"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, Check, FilePlus2, RotateCw, ShieldCheck, Undo2 } from "lucide-react";
import type { ChangeFlow } from "@/lib/useChangeFlow";
import { DiffView } from "@/components/ChangeParts";

interface RealPreviewViewProps {
  flow: ChangeFlow;
  onOpenFile: (path: string) => void;
  onGoToImpact: () => void;
}

/** The exact edits prepared for a REAL project, file by file. Nothing is written until the user applies the ticked files. */
export function RealPreviewView({ flow, onOpenFile, onGoToImpact }: RealPreviewViewProps) {
  const { proposal, stage, approved, toggleApproved, busy, error, applied, reverted, runApply, runRevert, reset } = flow;
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    setActive(proposal?.files[0]?.path ?? null);
  }, [proposal]);

  if (!proposal) {
    return (
      <div className="h-full flex items-center justify-center p-8" data-testid="preview-needs-plan">
        <div className="max-w-md text-center space-y-3">
          <ShieldCheck className="h-8 w-8 text-slate-500 mx-auto" />
          <h3 className="text-base font-bold text-white">No edits prepared yet</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            The preview is built from an approved plan. Describe a change in Impact Analysis, approve the plan steps, and the exact edits appear here for review.
          </p>
          {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
          <button onClick={onGoToImpact} className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs" data-testid="preview-go-impact">
            Go to Impact Analysis
          </button>
        </div>
      </div>
    );
  }

  const file = proposal.files.find((f) => f.path === active) ?? proposal.files[0];
  const done = stage === "done";
  const totalAdded = proposal.files.reduce((n, f) => n + f.added, 0);
  const totalRemoved = proposal.files.reduce((n, f) => n + f.removed, 0);

  return (
    <div className="h-full flex flex-col min-h-0 text-xs" data-testid="real-preview">
      <div className="shrink-0 px-6 py-3 border-b border-slate-800 space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-bold text-white">{proposal.files.length} file{proposal.files.length === 1 ? "" : "s"} prepared</span>
          <span className="font-mono text-emerald-400">+{totalAdded}</span>
          <span className="font-mono text-rose-400">-{totalRemoved}</span>
          <span className="text-slate-500">
            {done ? (reverted ? "Undone: the original files are back." : "Applied to disk.") : "Not applied yet: this is only a preview."}
          </span>
        </div>
        {proposal.summary && <p className="text-slate-400 leading-relaxed">{proposal.summary}</p>}
        {error && (
          <div role="alert" className="flex gap-2 p-2.5 rounded-lg bg-rose-500/10 border border-rose-400/30 text-rose-200" data-testid="preview-error">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        {busy && (
          <div className="flex items-center gap-2 text-indigo-300">
            <RotateCw className="h-4 w-4 animate-spin" />
            <span>{busy}</span>
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 flex">
        <aside className="w-72 shrink-0 border-r border-slate-800 overflow-y-auto p-2 space-y-1" data-testid="preview-files">
          {proposal.files.map((f) => (
            <div
              key={f.path}
              className={`flex items-start gap-2 p-2 rounded-lg border cursor-pointer ${f.path === file?.path ? "border-indigo-400/60 bg-indigo-600/10" : "border-slate-800 hover:border-slate-600"}`}
              onClick={() => setActive(f.path)}
              data-testid="preview-file"
            >
              {!done && (
                <input
                  type="checkbox"
                  checked={approved.has(f.path)}
                  onChange={() => toggleApproved(f.path)}
                  onClick={(e) => e.stopPropagation()}
                  className="mt-0.5"
                  aria-label={`Approve ${f.path}`}
                />
              )}
              <span className="min-w-0 flex-1">
                <span className="block font-mono text-[11px] text-slate-100 break-all">{f.path}</span>
                <span className="flex items-center gap-2 mt-0.5">
                  {f.is_new && (
                    <span className="inline-flex items-center gap-0.5 px-1.5 rounded-full text-[9px] border border-emerald-400/40 text-emerald-200">
                      <FilePlus2 className="h-2.5 w-2.5" /> new
                    </span>
                  )}
                  <span className="font-mono text-[10px] text-emerald-400">+{f.added}</span>
                  <span className="font-mono text-[10px] text-rose-400">-{f.removed}</span>
                </span>
              </span>
            </div>
          ))}
          {proposal.rejected.length > 0 && (
            <div className="mt-2 p-2 rounded-lg bg-amber-500/10 border border-amber-400/30 text-amber-200 space-y-1" data-testid="preview-rejected">
              <div className="font-semibold">No safe edit could be made for:</div>
              {proposal.rejected.map((r) => (
                <div key={r.path} className="leading-snug">
                  <span className="font-mono">{r.path}</span>: {r.reason}
                </div>
              ))}
            </div>
          )}
        </aside>

        <section className="flex-1 min-w-0 flex flex-col min-h-0">
          {file && (
            <>
              <div className="shrink-0 px-4 py-2 border-b border-slate-800 flex items-center gap-3">
                <button onClick={() => onOpenFile(file.path)} className="font-mono text-[11px] text-slate-100 hover:text-indigo-300 break-all text-left" title="Open in the editor">
                  {file.path}
                </button>
                {file.explanation && <span className="text-slate-400 truncate">{file.explanation}</span>}
              </div>
              <div className="flex-1 min-h-0 overflow-auto">
                <DiffView diff={file.diff} maxHeight="max-h-none" />
              </div>
            </>
          )}
        </section>
      </div>

      <div className="shrink-0 px-6 py-3 border-t border-slate-800 flex flex-wrap items-center gap-2">
        {!done && (
          <>
            <button
              onClick={() => void runApply()}
              disabled={approved.size === 0 || !!busy}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-2 disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed"
              data-testid="preview-apply"
            >
              <Check className="h-4 w-4" /> Apply {approved.size} approved file{approved.size === 1 ? "" : "s"}
            </button>
            <button onClick={onGoToImpact} disabled={!!busy} className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold disabled:opacity-50">
              Adjust the plan
            </button>
            <span className="text-slate-500">Files are written only if they are unchanged since this preview. You can undo right after.</span>
          </>
        )}
        {done && (
          <>
            {!reverted && (
              <button onClick={() => void runRevert()} disabled={!!busy} className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold flex items-center gap-2 disabled:opacity-50" data-testid="preview-revert">
                <Undo2 className="h-4 w-4" /> Undo this change
              </button>
            )}
            {applied.map((p) => (
              <button key={p} onClick={() => onOpenFile(p)} className="px-2 py-1 rounded border border-slate-700 hover:border-indigo-400 font-mono text-[10px] text-slate-200">
                {p}
              </button>
            ))}
            <button onClick={() => { reset(); onGoToImpact(); }} disabled={!!busy} className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold ml-auto">
              New change
            </button>
          </>
        )}
      </div>
    </div>
  );
}
