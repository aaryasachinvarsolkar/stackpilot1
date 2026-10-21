"use client";

import React from "react";
import { AlertTriangle, ArrowRight, Database, FilePlus2, GitFork, ShieldAlert, Eye } from "lucide-react";
import { IMPACT_ITEMS, LAYERS, LAYER_BY_ID, SCENARIO, type RiskLevel } from "@/lib/sampleScenario";

// SAMPLE scenario: deterministic results from lib/sampleScenario.ts. No scan, analyzer or AI model ran.

const RISK_STYLE: Record<RiskLevel, string> = {
  high: "bg-rose-500/15 border-rose-400/40 text-rose-200",
  medium: "bg-amber-500/15 border-amber-400/40 text-amber-200",
  low: "bg-emerald-500/15 border-emerald-400/40 text-emerald-200",
};

interface ImpactAnalysisProps {
  selected: boolean;
  onSelect: (v: boolean) => void;
  onShowGraph: () => void;
  onShowPreview: () => void;
}

export function ImpactAnalysis({ selected, onSelect, onShowGraph, onShowPreview }: ImpactAnalysisProps) {
  const direct = IMPACT_ITEMS.filter((i) => i.category === "direct").length;
  const indirect = IMPACT_ITEMS.length - direct;
  const layersAffected = new Set(IMPACT_ITEMS.map((i) => i.layer)).size;

  return (
    <div className="h-full overflow-y-auto" data-testid="impact-root">
      <div className="max-w-5xl mx-auto px-6 py-6 space-y-6 text-xs">
        <div className="flex items-start gap-3 p-3 rounded-lg bg-violet-500/10 border border-violet-400/30 text-violet-100 leading-relaxed" data-testid="impact-sample-banner">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-violet-300" />
          <span>
            <strong>Sample scenario.</strong> These results are deterministic sample data for the orders-platform demo. No repository was scanned, and no static analyzer or AI model ran.
          </span>
        </div>

        <section className="space-y-2">
          <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">1. Choose an example change</h2>
          <button
            onClick={() => onSelect(!selected)}
            data-testid="scenario-card"
            aria-pressed={selected}
            className={`w-full text-left p-4 rounded-xl border transition-colors flex items-start gap-3 ${
              selected ? "bg-indigo-600/15 border-indigo-400/60" : "bg-surface/40 border-slate-800 hover:border-indigo-500/50"
            }`}
          >
            <Database className="h-5 w-5 text-pink-400 shrink-0 mt-0.5" />
            <span className="flex-1">
              <span className="block text-sm font-bold text-white">{SCENARIO.title}</span>
              <span className="block mt-1 text-slate-400 leading-relaxed">{SCENARIO.summary}</span>
            </span>
            <span className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold ${selected ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-300"}`}>
              {selected ? "Selected" : "Analyze this change"}
            </span>
          </button>
        </section>

        {!selected ? (
          <p className="text-slate-500 text-center py-10" data-testid="impact-empty">
            Select the example change to see which layers, files and tests it affects.
          </p>
        ) : (
          <div className="space-y-6" data-testid="impact-report">
            <section className="space-y-2">
              <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">2. Proposed change</h2>
              <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 font-mono text-[12px] text-slate-200">
                <span className="text-slate-500">orders.</span>
                <span className="text-rose-300 line-through">{SCENARIO.from}</span>
                <ArrowRight className="inline h-3.5 w-3.5 mx-2 text-slate-500" />
                <span className="text-emerald-300">orders.{SCENARIO.to}</span>
              </div>
            </section>

            <section className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="impact-tiles">
              <Tile label="Overall risk" value={SCENARIO.overallRisk.toUpperCase()} tone="risk" />
              <Tile label="Layers affected" value={`${layersAffected} of ${LAYERS.length}`} />
              <Tile label="Files to review" value={`${IMPACT_ITEMS.length} + 1 new`} />
              <Tile label="Direct / indirect" value={`${direct} / ${indirect}`} />
            </section>

            <section className="space-y-2">
              <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">3. Why these are affected: dependency path</h2>
              <div className="flex flex-wrap items-center gap-1.5" data-testid="impact-path">
                {SCENARIO.path.map((step, i) => (
                  <React.Fragment key={step}>
                    <span className={`px-2 py-1 rounded-md font-mono text-[11px] border ${i === 0 ? "bg-rose-500/15 border-rose-400/40 text-rose-100" : "bg-slate-900 border-slate-800 text-slate-200"}`}>{step}</span>
                    {i < SCENARIO.path.length - 1 && <ArrowRight className="h-3.5 w-3.5 text-slate-600" />}
                  </React.Fragment>
                ))}
              </div>
              <p className="text-slate-400 leading-relaxed">
                A change at the database column travels up through every layer that depends on it (models, repositories, services, the API contract, the TypeScript types and components), and finally to the tests that cover those pieces.
              </p>
            </section>

            <section className="space-y-2" data-testid="impact-risk">
              <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">4. Risk</h2>
              <div className="p-4 rounded-xl bg-rose-950/20 border border-rose-500/30 space-y-3">
                <div className="flex items-center gap-2 font-bold text-rose-200">
                  <ShieldAlert className="h-4 w-4" /> High risk
                </div>
                <ul className="list-disc pl-5 space-y-1 text-slate-300">
                  {SCENARIO.riskReasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
                <div className="text-[11px] font-semibold text-slate-400 pt-1">Suggested mitigations</div>
                <ul className="list-disc pl-5 space-y-1 text-slate-300">
                  {SCENARIO.mitigations.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="space-y-3" data-testid="impact-layers">
              <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">5. Files and components to review, by layer</h2>
              {LAYERS.map((layer) => {
                const items = IMPACT_ITEMS.filter((i) => i.layer === layer.id);
                if (!items.length) return null;
                return (
                  <div key={layer.id} className="rounded-xl border border-slate-800 overflow-hidden" data-testid="impact-layer-group" data-layer={layer.id}>
                    <div className="px-3 py-2 bg-slate-900 flex items-center gap-2 font-semibold" style={{ color: layer.color }}>
                      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: layer.color }} />
                      {layer.label}
                      <span className="ml-auto text-slate-500 font-mono">{items.length}</span>
                    </div>
                    <div className="divide-y divide-slate-800/80">
                      {items.map((item) => (
                        <div key={item.file} className="px-3 py-2.5 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1" data-testid="impact-item">
                          <div className="font-mono text-[11px] text-slate-100 break-all">{item.file}</div>
                          <div className="flex gap-1.5 justify-end">
                            <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${item.category === "direct" ? "bg-sky-500/10 border-sky-400/40 text-sky-200" : "bg-slate-800 border-slate-600 text-slate-300"}`}>
                              {item.category}
                            </span>
                            <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${RISK_STYLE[item.risk]}`}>{item.risk}</span>
                          </div>
                          <div className="col-span-2 text-slate-400 leading-relaxed">
                            <span className="font-mono text-slate-300">{item.symbol}</span>: {item.why} <span className="text-slate-200">Action: {item.action}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
              <div className="rounded-xl border border-dashed border-slate-700 px-3 py-2.5 flex items-center gap-2 text-slate-300" data-testid="impact-new-file">
                <FilePlus2 className="h-4 w-4 text-emerald-400" />
                <span className="font-mono text-[11px]">{SCENARIO.newFile}</span>
                <span className="text-slate-500">new migration file to create</span>
              </div>
              <p className="text-[11px] text-slate-500">
                &quot;Direct&quot; means the file contains the identifier itself. &quot;Indirect&quot; means it depends on a directly affected file but does not use the identifier.
              </p>
            </section>

            <div className="flex flex-wrap gap-2 pt-2">
              <button onClick={onShowGraph} data-testid="open-graph-highlight" className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold flex items-center gap-2">
                <GitFork className="h-4 w-4 text-indigo-300" /> Highlight in the dependency graph
              </button>
              <button onClick={onShowPreview} data-testid="open-preview" className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-2 shadow-glow">
                <Eye className="h-4 w-4" /> Preview the proposed modification
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: "risk" }) {
  return (
    <div className={`p-3 rounded-xl border ${tone === "risk" ? "bg-rose-950/20 border-rose-500/30" : "bg-surface/40 border-slate-800"}`}>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-bold ${tone === "risk" ? "text-rose-300" : "text-white"}`}>{value}</div>
    </div>
  );
}
