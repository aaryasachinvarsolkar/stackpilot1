"use client";

import React, { useState } from "react";
import {
  Terminal as TerminalIcon,
  CheckCircle2,
  AlertCircle,
  X,
  ChevronUp,
  ChevronDown,
  Play,
  RotateCcw,
  Network,
  Search,
  ExternalLink,
  ShieldCheck,
  Cpu,
} from "lucide-react";

interface BottomPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenGraph?: () => void;
}

export function BottomPanel({ isOpen, onClose, onOpenGraph }: BottomPanelProps) {
  const [activeTab, setActiveTab] = useState<"terminal" | "tests" | "dependencies" | "problems">("tests");
  const [depSearch, setDepSearch] = useState("");

  if (!isOpen) return null;

  const dependenciesList = [
    { file: "app/main.py", imports: ["app.core.config", "app.api.routes", "app.db.session"], callers: [] },
    { file: "app/api/routes.py", imports: ["app.db.session", "app.models.user"], callers: ["app/main.py"] },
    { file: "app/db/session.py", imports: ["app.core.config"], callers: ["app/main.py", "app/api/routes.py"] },
    { file: "app/core/config.py", imports: [], callers: ["app/main.py", "app/db/session.py"] },
    { file: "app/models/user.py", imports: ["app.db.session"], callers: ["app/api/routes.py"] },
    { file: "tests/test_health.py", imports: ["app.main"], callers: [] },
  ];

  const filteredDeps = dependenciesList.filter((d) =>
    d.file.toLowerCase().includes(depSearch.toLowerCase())
  );

  return (
    <div className="h-60 border-t border-slate-800 bg-[#090d16] flex flex-col select-none text-xs z-20">
      {/* Panel Tab Header */}
      <div className="h-9 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between px-3">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveTab("tests")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-t transition-colors ${
              activeTab === "tests"
                ? "bg-[#090d16] text-white border-t-2 border-t-emerald-500"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
            <span>Test Results</span>
            <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] font-mono">
              3/3
            </span>
          </button>

          <button
            onClick={() => setActiveTab("terminal")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-t transition-colors ${
              activeTab === "terminal"
                ? "bg-[#090d16] text-white border-t-2 border-t-indigo-500"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <TerminalIcon className="h-3.5 w-3.5 text-indigo-400" />
            <span>Terminal</span>
            <span className="flex items-center gap-1 px-1.5 py-0.2 rounded bg-indigo-500/10 text-indigo-300 text-[10px] font-mono border border-indigo-500/20">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Sandbox Active
            </span>
          </button>

          <button
            onClick={() => setActiveTab("dependencies")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-t transition-colors ${
              activeTab === "dependencies"
                ? "bg-[#090d16] text-white border-t-2 border-t-cyan-500"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Network className="h-3.5 w-3.5 text-cyan-400" />
            <span>Dependencies</span>
            <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-400 text-[10px] font-mono">
              {dependenciesList.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("problems")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-t transition-colors ${
              activeTab === "problems"
                ? "bg-[#090d16] text-white border-t-2 border-t-amber-500"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <span>Problems</span>
            <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-400 text-[10px] font-mono">
              0
            </span>
          </button>
        </div>

        {/* Panel Actions & Sandbox Status Pill */}
        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-950/30 border border-emerald-500/20 text-emerald-400 text-[10px] font-mono">
            <ShieldCheck className="h-3 w-3" />
            <span>Running in Sandbox (Docker v26)</span>
          </div>

          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200"
            title="Close Panel"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Panel Content Body */}
      <div className="flex-1 p-3 overflow-y-auto font-mono text-xs text-slate-300">
        {/* TAB: TESTS */}
        {activeTab === "tests" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] text-slate-400 border-b border-slate-800/60 pb-1.5">
              <span className="text-emerald-400 font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" /> All 3 test suites passed (0.16s)
              </span>
              <span className="text-slate-500">Resource: 512MB RAM • 1.0 vCPU • Network Isolated</span>
            </div>

            <div className="space-y-1 text-[11px]">
              <div className="flex items-center gap-2 text-slate-200 hover:bg-slate-900/60 p-1 rounded">
                <span className="text-emerald-400 font-bold">✓</span>
                <span className="text-slate-400">tests/test_health.py::</span>
                <span className="text-white font-medium">test_health_check_endpoint</span>
                <span className="text-slate-500 ml-auto">38ms</span>
              </div>
              <div className="flex items-center gap-2 text-slate-200 hover:bg-slate-900/60 p-1 rounded">
                <span className="text-emerald-400 font-bold">✓</span>
                <span className="text-slate-400">tests/test_health.py::</span>
                <span className="text-white font-medium">test_detailed_health_check_endpoint</span>
                <span className="text-slate-500 ml-auto">72ms</span>
              </div>
              <div className="flex items-center gap-2 text-slate-200 hover:bg-slate-900/60 p-1 rounded">
                <span className="text-emerald-400 font-bold">✓</span>
                <span className="text-slate-400">tests/test_health.py::</span>
                <span className="text-white font-medium">test_info_endpoint</span>
                <span className="text-slate-500 ml-auto">50ms</span>
              </div>
            </div>
          </div>
        )}

        {/* TAB: TERMINAL */}
        {activeTab === "terminal" && (
          <div className="space-y-1 text-slate-300">
            <div className="text-slate-500 flex items-center gap-2">
              <span>STACKPILOT Sandboxed Container (Isolated Environment)</span>
              <span className="text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded text-[10px]">Active</span>
            </div>
            <div className="text-indigo-400">$ pytest tests/ -v</div>
            <div className="text-slate-400">============================= test session starts =============================</div>
            <div className="text-slate-300">collected 3 items</div>
            <div className="text-emerald-400">tests/test_health.py::test_health_check_endpoint PASSED [ 33%]</div>
            <div className="text-emerald-400">tests/test_health.py::test_detailed_health_check_endpoint PASSED [ 66%]</div>
            <div className="text-emerald-400">tests/test_health.py::test_info_endpoint PASSED [100%]</div>
            <div className="text-emerald-300 font-bold">============================== 3 passed in 0.16s ==============================</div>
            <div className="flex items-center gap-1.5 text-indigo-400 mt-2">
              <span>$</span>
              <span className="animate-pulse inline-block w-2 h-3.5 bg-indigo-400" />
            </div>
          </div>
        )}

        {/* TAB: DEPENDENCIES */}
        {activeTab === "dependencies" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-4 pb-2 border-b border-slate-800">
              <div className="relative flex-1 max-w-sm">
                <Search className="h-3.5 w-3.5 text-slate-500 absolute left-2.5 top-2" />
                <input
                  type="text"
                  value={depSearch}
                  onChange={(e) => setDepSearch(e.target.value)}
                  placeholder="Filter project dependencies..."
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 pl-8 py-1 text-xs text-white placeholder:text-slate-600 outline-none focus:border-cyan-500"
                />
              </div>

              {onOpenGraph && (
                <button
                  onClick={onOpenGraph}
                  className="flex items-center gap-1.5 px-3 py-1 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/30 rounded text-xs font-semibold transition-colors"
                >
                  <Network className="h-3.5 w-3.5" />
                  <span>View as Interactive Graph</span>
                </button>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-[11px]">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800/80">
                    <th className="py-1 px-2">Module / File</th>
                    <th className="py-1 px-2">Depends On (Imports)</th>
                    <th className="py-1 px-2">Depended By (Callers)</th>
                    <th className="py-1 px-2 text-right">Coupling</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/40">
                  {filteredDeps.map((dep) => (
                    <tr key={dep.file} className="hover:bg-slate-900/40">
                      <td className="py-1.5 px-2 text-indigo-300 font-semibold">{dep.file}</td>
                      <td className="py-1.5 px-2 text-slate-300">
                        {dep.imports.length > 0 ? (
                          <span className="text-cyan-400">{dep.imports.join(", ")}</span>
                        ) : (
                          <span className="text-slate-600">none</span>
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-slate-300">
                        {dep.callers.length > 0 ? (
                          <span className="text-amber-400">{dep.callers.join(", ")}</span>
                        ) : (
                          <span className="text-slate-600">none</span>
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono text-slate-400">
                        {dep.imports.length + dep.callers.length} edges
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB: PROBLEMS */}
        {activeTab === "problems" && (
          <div className="text-slate-500 flex items-center justify-center h-full">
            No problems detected in the current workspace.
          </div>
        )}
      </div>
    </div>
  );
}
