"use client";

import React from "react";
import { AlertTriangle, ArrowLeft, Check, FilePlus2, FileCode, RotateCw, Undo2 } from "lucide-react";
import type { ChangeFlow, ChangeStage } from "@/lib/useChangeFlow";
import { DiffView, RiskChip } from "@/components/ChangeParts";

interface ChangeAssistantProps {
  /** The shared flow (held by the workspace), so the Impact and Preview tabs show the same analysis and edits. */
  flow: ChangeFlow;
  /** False when no provider is configured or sending is not allowed; the reason is shown instead of a button that fails. */
  canSend: boolean;
  blockedReason?: string | null;
  onOpenFile: (file: string) => void;
}

export function ChangeAssistant({ flow, canSend, blockedReason, onOpenFile }: ChangeAssistantProps) {
  const {
    stage, setStage, request, setRequest, notes, setNotes, busy, error, impact, chosen, proposal, approved, applied, reverted,
    toggleChosen, toggleApproved, reset, runAnalyze, runPropose, runApply, runRevert,
  } = flow;

  const label = "text-[10px] font-bold uppercase tracking-wider text-slate-400";
  const primary =
    "px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed";
  const secondary = "px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold disabled:opacity-50";

  return (
    <div className="flex-1 flex flex-col p-3 space-y-3 overflow-y-auto" data-testid="change-assistant">
      {!canSend && (
        <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-400/30 text-amber-200 text-[11px] leading-snug" data-testid="change-blocked">
          Changes need a connected model. {blockedReason ?? "The AI provider is not available."}
        </div>
      )}

      {/* Step indicator */}
      <ol className="flex items-center gap-1 text-[10px] font-semibold text-slate-500">
        {(["describe", "impact", "review", "done"] as ChangeStage[]).map((s, i) => (
          <li key={s} className={`px-1.5 py-0.5 rounded ${stage === s ? "bg-indigo-600 text-white" : "bg-slate-900"}`}>
            {i + 1}. {{ describe: "Describe", impact: "Impact", review: "Review", done: "Done" }[s]}
          </li>
        ))}
      </ol>

      {error && (
        <div role="alert" className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-400/30 text-rose-200 text-[11px] leading-snug flex gap-2" data-testid="change-error">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {busy && (
        <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-2 text-indigo-300">
          <RotateCw className="h-3.5 w-3.5 animate-spin" />
          <span>{busy}</span>
        </div>
      )}

      {/* 1. Describe / adjust the idea */}
      {(stage === "describe" || stage === "impact") && (
        <section className="space-y-1.5">
          <label className={label} htmlFor="change-request">
            {stage === "describe" ? "What feature or change do you want?" : "Your idea (edit it, then re-plan)"}
          </label>
          <textarea
            id="change-request"
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            rows={4}
            placeholder="Say it simply, e.g. Add a dark mode toggle to the dashboard"
            className="w-full bg-slate-900 border border-slate-800 focus:border-indigo-500 outline-none rounded-lg p-2 text-xs text-white placeholder:text-slate-600 resize-y"
          />
          <button onClick={() => void runAnalyze()} disabled={!request.trim() || !!busy || !canSend} className={primary} data-testid="analyze-button">
            {stage === "describe" ? "Find files, impact and plan" : "Re-plan"}
          </button>
          <p className="text-[10px] text-slate-500 leading-snug">Nothing is changed in this step. Only matching excerpts of your files are sent to the model.</p>
        </section>
      )}

      {/* 2. Impact */}
      {stage === "impact" && impact && (
        <section className="space-y-3" data-testid="impact-result">
          {impact.status === "not_in_context" ? (
            <p className="text-slate-300 leading-relaxed">{impact.summary}</p>
          ) : (
            <>
              <div className="flex items-center gap-2">
                {impact.risk && <RiskChip risk={impact.risk} />}
                <span className="text-[10px] text-slate-500">based on {impact.excerpts_used} excerpts, not a full dependency scan</span>
              </div>
              {impact.summary && <p className="text-slate-200 leading-relaxed whitespace-pre-wrap">{impact.summary}</p>}
              {impact.risk_reasons.length > 0 && (
                <ul className="list-disc pl-4 space-y-0.5 text-slate-300">
                  {impact.risk_reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}

              <div className="space-y-1.5" data-testid="impact-plan">
                <div className={label}>Plan: tick the steps you approve</div>
                {impact.plan.length === 0 && (
                  <p className="text-slate-500">No safe step could be planned. Describe it with more detail (name a page, function or file) and re-plan.</p>
                )}
                {impact.plan.map((st) => (
                  <label key={st.path} className="flex gap-2 p-2 rounded-lg border border-slate-800 bg-slate-900/60 cursor-pointer" data-testid="plan-step">
                    <input type="checkbox" checked={chosen.has(st.path)} onChange={() => toggleChosen(st.path)} className="mt-0.5" />
                    <span className="min-w-0 space-y-0.5">
                      <span className="flex items-center gap-1.5 flex-wrap">
                        <span className={`px-1.5 rounded-full text-[9px] border font-semibold ${st.action === "create" ? "border-emerald-400/40 text-emerald-200" : "border-sky-400/40 text-sky-200"}`}>
                          {st.action === "create" ? "new file" : "edit"}
                        </span>
                        <span className="font-mono text-[11px] text-slate-100 break-all">{st.path}</span>
                      </span>
                      <span className="block text-slate-400 leading-snug">{st.what}</span>
                    </span>
                  </label>
                ))}
                {impact.skipped_steps.length > 0 && (
                  <details className="text-[10px] text-slate-500">
                    <summary className="cursor-pointer">{impact.skipped_steps.length} suggested step(s) were dropped as unsafe or invalid</summary>
                    <ul className="list-disc pl-4 mt-1 space-y-0.5">
                      {impact.skipped_steps.map((sk, i) => (
                        <li key={i}>
                          <span className="font-mono">{sk.path}</span>: {sk.reason}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>

              {impact.affected_files.length > 0 && (
                <div className="space-y-1.5" data-testid="impact-files">
                  <div className={label}>Existing files this touches</div>
                  {impact.affected_files.map((f) => (
                    <div key={f.path} className="p-2 rounded-lg border border-slate-800/80 space-y-0.5" data-testid="impact-file">
                      <span className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-mono text-[11px] text-slate-100 break-all">{f.path}</span>
                        <span className={`px-1.5 rounded-full text-[9px] border ${f.category === "direct" ? "border-sky-400/40 text-sky-200" : "border-slate-600 text-slate-300"}`}>{f.category}</span>
                      </span>
                      <span className="block text-slate-400 leading-snug">{f.why}</span>
                      {!f.editable && f.not_editable_reason && <span className="block text-amber-300/80">{f.not_editable_reason}</span>}
                    </div>
                  ))}
                </div>
              )}

              {impact.questions.length > 0 && (
                <div className="space-y-1">
                  <div className={label}>Decide before changing</div>
                  <ul className="list-disc pl-4 space-y-0.5 text-slate-300">
                    {impact.questions.map((q) => (
                      <li key={q}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="space-y-1.5">
                <label className={label} htmlFor="change-notes">Change the plan? Tell it here (optional)</label>
                <textarea
                  id="change-notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                  placeholder="e.g. Use a button in the navbar and remember the choice"
                  className="w-full bg-slate-900 border border-slate-800 focus:border-indigo-500 outline-none rounded-lg p-2 text-xs text-white placeholder:text-slate-600 resize-y"
                />
                <button onClick={() => void runPropose()} disabled={chosen.size === 0 || !!busy || !canSend} className={primary} data-testid="propose-button">
                  Approve plan and prepare {chosen.size} file{chosen.size === 1 ? "" : "s"}
                </button>
                <p className="text-[10px] text-slate-500 leading-snug">Still nothing is written. You review every edit first.</p>
              </div>
            </>
          )}
        </section>
      )}

      {/* 3. Review the exact edits */}
      {stage === "review" && proposal && (
        <section className="space-y-3" data-testid="review-result">
          {proposal.summary && <p className="text-slate-200 leading-relaxed whitespace-pre-wrap">{proposal.summary}</p>}
          {proposal.files.map((f) => (
            <div key={f.path} className="rounded-lg border border-slate-800 overflow-hidden" data-testid="proposed-file">
              <label className="flex items-center gap-2 px-2 py-1.5 bg-slate-900 cursor-pointer">
                <input type="checkbox" checked={approved.has(f.path)} onChange={() => toggleApproved(f.path)} />
                {f.is_new && (
                  <span className="inline-flex items-center gap-0.5 px-1.5 rounded-full text-[9px] border border-emerald-400/40 text-emerald-200">
                    <FilePlus2 className="h-2.5 w-2.5" /> new
                  </span>
                )}
                <span className="font-mono text-[11px] text-slate-100 break-all flex-1">{f.path}</span>
                <span className="text-emerald-400 font-mono text-[10px]">+{f.added}</span>
                <span className="text-rose-400 font-mono text-[10px]">-{f.removed}</span>
              </label>
              {f.explanation && <p className="px-2 py-1 text-slate-400 leading-snug">{f.explanation}</p>}
              <DiffView diff={f.diff} />
            </div>
          ))}
          {proposal.rejected.length > 0 && (
            <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-400/30 text-amber-200 space-y-1">
              <div className="font-semibold">No safe edit could be made for:</div>
              {proposal.rejected.map((r) => (
                <div key={r.path}><span className="font-mono">{r.path}</span>: {r.reason}</div>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={() => void runApply()} disabled={approved.size === 0 || !!busy} className={primary} data-testid="apply-button">
              Apply {approved.size} approved file{approved.size === 1 ? "" : "s"}
            </button>
            <button onClick={() => setStage("impact")} disabled={!!busy} className={`${secondary} flex items-center gap-1`}>
              <ArrowLeft className="h-3 w-3" /> Adjust idea
            </button>
          </div>
          <p className="text-[10px] text-slate-500 leading-snug">Files are written only if they are unchanged since this suggestion. You can undo right after.</p>
        </section>
      )}

      {/* 4. Done */}
      {stage === "done" && (
        <section className="space-y-3" data-testid="done-result">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-400/30 text-emerald-200 flex gap-2">
            <Check className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>{reverted ? "The change was undone; the original files are back." : `Applied to ${applied.length} file${applied.length === 1 ? "" : "s"}.`}</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {applied.map((p) => (
              <button key={p} onClick={() => onOpenFile(p)} className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-slate-700 hover:border-indigo-400 font-mono text-[10px] text-slate-200">
                <FileCode className="h-2.5 w-2.5" /> {p}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            {!reverted && (
              <button onClick={() => void runRevert()} disabled={!!busy} className={`${secondary} flex items-center gap-1`} data-testid="revert-button">
                <Undo2 className="h-3 w-3" /> Undo this change
              </button>
            )}
            <button onClick={reset} disabled={!!busy} className={primary}>New change</button>
          </div>
        </section>
      )}
    </div>
  );
}
