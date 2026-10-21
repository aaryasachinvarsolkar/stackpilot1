"use client";

import React from "react";
import { AlertTriangle, Eye, FilePlus2, GitFork, RotateCw } from "lucide-react";
import type { ChangeFlow } from "@/lib/useChangeFlow";
import { RiskChip } from "@/components/ChangeParts";

interface RealImpactViewProps {
  flow: ChangeFlow;
  canSend: boolean;
  blockedReason?: string | null;
  onOpenFile: (path: string) => void;
  onShowGraph: () => void;
  onShowPreview: () => void;
}

const heading = "text-[11px] font-bold uppercase tracking-wider text-slate-400";

/** Impact analysis for a REAL project: the request is analysed against the project's own files by the backend. */
export function RealImpactView({ flow, canSend, blockedReason, onOpenFile, onShowGraph, onShowPreview }: RealImpactViewProps) {
  const { request, setRequest, notes, setNotes, busy, error, impact, chosen, proposal, stage, toggleChosen, runAnalyze, runPropose } = flow;

  const prepare = async () => {
    if (await runPropose()) onShowPreview();
  };

  return (
    <div className="h-full overflow-y-auto" data-testid="real-impact">
      <div className="max-w-5xl mx-auto px-6 py-6 space-y-6 text-xs">
        {!canSend && (
          <div className="flex items-start gap-3 p-3 rounded-lg bg-amber-500/10 border border-amber-400/30 text-amber-200 leading-relaxed" data-testid="impact-blocked">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>Impact analysis needs a connected model. {blockedReason ?? "The AI provider is not available."}</span>
          </div>
        )}

        <section className="space-y-2">
          <h2 className={heading}>1. Describe the feature or change</h2>
          <textarea
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            rows={3}
            placeholder="Say it simply, e.g. Add a dark mode toggle to the dashboard"
            className="w-full bg-slate-900 border border-slate-800 focus:border-indigo-500 outline-none rounded-lg p-3 text-xs text-white placeholder:text-slate-600 resize-y"
            data-testid="impact-request"
          />
          <div className="flex items-center gap-3">
            <button
              onClick={() => void runAnalyze()}
              disabled={!request.trim() || !!busy || !canSend}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed"
              data-testid="impact-analyze"
            >
              {impact ? "Re-analyze" : "Find files, impact and plan"}
            </button>
            <span className="text-slate-500">Nothing is changed in this step. Only matching excerpts of your files are sent to the model.</span>
          </div>
        </section>

        {error && (
          <div role="alert" className="flex gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-400/30 text-rose-200" data-testid="impact-error">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        {busy && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-indigo-300">
            <RotateCw className="h-4 w-4 animate-spin" />
            <span>{busy}</span>
          </div>
        )}

        {!impact && !busy && (
          <p className="text-slate-500 text-center py-8" data-testid="impact-empty">
            Describe a change above to see which files it touches, how risky it is and a step-by-step plan.
          </p>
        )}

        {impact && impact.status === "not_in_context" && <p className="text-slate-300">{impact.summary}</p>}

        {impact && impact.status === "analyzed" && (
          <div className="space-y-6" data-testid="impact-report">
            <section className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="impact-tiles">
              <div className="p-3 rounded-xl border border-slate-800 bg-surface/40">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">Overall risk</div>
                <div className="mt-1.5">{impact.risk ? <RiskChip risk={impact.risk} /> : <span className="text-slate-400">not stated</span>}</div>
              </div>
              <Tile label="Plan steps" value={String(impact.plan.length)} />
              <Tile label="Existing files affected" value={String(impact.affected_files.length)} />
              <Tile label="Open questions" value={String(impact.questions.length)} />
            </section>

            {impact.summary && (
              <section className="space-y-2">
                <h2 className={heading}>2. What this change involves</h2>
                <p className="text-slate-200 leading-relaxed whitespace-pre-wrap">{impact.summary}</p>
                <p className="text-[11px] text-slate-500">
                  Based on {impact.excerpts_used} matching excerpts of your files plus the file list, not a full dependency scan. Check the files below.
                </p>
              </section>
            )}

            {impact.risk_reasons.length > 0 && (
              <section className="space-y-2" data-testid="impact-risk-reasons">
                <h2 className={heading}>3. Why this risk level</h2>
                <ul className="list-disc pl-5 space-y-1 text-slate-300">
                  {impact.risk_reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </section>
            )}

            <section className="space-y-2" data-testid="impact-plan">
              <h2 className={heading}>4. Plan: tick the steps you approve</h2>
              {impact.plan.length === 0 && <p className="text-slate-500">No safe step could be planned. Name a page, function or file in your description and re-analyze.</p>}
              {impact.plan.map((st) => (
                <label key={st.path} className="flex gap-3 p-3 rounded-xl border border-slate-800 bg-slate-900/60 cursor-pointer" data-testid="plan-step">
                  <input type="checkbox" checked={chosen.has(st.path)} onChange={() => toggleChosen(st.path)} className="mt-0.5" />
                  <span className="min-w-0 space-y-1">
                    <span className="flex items-center gap-2 flex-wrap">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold ${st.action === "create" ? "border-emerald-400/40 text-emerald-200" : "border-sky-400/40 text-sky-200"}`}>
                        {st.action === "create" && <FilePlus2 className="h-3 w-3" />}
                        {st.action === "create" ? "new file" : "edit"}
                      </span>
                      <span className="font-mono text-[11px] text-slate-100 break-all">{st.path}</span>
                    </span>
                    <span className="block text-slate-400 leading-relaxed">{st.what}</span>
                  </span>
                </label>
              ))}
              {impact.skipped_steps.length > 0 && (
                <details className="text-[11px] text-slate-500">
                  <summary className="cursor-pointer">{impact.skipped_steps.length} suggested step(s) were dropped as unsafe or invalid</summary>
                  <ul className="list-disc pl-5 mt-1 space-y-0.5">
                    {impact.skipped_steps.map((sk, i) => (
                      <li key={i}>
                        <span className="font-mono">{sk.path}</span>: {sk.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </section>

            {impact.affected_files.length > 0 && (
              <section className="space-y-2" data-testid="impact-files">
                <h2 className={heading}>5. Existing files this touches</h2>
                <div className="rounded-xl border border-slate-800 divide-y divide-slate-800/80 overflow-hidden">
                  {impact.affected_files.map((f) => (
                    <div key={f.path} className="px-3 py-2.5 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1" data-testid="impact-file">
                      <button onClick={() => onOpenFile(f.path)} className="text-left font-mono text-[11px] text-slate-100 hover:text-indigo-300 break-all" title="Open in the editor">
                        {f.path}
                      </button>
                      <span className={`justify-self-end px-2 py-0.5 rounded-full border text-[10px] font-semibold ${f.category === "direct" ? "bg-sky-500/10 border-sky-400/40 text-sky-200" : "bg-slate-800 border-slate-600 text-slate-300"}`}>
                        {f.category}
                      </span>
                      <span className="col-span-2 text-slate-400 leading-relaxed">{f.why}</span>
                      {!f.editable && f.not_editable_reason && <span className="col-span-2 text-amber-300/80">{f.not_editable_reason}</span>}
                    </div>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500">&quot;Direct&quot; means the file must change itself. &quot;Indirect&quot; means it depends on something that changes.</p>
              </section>
            )}

            {impact.questions.length > 0 && (
              <section className="space-y-2" data-testid="impact-questions">
                <h2 className={heading}>6. Decide before changing</h2>
                <ul className="list-disc pl-5 space-y-1 text-slate-300">
                  {impact.questions.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </section>
            )}

            <section className="space-y-2">
              <h2 className={heading}>7. Change the plan? Tell it here (optional)</h2>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder="e.g. Use a button in the navbar and remember the choice"
                className="w-full bg-slate-900 border border-slate-800 focus:border-indigo-500 outline-none rounded-lg p-3 text-xs text-white placeholder:text-slate-600 resize-y"
              />
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  onClick={() => void prepare()}
                  disabled={chosen.size === 0 || !!busy || !canSend}
                  className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-2 disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed"
                  data-testid="impact-prepare"
                >
                  <Eye className="h-4 w-4" /> Approve plan and preview the modification ({chosen.size})
                </button>
                <button onClick={onShowGraph} className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold flex items-center gap-2">
                  <GitFork className="h-4 w-4 text-indigo-300" /> Dependency graph
                </button>
                {proposal && stage !== "impact" && (
                  <button onClick={onShowPreview} className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-emerald-200 font-semibold" data-testid="impact-go-preview">
                    Edits already prepared: open the preview
                  </button>
                )}
              </div>
              <p className="text-[11px] text-slate-500">Still nothing is written. You review every edit in the Modification Preview first.</p>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-3 rounded-xl border border-slate-800 bg-surface/40">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-bold text-white">{value}</div>
    </div>
  );
}
