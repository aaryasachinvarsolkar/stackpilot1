"use client";

import React, { useMemo, useState } from "react";
import { AlertTriangle, Check, Copy, Download, FilePlus2, ShieldCheck, X } from "lucide-react";
import { buildChanges, buildHunks, unifiedPatch, SCENARIO, LAYER_BY_ID, IMPACT_ITEMS } from "@/lib/sampleScenario";

// SAMPLE preview: before/after text is generated from lib/sampleScenario.ts. Nothing is ever written to disk.

interface ModificationPreviewProps {
  scenarioSelected: boolean;
  onGoToImpact: () => void;
}

export function ModificationPreview({ scenarioSelected, onGoToImpact }: ModificationPreviewProps) {
  const changes = useMemo(() => buildChanges(), []);
  const patch = useMemo(() => unifiedPatch(changes), [changes]);
  const [activePath, setActivePath] = useState(changes[0].path);
  const [showPatch, setShowPatch] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!scenarioSelected) {
    return (
      <div className="h-full flex items-center justify-center p-8" data-testid="preview-needs-scenario">
        <div className="max-w-md text-center space-y-3">
          <ShieldCheck className="h-8 w-8 text-slate-500 mx-auto" />
          <h3 className="text-base font-bold text-white">Select a change first</h3>
          <p className="text-xs text-slate-400 leading-relaxed">The modification preview is built from a reviewed impact report. Choose the example change in Impact Analysis first.</p>
          <button onClick={onGoToImpact} className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs">Go to Impact Analysis</button>
        </div>
      </div>
    );
  }

  const active = changes.find((c) => c.path === activePath) ?? changes[0];
  const hunks = buildHunks(active);
  const reviewOnly = !active.isNew && hunks.length === 0;
  const impactItem = IMPACT_ITEMS.find((i) => i.file === active.path);
  const editedCount = changes.filter((c) => !c.isNew && c.changedLines > 0).length;
  const newCount = changes.filter((c) => c.isNew).length;
  const reviewOnlyCount = changes.filter((c) => !c.isNew && c.changedLines === 0).length;

  const copyPatch = async () => {
    try {
      await navigator.clipboard.writeText(patch);
      setCopied(true);
    } catch {
      setShowPatch(true); // clipboard unavailable: show the text so it can be selected and copied manually
    }
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadPatch = () => {
    const url = URL.createObjectURL(new Blob([patch], { type: "text/x-diff" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "orders-platform-rename-customer-id.sample.patch";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full flex flex-col min-h-0" data-testid="preview-root">
      <div className="shrink-0 px-4 py-2.5 border-b border-slate-800 bg-[#090d16] flex flex-wrap items-center gap-3 text-xs">
        <span className="px-2.5 py-1 rounded-full bg-amber-500/15 border border-amber-400/40 text-amber-200 font-semibold" data-testid="preview-chip">
          PREVIEW ONLY · 0 files written
        </span>
        <span className="px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-400/40 text-violet-200 text-[10px] font-semibold">SAMPLE PROJECT</span>
        <span className="text-slate-400" data-testid="preview-summary">{SCENARIO.title}: {editedCount} files edited, {newCount} new file, {reviewOnlyCount} review-only</span>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => setShowPatch((v) => !v)} data-testid="toggle-patch" className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200">{showPatch ? "Hide" : "Show"} unified patch</button>
          <button onClick={copyPatch} data-testid="copy-patch" className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 flex items-center gap-1.5">
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />} {copied ? "Copied" : "Copy patch"}
          </button>
          <button onClick={downloadPatch} data-testid="download-patch" className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 flex items-center gap-1.5"><Download className="h-3.5 w-3.5" /> Download .patch</button>
          <button onClick={() => setConfirmOpen(true)} data-testid="apply-changes" className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold">Apply changes…</button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex">
        <div className="w-72 shrink-0 border-r border-slate-800 bg-[#0b101b] overflow-y-auto" data-testid="preview-files">
          {changes.map((c) => {
            const item = IMPACT_ITEMS.find((i) => i.file === c.path);
            const layer = item ? LAYER_BY_ID[item.layer] : LAYER_BY_ID.database;
            const none = !c.isNew && c.changedLines === 0;
            return (
              <button
                key={c.path}
                onClick={() => setActivePath(c.path)}
                data-testid="preview-file"
                data-path={c.path}
                className={`w-full text-left px-3 py-2 border-b border-slate-800/70 text-xs ${activePath === c.path ? "bg-indigo-600/15" : "hover:bg-slate-800/60"}`}
              >
                <div className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-sm shrink-0" style={{ background: layer.color }} />
                  <span className="font-mono text-[11px] text-slate-100 truncate">{c.path.split("/").slice(-2).join("/")}</span>
                  {c.isNew && <FilePlus2 className="h-3 w-3 text-emerald-400 shrink-0" />}
                </div>
                <div className="text-[10px] text-slate-500 truncate pl-3.5">{c.path}</div>
                <div className="text-[10px] pl-3.5 mt-0.5">{c.isNew ? <span className="text-emerald-400">new file</span> : none ? <span className="text-slate-500">review only, no edit</span> : <span className="text-amber-300">{c.changedLines} line{c.changedLines === 1 ? "" : "s"} changed</span>}</div>
              </button>
            );
          })}
        </div>

        <div className="flex-1 min-w-0 overflow-auto bg-[#070a12]">
          {showPatch ? (
            <pre className="p-4 text-[12px] leading-5 font-mono text-slate-200 whitespace-pre" data-testid="patch-text">{patch}</pre>
          ) : (
            <div className="p-4 space-y-3" data-testid="diff-view">
              <div>
                <div className="font-mono text-sm text-white break-all">{active.path}</div>
                {impactItem && <div className="mt-1 text-xs text-slate-400 leading-relaxed">{impactItem.why} <span className="text-slate-300">{impactItem.action}</span></div>}
              </div>
              {reviewOnly ? (
                <div className="p-4 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 leading-relaxed" data-testid="review-only">
                  No edit is proposed for this file. It was flagged <strong>indirect</strong>: it depends on a changed file but does not use the identifier. Review it manually.
                </div>
              ) : (
                hunks.map((h, hi) => (
                  <div key={hi} className="rounded-lg border border-slate-800 overflow-hidden" data-testid="hunk">
                    <div className="px-3 py-1 bg-slate-900 text-[11px] font-mono text-slate-500">@@ -{h.oldStart},{h.oldCount} +{h.newStart},{h.newCount} @@</div>
                    <div className="font-mono text-[12px] leading-5">
                      {h.lines.map((l, li) => (
                        <div key={li} data-testid={`diff-${l.t}`} className={`px-3 whitespace-pre ${l.t === "del" ? "bg-rose-950/40 text-rose-200" : l.t === "add" ? "bg-emerald-950/40 text-emerald-200" : "text-slate-400"}`}>
                          <span className="inline-block w-4 select-none opacity-70">{l.t === "del" ? "-" : l.t === "add" ? "+" : " "}</span>
                          {l.text || " "}
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {confirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" role="dialog" aria-modal="true" data-testid="apply-dialog">
          <div className="w-full max-w-md rounded-2xl bg-surface border border-slate-700 shadow-2xl p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2 text-white font-bold">
                <AlertTriangle className="h-5 w-5 text-amber-400" /> Applying changes is not available yet
              </div>
              <button onClick={() => setConfirmOpen(false)} aria-label="Close" className="text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              This prototype only <strong>previews</strong> a modification. It has no safe, verified way to edit files yet, so nothing has been or will be written to disk, and no project or database is touched.
            </p>
            <p className="text-xs text-slate-400 leading-relaxed">You can copy or download the patch above and review or apply it yourself.</p>
            <div className="flex justify-end gap-2">
              <button disabled data-testid="apply-confirm" className="px-4 py-2 rounded-xl bg-slate-800 text-slate-500 text-xs font-semibold cursor-not-allowed">Apply (not available yet)</button>
              <button onClick={() => setConfirmOpen(false)} data-testid="apply-close" className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold">Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
