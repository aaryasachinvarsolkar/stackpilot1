"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ZoomIn, ZoomOut, Maximize2, GitFork, MousePointerClick } from "lucide-react";
import {
  GRAPH_EDGES,
  GRAPH_NODES,
  LAYERS,
  LAYER_BY_ID,
  NODE_BY_ID,
  SCENARIO,
  dependenciesOf,
  dependentsOf,
  directDependencies,
  directDependents,
  impactOf,
  type GraphNodeData,
} from "@/lib/sampleScenario";

// SAMPLE graph: the data comes from lib/sampleScenario.ts, not from a repository scan.

const NODE_W = 160;
const NODE_H = 46;
const COL_GAP = 212;
const ROW_GAP = 76;
const HEADER_H = 34;

interface Placed extends GraphNodeData {
  cx: number;
  cy: number;
}

function computeLayout() {
  const byLayer = LAYERS.map((l) => GRAPH_NODES.filter((n) => n.layer === l.id));
  const maxRows = Math.max(...byLayer.map((c) => c.length));
  const placed: Placed[] = [];
  byLayer.forEach((col, ci) => {
    const offset = ((maxRows - col.length) * ROW_GAP) / 2;
    col.forEach((n, ri) => {
      placed.push({ ...n, cx: ci * COL_GAP + NODE_W / 2, cy: offset + ri * ROW_GAP + NODE_H / 2 });
    });
  });
  const width = (LAYERS.length - 1) * COL_GAP + NODE_W;
  const height = (maxRows - 1) * ROW_GAP + NODE_H;
  return { placed, width, height };
}

function edgePath(a: Placed, b: Placed): string {
  if (a.cx < b.cx) {
    const x1 = a.cx + NODE_W / 2;
    const x2 = b.cx - NODE_W / 2;
    const dx = Math.max(40, (x2 - x1) / 2);
    return `M ${x1} ${a.cy} C ${x1 + dx} ${a.cy}, ${x2 - dx} ${b.cy}, ${x2} ${b.cy}`;
  }
  if (a.cx > b.cx) {
    const x1 = a.cx - NODE_W / 2;
    const x2 = b.cx + NODE_W / 2;
    const dx = Math.max(40, (x1 - x2) / 2);
    return `M ${x1} ${a.cy} C ${x1 - dx} ${a.cy}, ${x2 + dx} ${b.cy}, ${x2} ${b.cy}`;
  }
  const down = b.cy > a.cy;
  const y1 = a.cy + (down ? NODE_H / 2 : -NODE_H / 2);
  const y2 = b.cy + (down ? -NODE_H / 2 : NODE_H / 2);
  return `M ${a.cx} ${y1} L ${b.cx} ${y2}`;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

interface LayerGraphProps {
  /** When the sample change has been selected, mark the changed node and everything it impacts. */
  showScenario?: boolean;
}

export function LayerGraph({ showScenario = false }: LayerGraphProps) {
  const { placed, width, height } = useMemo(computeLayout, []);
  const byId = useMemo(() => Object.fromEntries(placed.map((p) => [p.id, p])) as Record<string, Placed>, [placed]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const [userMoved, setUserMoved] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const fit = useCallback(() => {
    const el = containerRef.current;
    if (!el || el.clientWidth === 0 || el.clientHeight === 0) return;
    const pad = 28;
    const minY = -HEADER_H;
    const bw = width;
    const bh = height - minY;
    const k = clamp(Math.min((el.clientWidth - 2 * pad) / bw, (el.clientHeight - 2 * pad) / bh), 0.3, 1.25);
    setView({ k, x: (el.clientWidth - bw * k) / 2, y: (el.clientHeight - bh * k) / 2 - minY * k });
  }, [width, height]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Auto-fit only until the user has panned or zoomed; re-running this effect must never undo their change.
    if (!userMoved) fit();
    const ro = new ResizeObserver(() => {
      if (!userMoved) fit();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [fit, userMoved]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      setUserMoved(true);
      setView((v) => {
        const k = clamp(v.k * (e.deltaY < 0 ? 1.1 : 1 / 1.1), 0.3, 2.5);
        const r = k / v.k;
        return { k, x: px - (px - v.x) * r, y: py - (py - v.y) * r };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const zoomBy = (factor: number) => {
    const el = containerRef.current;
    if (!el) return;
    const px = el.clientWidth / 2;
    const py = el.clientHeight / 2;
    setUserMoved(true);
    setView((v) => {
      const k = clamp(v.k * factor, 0.3, 2.5);
      const r = k / v.k;
      return { k, x: px - (px - v.x) * r, y: py - (py - v.y) * r };
    });
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as Element).closest("[data-node]")) return;
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    d.x = e.clientX;
    d.y = e.clientY;
    if (Math.abs(dx) + Math.abs(dy) > 0) d.moved = true;
    setUserMoved(true);
    setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    if (drag.current) {
      if (!drag.current.moved) setSelectedId(null); // plain click on the background clears the selection
      drag.current = null;
      try {
        (e.currentTarget as Element).releasePointerCapture(e.pointerId);
      } catch {
        /* pointer already released */
      }
    }
  };

  // --- highlight sets -------------------------------------------------------------------------
  const selected = selectedId ? NODE_BY_ID[selectedId] : null;
  const selDeps = useMemo(() => (selectedId ? new Set(dependenciesOf(selectedId)) : new Set<string>()), [selectedId]);
  const selImpact = useMemo(() => (selectedId ? new Set(impactOf(selectedId)) : new Set<string>()), [selectedId]);
  const scenarioImpact = useMemo(() => new Set(impactOf(SCENARIO.changedNodeId)), []);

  type Role = "selected" | "dependency" | "impact" | "changed" | "scenario" | "none";
  const roleOf = (id: string): Role => {
    if (selectedId) {
      if (id === selectedId) return "selected";
      if (selImpact.has(id)) return "impact";
      if (selDeps.has(id)) return "dependency";
      return "none";
    }
    if (showScenario) {
      if (id === SCENARIO.changedNodeId) return "changed";
      if (scenarioImpact.has(id)) return "scenario";
    }
    return "none";
  };
  const highlighting = Boolean(selectedId) || showScenario;

  const roleStyle: Record<Role, { stroke: string; fill: string; width: number; dash?: string }> = {
    selected: { stroke: "#ffffff", fill: "#1e293b", width: 3 },
    dependency: { stroke: "#22d3ee", fill: "#0b1b2a", width: 2, dash: "5 3" },
    impact: { stroke: "#f59e0b", fill: "#2a1a05", width: 2.5 },
    changed: { stroke: "#f43f5e", fill: "#33101a", width: 3 },
    scenario: { stroke: "#f59e0b", fill: "#2a1a05", width: 2.5 },
    none: { stroke: "", fill: "#0f172a", width: 1.5 },
  };

  const edgeRole = (from: string, to: string): "hot" | "dep" | "none" => {
    const a = roleOf(from);
    const b = roleOf(to);
    const hotRoles: Role[] = ["selected", "impact", "changed", "scenario"];
    if (hotRoles.includes(a) && hotRoles.includes(b)) return "hot";
    if (selectedId && (a === "dependency" || a === "selected") && (b === "dependency" || b === "selected")) return "dep";
    return "none";
  };

  // --- side panel ------------------------------------------------------------------------------
  const impacted = selectedId ? impactOf(selectedId) : [];
  const impactedByLayer = LAYERS.map((l) => ({ layer: l, nodes: impacted.map((id) => NODE_BY_ID[id]).filter((n) => n.layer === l.id) })).filter((g) => g.nodes.length);

  return (
    <div className="h-full w-full flex bg-[#070a12] text-slate-200 select-none overflow-hidden" data-testid="graph-root">
      {/* ------------------------------ canvas ------------------------------ */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="h-11 shrink-0 border-b border-slate-800 bg-[#090d16]/90 px-3 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 font-bold text-white">
            <GitFork className="h-4 w-4 text-indigo-400" />
            <span>Cross-layer dependency graph</span>
            <span className="px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-400/40 text-violet-200 text-[10px] font-semibold tracking-wide" data-testid="graph-sample-chip">
              SAMPLE DATA
            </span>
          </div>
          <div className="flex items-center gap-1">
            <span className="text-[11px] text-slate-500 font-mono mr-2" data-testid="graph-zoom-label">
              {Math.round(view.k * 100)}%
            </span>
            <button onClick={() => zoomBy(1.2)} title="Zoom in" className="p-1.5 hover:bg-slate-800 rounded text-slate-300 hover:text-white">
              <ZoomIn className="h-4 w-4" />
            </button>
            <button onClick={() => zoomBy(1 / 1.2)} title="Zoom out" className="p-1.5 hover:bg-slate-800 rounded text-slate-300 hover:text-white">
              <ZoomOut className="h-4 w-4" />
            </button>
            <button
              onClick={() => {
                setUserMoved(false);
                fit();
              }}
              title="Fit to screen"
              className="flex items-center gap-1 px-2 py-1 hover:bg-slate-800 rounded text-slate-300 hover:text-white"
            >
              <Maximize2 className="h-3.5 w-3.5" />
              <span>Fit</span>
            </button>
          </div>
        </div>

        <div
          ref={containerRef}
          data-testid="graph-canvas"
          className="flex-1 min-h-0 relative overflow-hidden cursor-grab active:cursor-grabbing touch-none"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <div
            className="absolute inset-0 opacity-15 pointer-events-none"
            style={{ backgroundImage: "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.2) 1px, transparent 0)", backgroundSize: "24px 24px" }}
          />
          <svg className="absolute inset-0 w-full h-full" data-testid="graph-svg">
            <defs>
              {[
                ["arrow-n", "#64748b"],
                ["arrow-hot", "#f59e0b"],
                ["arrow-dep", "#22d3ee"],
              ].map(([id, color]) => (
                <marker key={id} id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
                  <path d="M 0 1 L 10 5 L 0 9 z" fill={color} />
                </marker>
              ))}
            </defs>
            <g data-testid="graph-viewport" data-k={view.k.toFixed(3)} data-x={view.x.toFixed(1)} data-y={view.y.toFixed(1)} transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              {LAYERS.map((l, i) => (
                <text key={l.id} x={i * COL_GAP + NODE_W / 2} y={-HEADER_H / 2 + 6} textAnchor="middle" fontSize="11" fontWeight="700" letterSpacing="1.5" fill={l.color} data-testid="layer-header">
                  {l.short}
                </text>
              ))}

              {GRAPH_EDGES.map((e) => {
                const a = byId[e.from];
                const b = byId[e.to];
                const r = edgeRole(e.from, e.to);
                const color = r === "hot" ? "#f59e0b" : r === "dep" ? "#22d3ee" : "#64748b";
                const dim = highlighting && r === "none";
                return (
                  <path
                    key={e.id}
                    data-testid="graph-edge"
                    d={edgePath(a, b)}
                    fill="none"
                    stroke={color}
                    strokeWidth={r === "none" ? 1.4 : 2.4}
                    strokeDasharray={e.kind === "tested-by" ? "5 4" : undefined}
                    markerEnd={`url(#${r === "hot" ? "arrow-hot" : r === "dep" ? "arrow-dep" : "arrow-n"})`}
                    opacity={dim ? 0.12 : 0.85}
                  />
                );
              })}

              {placed.map((n) => {
                const role = roleOf(n.id);
                const style = roleStyle[role];
                const layer = LAYER_BY_ID[n.layer];
                const dim = highlighting && role === "none";
                return (
                  <g
                    key={n.id}
                    data-node
                    data-testid="graph-node"
                    data-node-id={n.id}
                    data-role={role}
                    data-selected={role === "selected" ? "true" : "false"}
                    transform={`translate(${n.cx - NODE_W / 2} ${n.cy - NODE_H / 2})`}
                    tabIndex={0}
                    role="button"
                    aria-label={`${n.label}, ${layer.label}`}
                    onClick={() => setSelectedId(n.id === selectedId ? null : n.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedId(n.id === selectedId ? null : n.id);
                      }
                    }}
                    className="cursor-pointer outline-none"
                    opacity={dim ? 0.3 : 1}
                  >
                    <rect width={NODE_W} height={NODE_H} rx={9} fill={style.fill} stroke={style.stroke || layer.color} strokeWidth={style.width} strokeDasharray={style.dash} />
                    <rect width={5} height={NODE_H} rx={2} fill={layer.color} />
                    <text x={NODE_W / 2 + 2} y={19} textAnchor="middle" fontSize="11.5" fontWeight="700" fill="#ffffff" fontFamily="ui-monospace, monospace">
                      {n.label}
                    </text>
                    <text x={NODE_W / 2 + 2} y={34} textAnchor="middle" fontSize="9.5" fill="#94a3b8">
                      {n.kind}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>

          {/* legend */}
          <div className="absolute bottom-3 left-3 p-2.5 rounded-lg bg-slate-900/90 border border-slate-800 text-[10px] text-slate-300 space-y-1 pointer-events-none" data-testid="graph-legend">
            <div className="flex items-center gap-2"><span className="inline-block w-5 h-0 border-t-2 border-slate-500" /> depends on (arrow points at the dependency)</div>
            <div className="flex items-center gap-2"><span className="inline-block w-5 h-0 border-t-2 border-dashed border-slate-500" /> covered by a test</div>
            {showScenario && !selectedId && (
              <>
                <div className="flex items-center gap-2"><span className="inline-block w-3 h-3 rounded-sm border-2 border-rose-500" /> changed: orders.customer_id</div>
                <div className="flex items-center gap-2"><span className="inline-block w-3 h-3 rounded-sm border-2 border-amber-500" /> impacted by the sample change</div>
              </>
            )}
            {selectedId && (
              <>
                <div className="flex items-center gap-2"><span className="inline-block w-3 h-3 rounded-sm border-2 border-amber-500" /> would be impacted if the selected node changes</div>
                <div className="flex items-center gap-2"><span className="inline-block w-3 h-3 rounded-sm border-2 border-dashed border-cyan-400" /> what the selected node depends on</div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ------------------------------ side panel ------------------------------ */}
      <aside className="w-80 shrink-0 border-l border-slate-800 bg-[#0b101b] overflow-y-auto text-xs" data-testid="graph-sidepanel">
        {!selected ? (
          <div className="p-4 space-y-4">
            <div className="flex items-center gap-2 text-slate-300 font-semibold">
              <MousePointerClick className="h-4 w-4 text-indigo-400" />
              <span>Select a node</span>
            </div>
            <p className="text-slate-400 leading-relaxed">
              Click any node to see which layer it belongs to, what it depends on, and what would be impacted downstream if it changed. Drag the background to pan, scroll to zoom.
            </p>
            <div className="space-y-1.5">
              {LAYERS.map((l) => (
                <div key={l.id} className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-slate-300">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} />
                    {l.label}
                  </span>
                  <span className="font-mono text-slate-500">{GRAPH_NODES.filter((n) => n.layer === l.id).length}</span>
                </div>
              ))}
            </div>
            <div className="p-3 rounded-lg bg-violet-500/10 border border-violet-400/30 text-violet-100 leading-relaxed">
              <strong>Sample data.</strong> {GRAPH_NODES.length} nodes and {GRAPH_EDGES.length} edges written by hand for the orders-platform demo. No repository was scanned and no analyzer or AI model produced this graph.
            </div>
          </div>
        ) : (
          <div className="p-4 space-y-4" data-testid="graph-node-details">
            <div>
              <h3 className="text-sm font-bold text-white font-mono break-all" data-testid="selected-label">{selected.label}</h3>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold border" style={{ color: LAYER_BY_ID[selected.layer].color, borderColor: LAYER_BY_ID[selected.layer].color + "88" }} data-testid="selected-layer">
                  {LAYER_BY_ID[selected.layer].label}
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-800 text-slate-300">{selected.kind}</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] bg-violet-500/15 border border-violet-400/40 text-violet-200">sample</span>
              </div>
              <div className="mt-2 font-mono text-[11px] text-slate-400 break-all">{selected.file}</div>
              <p className="mt-2 text-slate-300 leading-relaxed">{selected.detail}</p>
            </div>

            <Section title="Depends on" count={directDependencies(selected.id).length} testid="deps-list">
              {directDependencies(selected.id).map(({ node, label }) => (
                <NodeLink key={node.id + label} node={node} note={label} onClick={() => setSelectedId(node.id)} />
              ))}
            </Section>

            <Section title="Used by / covered by" count={directDependents(selected.id).length} testid="dependents-list">
              {directDependents(selected.id).map(({ node, label }) => (
                <NodeLink key={node.id + label} node={node} note={label} onClick={() => setSelectedId(node.id)} />
              ))}
            </Section>

            <div data-testid="impact-summary">
              <div className="text-[11px] font-bold uppercase tracking-wider text-amber-300 mb-1.5">
                Potential downstream impact ({impacted.length})
              </div>
              {impacted.length === 0 ? (
                <p className="text-slate-400">Nothing in the sample graph depends on this node, so a change here has no downstream impact.</p>
              ) : (
                <div className="space-y-2.5">
                  <p className="text-slate-400 leading-relaxed">If this node changes, these would need review (transitive dependents, plus the tests that cover them):</p>
                  {impactedByLayer.map(({ layer, nodes }) => (
                    <div key={layer.id}>
                      <div className="text-[10px] font-semibold mb-1" style={{ color: layer.color }}>{layer.short}</div>
                      <div className="space-y-1">
                        {nodes.map((n) => (
                          <NodeLink key={n.id} node={n} onClick={() => setSelectedId(n.id)} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <p className="mt-2 text-[10px] text-slate-500">Computed from the sample edges above; deterministic.</p>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function Section({ title, count, testid, children }: { title: string; count: number; testid: string; children: React.ReactNode }) {
  return (
    <div data-testid={testid}>
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
        {title} ({count})
      </div>
      {count === 0 ? <p className="text-slate-500">None</p> : <div className="space-y-1">{children}</div>}
    </div>
  );
}

function NodeLink({ node, note, onClick }: { node: GraphNodeData; note?: string; onClick: () => void }) {
  const layer = LAYER_BY_ID[node.layer];
  return (
    <button onClick={onClick} className="w-full text-left px-2 py-1.5 rounded-md bg-slate-900 hover:bg-slate-800 border border-slate-800 flex items-center gap-2">
      <span className="h-2 w-2 rounded-sm shrink-0" style={{ background: layer.color }} />
      <span className="min-w-0">
        <span className="block font-mono text-[11px] text-slate-100 truncate">{node.label}</span>
        {note && <span className="block text-[10px] text-slate-500 truncate">{note}</span>}
      </span>
    </button>
  );
}
