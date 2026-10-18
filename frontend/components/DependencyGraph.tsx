"use client";

import React, { useState, useMemo, useRef } from "react";
import {
  Layers,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Download,
  AlertTriangle,
  Search,
  Filter,
  Eye,
  GitFork,
  ArrowRight,
  Maximize2,
  FileCode,
  ShieldAlert,
  Info,
} from "lucide-react";

export type NodeType = "file" | "class" | "function";
export type EdgeType = "imports" | "calls" | "extends";

export interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  path: string;
  loc: number;
  functionsCount?: number;
  x: number;
  y: number;
  isCycle?: boolean;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
  isCycle?: boolean;
}

interface DependencyGraphProps {
  onSelectNode?: (path: string) => void;
  onClose?: () => void;
}

const INITIAL_NODES: GraphNode[] = [
  // Files
  { id: "main.py", label: "main.py", type: "file", path: "app/main.py", loc: 45, functionsCount: 1, x: 380, y: 80 },
  { id: "routes.py", label: "routes.py", type: "file", path: "app/api/routes.py", loc: 68, functionsCount: 3, x: 220, y: 190 },
  { id: "connection.py", label: "connection.py", type: "file", path: "app/database/connection.py", loc: 52, functionsCount: 2, x: 120, y: 310 },
  { id: "session.py", label: "session.py", type: "file", path: "app/database/session.py", loc: 24, functionsCount: 1, x: 260, y: 310 },
  { id: "base.py", label: "base.py", type: "file", path: "app/models/base.py", loc: 32, functionsCount: 2, x: 390, y: 310 },
  { id: "config.py", label: "config.py", type: "file", path: "app/config.py", loc: 48, functionsCount: 1, x: 540, y: 190 },
  { id: "rateLimiter.ts", label: "rateLimiter.ts", type: "file", path: "app/middleware/rateLimiter.ts", loc: 40, functionsCount: 1, x: 360, y: 190, isCycle: true },
  { id: "test_health.py", label: "test_health.py", type: "file", path: "tests/test_health.py", loc: 38, functionsCount: 3, x: 620, y: 80 },
  // Functions
  { id: "detailed_health()", label: "detailed_health()", type: "function", path: "app/api/routes.py", loc: 14, x: 180, y: 260 },
  { id: "check_db()", label: "check_db()", type: "function", path: "app/database/connection.py", loc: 18, x: 80, y: 380 },
  { id: "rateLimiter()", label: "rateLimiter()", type: "function", path: "app/middleware/rateLimiter.ts", loc: 22, x: 420, y: 260, isCycle: true },
];

const INITIAL_EDGES: GraphEdge[] = [
  { id: "e1", source: "main.py", target: "routes.py", type: "imports" },
  { id: "e2", source: "main.py", target: "config.py", type: "imports" },
  { id: "e3", source: "routes.py", target: "connection.py", type: "imports" },
  { id: "e4", source: "routes.py", target: "session.py", type: "imports" },
  { id: "e5", source: "routes.py", target: "rateLimiter.ts", type: "imports", isCycle: true },
  { id: "e6", source: "rateLimiter.ts", target: "routes.py", type: "imports", isCycle: true },
  { id: "e7", source: "connection.py", target: "config.py", type: "imports" },
  { id: "e8", source: "session.py", target: "connection.py", type: "calls" },
  { id: "e9", source: "main.py", target: "base.py", type: "imports" },
  { id: "e10", source: "test_health.py", target: "main.py", type: "calls" },
  { id: "e11", source: "detailed_health()", target: "check_db()", type: "calls" },
  { id: "e12", source: "routes.py", target: "detailed_health()", type: "extends" },
  { id: "e13", source: "rateLimiter.ts", target: "rateLimiter()", type: "extends", isCycle: true },
];

export function DependencyGraph({ onSelectNode, onClose }: DependencyGraphProps) {
  const [nodes, setNodes] = useState<GraphNode[]>(INITIAL_NODES);
  const [edges, setEdges] = useState<GraphEdge[]>(INITIAL_EDGES);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [filterType, setFilterType] = useState<"all" | "file-only">("all");
  const [layoutMode, setLayoutMode] = useState<"force" | "hierarchical">("hierarchical");
  const [search, setSearch] = useState("");
  const [showCyclesOnly, setShowCyclesOnly] = useState(false);
  const [impactMode, setImpactMode] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [showCycleList, setShowCycleList] = useState(false);

  // Filter nodes
  const visibleNodes = useMemo(() => {
    return nodes.filter((n) => {
      if (filterType === "file-only" && n.type === "function") return false;
      if (showCyclesOnly && !n.isCycle) return false;
      if (search && !n.label.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [nodes, filterType, showCyclesOnly, search]);

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);

  const visibleEdges = useMemo(() => {
    return edges.filter(
      (e) =>
        visibleNodeIds.has(e.source) &&
        visibleNodeIds.has(e.target) &&
        (!showCyclesOnly || e.isCycle)
    );
  }, [edges, visibleNodeIds, showCyclesOnly]);

  // Compute impact (dependents of selected node: what breaks if this changes)
  const impactedNodeIds = useMemo(() => {
    if (!selectedNode || !impactMode) return new Set<string>();
    const impacted = new Set<string>([selectedNode.id]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const e of edges) {
        if (impacted.has(e.target) && !impacted.has(e.source)) {
          impacted.add(e.source);
          changed = true;
        }
      }
    }
    return impacted;
  }, [selectedNode, impactMode, edges]);

  const handleNodeClick = (node: GraphNode) => {
    setSelectedNode(node);
    if (onSelectNode) {
      onSelectNode(node.path);
    }
  };

  const handleExportJSON = () => {
    const data = JSON.stringify({ nodes: visibleNodes, edges: visibleEdges }, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "stackpilot-dependency-graph.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full w-full flex flex-col bg-[#070a12] text-slate-200 select-none relative overflow-hidden font-sans">
      {/* ---------------------------------------------------- */}
      {/* 1. TOP GRAPH CONTROLS BAR                            */}
      {/* ---------------------------------------------------- */}
      <div className="h-11 border-b border-slate-800 bg-[#090d16]/90 px-3 flex items-center justify-between z-20 text-xs">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-bold text-white">
            <GitFork className="h-4 w-4 text-indigo-400" />
            <span>Dependency Graph</span>
          </div>

          <div className="h-4 w-[1px] bg-slate-800" />

          {/* Search within graph */}
          <div className="flex items-center gap-1.5 px-2 py-1 bg-slate-900 border border-slate-800 rounded-lg text-xs">
            <Search className="h-3 w-3 text-slate-500" />
            <input
              type="text"
              placeholder="Filter node..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-transparent border-none outline-none text-slate-200 text-xs placeholder:text-slate-600 w-28"
            />
          </div>

          {/* Function Detail Toggle */}
          <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-0.5">
            <button
              onClick={() => setFilterType("all")}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                filterType === "all" ? "bg-indigo-600 text-white font-semibold" : "text-slate-400 hover:text-white"
              }`}
            >
              All Symbols
            </button>
            <button
              onClick={() => setFilterType("file-only")}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                filterType === "file-only" ? "bg-indigo-600 text-white font-semibold" : "text-slate-400 hover:text-white"
              }`}
            >
              Files Only
            </button>
          </div>

          {/* Layout Toggle */}
          <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-0.5">
            <button
              onClick={() => setLayoutMode("hierarchical")}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                layoutMode === "hierarchical" ? "bg-indigo-600 text-white font-semibold" : "text-slate-400 hover:text-white"
              }`}
            >
              Hierarchical
            </button>
            <button
              onClick={() => setLayoutMode("force")}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                layoutMode === "force" ? "bg-indigo-600 text-white font-semibold" : "text-slate-400 hover:text-white"
              }`}
            >
              Force-Directed
            </button>
          </div>
        </div>

        {/* Right Controls: Impact, Cycles, Zoom & Export */}
        <div className="flex items-center gap-2">
          {/* Circular Dependency Warning Badge */}
          <button
            onClick={() => setShowCycleList(!showCycleList)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 text-xs font-semibold transition-colors"
          >
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>1 Circular Dependency Detected</span>
          </button>

          {/* Impact Analysis Mode Toggle */}
          <button
            onClick={() => setImpactMode(!impactMode)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold transition-colors ${
              impactMode
                ? "bg-amber-500/20 border-amber-500 text-amber-300 shadow-glow"
                : "bg-surface border-slate-800 text-slate-400 hover:text-white"
            }`}
            title="Highlight downstream dependencies ('what breaks if I change this')"
          >
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
            <span>Impact Analysis</span>
          </button>

          <div className="h-4 w-[1px] bg-slate-800" />

          {/* Zoom & Reset */}
          <button
            onClick={() => setZoom((z) => Math.min(z + 0.2, 2.5))}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            onClick={() => setZoom((z) => Math.max(z - 0.2, 0.4))}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <button
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
            title="Reset Pan & Zoom"
          >
            <RotateCcw className="h-4 w-4" />
          </button>

          {/* Export */}
          <button
            onClick={handleExportJSON}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface border border-slate-800 text-slate-300 hover:text-white transition-colors"
            title="Export Graph JSON"
          >
            <Download className="h-3.5 w-3.5 text-cyan-400" />
            <span>Export</span>
          </button>
        </div>
      </div>

      {/* ---------------------------------------------------- */}
      {/* 2. MAIN SVG CANVAS AREA                              */}
      {/* ---------------------------------------------------- */}
      <div className="flex-1 relative overflow-hidden bg-[#070a12] cursor-grab active:cursor-grabbing">
        {/* Background Grid Lines */}
        <div
          className="absolute inset-0 opacity-15 pointer-events-none"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.2) 1px, transparent 0)",
            backgroundSize: "24px 24px",
          }}
        />

        {/* SVG Drawing */}
        <svg
          className="w-full h-full"
          viewBox="0 0 800 500"
          style={{
            transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
            transformOrigin: "center center",
            transition: "transform 0.1s ease-out",
          }}
        >
          <defs>
            <marker
              id="arrow-imports"
              viewBox="0 0 10 10"
              refX="18"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#6366f1" />
            </marker>
            <marker
              id="arrow-calls"
              viewBox="0 0 10 10"
              refX="18"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#06b6d4" />
            </marker>
            <marker
              id="arrow-cycle"
              viewBox="0 0 10 10"
              refX="18"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#f43f5e" />
            </marker>
          </defs>

          {/* Render Edges */}
          {visibleEdges.map((edge) => {
            const sourceNode = visibleNodes.find((n) => n.id === edge.source);
            const targetNode = visibleNodes.find((n) => n.id === edge.target);
            if (!sourceNode || !targetNode) return null;

            const isCycle = edge.isCycle;
            const isImpacted =
              impactMode &&
              impactedNodeIds.has(edge.source) &&
              impactedNodeIds.has(edge.target);

            return (
              <line
                key={edge.id}
                x1={sourceNode.x}
                y1={sourceNode.y}
                x2={targetNode.x}
                y2={targetNode.y}
                stroke={
                  isCycle
                    ? "#f43f5e"
                    : isImpacted
                    ? "#f59e0b"
                    : edge.type === "imports"
                    ? "#4f46e5"
                    : "#06b6d4"
                }
                strokeWidth={isCycle ? 2.5 : isImpacted ? 2.5 : 1.5}
                strokeDasharray={edge.type === "calls" ? "4,4" : undefined}
                markerEnd={
                  isCycle
                    ? "url(#arrow-cycle)"
                    : edge.type === "calls"
                    ? "url(#arrow-calls)"
                    : "url(#arrow-imports)"
                }
                opacity={
                  selectedNode
                    ? edge.source === selectedNode.id || edge.target === selectedNode.id || isImpacted
                      ? 1
                      : 0.2
                    : 0.7
                }
              />
            );
          })}

          {/* Render Nodes */}
          {visibleNodes.map((node) => {
            const isSelected = selectedNode?.id === node.id;
            const isHovered = hoveredNode?.id === node.id;
            const isImpacted = impactMode && impactedNodeIds.has(node.id);
            const isCycle = node.isCycle;

            const fillColor = isCycle
              ? "#4c0519"
              : isImpacted
              ? "#451a03"
              : node.type === "file"
              ? "#0f172a"
              : "#083344";

            const strokeColor = isCycle
              ? "#f43f5e"
              : isImpacted
              ? "#f59e0b"
              : isSelected
              ? "#6366f1"
              : node.type === "file"
              ? "#3b82f6"
              : "#06b6d4";

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={() => handleNodeClick(node)}
                onMouseEnter={() => setHoveredNode(node)}
                onMouseLeave={() => setHoveredNode(null)}
                className="cursor-pointer"
              >
                {/* Node Box */}
                <rect
                  x="-65"
                  y="-18"
                  width="130"
                  height="36"
                  rx={node.type === "function" ? 18 : 8}
                  fill={fillColor}
                  stroke={strokeColor}
                  strokeWidth={isSelected || isCycle || isImpacted ? 2.5 : 1.5}
                  filter={isSelected || isCycle ? "drop-shadow(0 0 10px rgba(99,102,241,0.5))" : undefined}
                />

                {/* Node Label */}
                <text
                  textAnchor="middle"
                  dy="4"
                  fill="#ffffff"
                  fontSize="11"
                  fontFamily="monospace"
                  fontWeight="600"
                >
                  {node.label}
                </text>
              </g>
            );
          })}
        </svg>

        {/* ---------------------------------------------------- */}
        {/* 3. NODE HOVER TOOLTIP                                */}
        {/* ---------------------------------------------------- */}
        {hoveredNode && (
          <div className="absolute top-4 left-4 p-3 rounded-xl bg-slate-900/95 border border-slate-700 shadow-2xl backdrop-blur-md text-xs space-y-1 z-30 font-mono">
            <div className="font-bold text-white flex items-center gap-1.5">
              <FileCode className="h-3.5 w-3.5 text-indigo-400" />
              <span>{hoveredNode.label}</span>
            </div>
            <div className="text-[11px] text-slate-400">{hoveredNode.path}</div>
            <div className="pt-1 text-[11px] text-slate-300 flex items-center gap-3">
              <span>Lines: {hoveredNode.loc}</span>
              {hoveredNode.functionsCount !== undefined && (
                <span>Functions: {hoveredNode.functionsCount}</span>
              )}
            </div>
            {hoveredNode.isCycle && (
              <div className="text-[10px] text-rose-400 font-bold flex items-center gap-1 pt-1">
                <AlertTriangle className="h-3 w-3" /> Circular Dependency Detected
              </div>
            )}
          </div>
        )}

        {/* ---------------------------------------------------- */}
        {/* 4. CIRCULAR DEPENDENCY DRAWER                       */}
        {/* ---------------------------------------------------- */}
        {showCycleList && (
          <div className="absolute top-14 right-4 w-72 p-4 rounded-xl bg-slate-900/95 border border-rose-500/50 shadow-2xl backdrop-blur-xl z-30 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-rose-400">
                <ShieldAlert className="h-4 w-4" />
                <span>Detected Cycles (1)</span>
              </div>
              <button onClick={() => setShowCycleList(false)} className="text-slate-400 hover:text-white text-xs">
                ✕
              </button>
            </div>
            <div className="p-2.5 rounded-lg bg-rose-950/20 border border-rose-500/30 text-xs font-mono space-y-1">
              <div className="text-white font-semibold">Cycle 1:</div>
              <div className="text-rose-300">routes.py ➔ rateLimiter.ts</div>
              <div className="text-rose-300">rateLimiter.ts ➔ routes.py</div>
            </div>
            <p className="text-[11px] text-slate-400 leading-snug">
              Direct import cycle detected. Can cause runtime module resolution freezes in async workers.
            </p>
          </div>
        )}

        {/* ---------------------------------------------------- */}
        {/* 5. GRAPH LEGEND                                      */}
        {/* ---------------------------------------------------- */}
        <div className="absolute bottom-4 left-4 p-3 rounded-xl bg-slate-900/90 border border-slate-800/80 backdrop-blur-md text-[11px] flex flex-wrap gap-4 z-20">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-slate-900 border border-blue-500" />
            <span className="text-slate-300">File Node</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-cyan-950 border border-cyan-400" />
            <span className="text-slate-300">Function</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-[2px] bg-indigo-500 inline-block" />
            <span className="text-slate-300">Imports</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-[2px] border-b border-dashed border-cyan-400 inline-block" />
            <span className="text-slate-300">Function Call</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-[2px] bg-rose-500 inline-block" />
            <span className="text-rose-400 font-semibold">Circular Loop</span>
          </div>
        </div>
      </div>
    </div>
  );
}
