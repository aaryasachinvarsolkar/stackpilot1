"use client";

import React, { useEffect, useState, useMemo } from "react";
import { GitFork, Loader2, Sparkles, Box, FileCode, Layers, ArrowRight, ExternalLink } from "lucide-react";
import { getProjectGraph, ProjectGraphData, GraphNode, GraphLink } from "@/lib/api";

interface RealProjectGraphProps {
  projectId: string;
  onSelectFile?: (path: string) => void;
}

interface LayoutNode extends GraphNode {
  x: number;
  y: number;
  col: number;
  color: string;
}

const TYPE_COLORS: Record<string, string> = {
  entry: "from-cyan-500 to-blue-600 border-cyan-400/40 text-cyan-200",
  api: "from-indigo-500 to-purple-600 border-indigo-400/40 text-indigo-200",
  service: "from-emerald-500 to-teal-600 border-emerald-400/40 text-emerald-200",
  model: "from-amber-500 to-orange-600 border-amber-400/40 text-amber-200",
  component: "from-violet-500 to-fuchsia-600 border-violet-400/40 text-violet-200",
  module: "from-slate-700 to-slate-800 border-slate-600 text-slate-300",
};

export function RealProjectGraph({ projectId, onSelectFile }: RealProjectGraphProps) {
  const [data, setData] = useState<ProjectGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getProjectGraph(projectId).then((res) => {
      if (cancelled) return;
      setLoading(false);
      if (res.ok && res.data) {
        setData(res.data);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const { layoutNodes, layoutWidth, layoutHeight } = useMemo(() => {
    if (!data || !data.nodes || data.nodes.length === 0) {
      return { layoutNodes: [], layoutWidth: 800, layoutHeight: 500 };
    }

    // Partition into 4 logical columns
    const cols: GraphNode[][] = [[], [], [], []];
    data.nodes.forEach((n) => {
      if (n.type === "entry") cols[0].push(n);
      else if (n.type === "api") cols[1].push(n);
      else if (n.type === "service" || n.type === "component") cols[2].push(n);
      else cols[3].push(n);
    });

    // If some columns are empty, balance them
    const maxPerCol = Math.max(1, ...cols.map((c) => c.length));
    const COL_W = 240;
    const ROW_H = 75;
    const START_X = 60;
    const START_Y = 60;

    const placed: LayoutNode[] = [];
    cols.forEach((colNodes, colIdx) => {
      colNodes.forEach((node, rowIdx) => {
        placed.push({
          ...node,
          x: START_X + colIdx * COL_W,
          y: START_Y + rowIdx * ROW_H,
          col: colIdx,
          color: TYPE_COLORS[node.type] || TYPE_COLORS.module,
        });
      });
    });

    return {
      layoutNodes: placed,
      layoutWidth: START_X + 4 * COL_W + 100,
      layoutHeight: Math.max(550, START_Y + maxPerCol * ROW_H + 80),
    };
  }, [data]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, LayoutNode>();
    layoutNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [layoutNodes]);

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-slate-400 space-y-3">
        <Loader2 className="h-7 w-7 text-indigo-400 animate-spin" />
        <p className="text-xs">Scanning {projectId} for import statements...</p>
      </div>
    );
  }

  if (!data || layoutNodes.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-slate-400 space-y-2">
        <Box className="h-8 w-8 text-slate-600" />
        <h3 className="text-white font-semibold text-sm">No code modules found to graph</h3>
        <p className="text-xs max-w-sm text-center">Add Python, TypeScript, or Go files to generate an architecture map.</p>
      </div>
    );
  }

  const selectedNodeObj = selectedNode ? nodeMap.get(selectedNode) : null;
  const connectedLinks = data.links.filter(
    (l) => l.source === selectedNode || l.target === selectedNode
  );

  return (
    <div className="h-full w-full flex flex-col min-h-0 bg-[#070b14] overflow-hidden select-none">
      {/* Top Telemetry Strip */}
      <div className="shrink-0 px-4 py-2 border-b border-slate-800 bg-[#0a0f1b] flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <GitFork className="h-4 w-4 text-indigo-400" />
          <span className="font-bold text-white uppercase tracking-wider text-[11px]">Architecture & Dependency Graph</span>
          <span className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-200 border border-amber-400/30 text-[10px] font-semibold" data-testid="graph-heuristic-chip" title="Edges come from a text match on import lines in the first 80 lines of each file, not from a parser. Some edges may be wrong or missing, and at most 60 files and 80 edges are shown.">
            HEURISTIC · import-line scan, not a parser
          </span>
          <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 text-[10px] font-mono">
            {layoutNodes.length} files shown
          </span>
        </div>
        <p className="text-[11px] text-slate-400 font-mono hidden md:block">{data.summary}</p>
      </div>

      <div className="flex-1 min-h-0 flex relative overflow-hidden">
        {/* SVG Canvas Area */}
        <div className="flex-1 min-h-0 overflow-auto p-4 cursor-grab">
          <svg
            width={layoutWidth}
            height={layoutHeight}
            className="overflow-visible"
            style={{ minWidth: "100%", minHeight: "100%" }}
          >
            {/* Column Label Backdrops */}
            {["1. Entrypoints", "2. API & Routes", "3. Core & Services", "4. Models & Schemas"].map((colLabel, idx) => (
              <g key={idx}>
                <text
                  x={60 + idx * 240 + 75}
                  y={30}
                  textAnchor="middle"
                  className="fill-slate-500 font-mono text-[10px] uppercase font-bold tracking-wider"
                >
                  {colLabel}
                </text>
                <line
                  x1={60 + idx * 240 + 75}
                  y1={42}
                  x2={60 + idx * 240 + 75}
                  y2={layoutHeight - 20}
                  stroke="#1e293b"
                  strokeDasharray="4 4"
                  strokeWidth="1"
                />
              </g>
            ))}

            {/* Dependency Links */}
            {data.links.map((link, idx) => {
              const src = nodeMap.get(link.source);
              const tgt = nodeMap.get(link.target);
              if (!src || !tgt) return null;

              const isHighlighted = selectedNode === link.source || selectedNode === link.target;
              const x1 = src.x + 150;
              const y1 = src.y + 22;
              const x2 = tgt.x;
              const y2 = tgt.y + 22;
              const dx = Math.abs(x2 - x1) / 2;

              return (
                <path
                  key={idx}
                  d={`M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`}
                  fill="none"
                  stroke={isHighlighted ? "#818cf8" : "#334155"}
                  strokeWidth={isHighlighted ? 2.5 : 1.2}
                  strokeOpacity={isHighlighted ? 0.9 : 0.4}
                  className="transition-all"
                />
              );
            })}

            {/* Nodes */}
            {layoutNodes.map((n) => {
              const isSelected = selectedNode === n.id;
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x}, ${n.y})`}
                  onClick={() => setSelectedNode(n.id === selectedNode ? null : n.id)}
                  className="cursor-pointer group"
                >
                  <rect
                    width={150}
                    height={44}
                    rx={10}
                    className={`transition-all ${
                      isSelected
                        ? "fill-indigo-950 stroke-indigo-400 stroke-2 filter drop-shadow(0 0 10px rgba(99,102,241,0.5))"
                        : "fill-slate-900/90 stroke-slate-800 hover:stroke-indigo-500/80 hover:fill-slate-800/90"
                    }`}
                  />
                  {/* Left accent bar */}
                  <rect
                    x={0}
                    y={0}
                    width={4}
                    height={44}
                    rx={2}
                    className={`bg-gradient-to-b ${
                      n.type === "entry"
                        ? "fill-cyan-400"
                        : n.type === "api"
                        ? "fill-indigo-400"
                        : n.type === "service"
                        ? "fill-emerald-400"
                        : "fill-amber-400"
                    }`}
                  />
                  <text
                    x={12}
                    y={20}
                    className="fill-slate-200 font-mono text-[11px] font-semibold truncate select-none"
                    style={{ maxWidth: 130 }}
                  >
                    {n.label}
                  </text>
                  <text
                    x={12}
                    y={34}
                    className="fill-slate-500 font-mono text-[9px] uppercase tracking-wider select-none"
                  >
                    {n.type}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Selected Node Details Sidecard */}
        {selectedNodeObj && (
          <div className="w-72 border-l border-slate-800 bg-[#090d16]/95 backdrop-blur-md p-4 flex flex-col space-y-3 z-10 text-xs">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="font-bold text-white uppercase text-[10px] tracking-wider">Module Inspector</span>
              <span className="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 font-mono text-[10px]">
                {selectedNodeObj.type}
              </span>
            </div>

            <div className="space-y-1">
              <span className="text-slate-400 text-[10px] uppercase font-semibold">File Path</span>
              <p className="font-mono text-indigo-300 break-all text-[11px] bg-slate-900 p-2 rounded border border-slate-800">
                {selectedNodeObj.path}
              </p>
            </div>

            <div className="space-y-1">
              <span className="text-slate-400 text-[10px] uppercase font-semibold">Connections</span>
              <p className="text-slate-300 text-xs">
                {connectedLinks.length} linked import{connectedLinks.length === 1 ? "" : "s"} across modules.
              </p>
            </div>

            {onSelectFile && (
              <button
                onClick={() => onSelectFile(selectedNodeObj.path)}
                className="w-full mt-auto py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-semibold text-xs flex items-center justify-center gap-1.5 transition-colors shadow-glow"
              >
                <FileCode className="h-3.5 w-3.5" />
                <span>Open in Code Editor</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
