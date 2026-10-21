"use client";

import React from "react";
import { Cpu, LayoutDashboard, Code2, FolderGit2 } from "lucide-react";

interface NavbarProps {
  currentView: "dashboard" | "workspace";
  onSwitchView: (view: "dashboard" | "workspace") => void;
  /** Name of the project that is open in the workspace, or "" if none. */
  projectLabel: string;
}

// Only controls that do something are shown. Review / docs / test-runner / settings buttons were removed:
// their features do not exist yet, and a button that cannot work should not look like one that can.
export function Navbar({ currentView, onSwitchView, projectLabel }: NavbarProps) {
  return (
    <header className="h-12 w-full shrink-0 border-b border-slate-800 bg-[#090d16] select-none flex items-center justify-between px-3 z-50 text-xs">
      <div className="flex items-center gap-3 min-w-0">
        <button onClick={() => onSwitchView("dashboard")} className="flex items-center gap-2 font-bold tracking-tight text-white hover:opacity-90" aria-label="StackPilot home">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-tr from-indigo-600 via-primary-500 to-cyan-400 p-[1px] shadow-glow flex items-center justify-center">
            <div className="h-full w-full bg-[#090d16] rounded-lg flex items-center justify-center">
              <Cpu className="h-4 w-4 text-indigo-400" />
            </div>
          </div>
          <span className="hidden sm:inline text-sm font-extrabold tracking-wide bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">STACKPILOT</span>
        </button>

        <div className="flex items-center p-0.5 bg-slate-900 border border-slate-800 rounded-lg">
          <button
            onClick={() => onSwitchView("dashboard")}
            data-testid="nav-dashboard"
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-colors ${currentView === "dashboard" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"}`}
          >
            <LayoutDashboard className="h-3.5 w-3.5" />
            <span>Dashboard</span>
          </button>
          <button
            onClick={() => onSwitchView("workspace")}
            data-testid="nav-workspace"
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-colors ${currentView === "workspace" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"}`}
          >
            <Code2 className="h-3.5 w-3.5" />
            <span>Workspace</span>
          </button>
        </div>

        <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-surface/80 border border-slate-800 text-slate-300 min-w-0" data-testid="nav-project">
          <FolderGit2 className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
          <span className="font-medium max-w-[220px] truncate">{projectLabel || "No project open"}</span>
        </div>
      </div>

      <span className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 text-[10px] font-semibold tracking-wide" data-testid="prototype-badge" title="Features marked 'sample' use illustrative data">
        PROTOTYPE
      </span>
    </header>
  );
}
