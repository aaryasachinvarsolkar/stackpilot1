"use client";

import React, { useState } from "react";
import {
  Cpu,
  Search,
  FolderGit2,
  ChevronDown,
  Play,
  Hammer,
  GitBranch,
  SplitSquareVertical,
  SidebarClose,
  SidebarOpen,
  PanelBottom,
  Sparkles,
  Settings,
  Bell,
  Check,
  Plus,
  LayoutDashboard,
  Code2,
  ShieldCheck,
  FileText,
  FileCheck2,
  Split,
  Network,
} from "lucide-react";

interface NavbarProps {
  currentView?: "dashboard" | "workspace";
  onSwitchView?: (view: "dashboard" | "workspace") => void;
  onToggleLeftSidebar?: () => void;
  onToggleRightSidebar?: () => void;
  onToggleBottomPanel?: () => void;
  onRunTests?: () => void;
  onOpenCodeReview?: () => void;
  onOpenDocGen?: () => void;
  onOpenDiffReview?: () => void;
  onOpenDependencyGraph?: () => void;
  onOpenSettings?: () => void;
  onOpenNewProject?: () => void;
  selectedProjectName?: string;
  onSelectProject?: (name: string) => void;
}

export function Navbar({
  currentView = "workspace",
  onSwitchView,
  onToggleLeftSidebar,
  onToggleRightSidebar,
  onToggleBottomPanel,
  onRunTests,
  onOpenCodeReview,
  onOpenDocGen,
  onOpenDiffReview,
  onOpenDependencyGraph,
  onOpenSettings,
  onOpenNewProject,
  selectedProjectName = "task-manager-service",
  onSelectProject,
}: NavbarProps) {
  const [projectOpen, setProjectOpen] = useState(false);

  const projects = ["task-manager-service", "auth-microservice", "e-commerce-api"];

  return (
    <header className="h-12 w-full border-b border-slate-800 bg-[#090d16] select-none flex items-center justify-between px-3 z-50 text-xs">
      {/* Left: Brand, View Switcher & Project Selector */}
      <div className="flex items-center gap-3">
        <div
          onClick={() => onSwitchView && onSwitchView("dashboard")}
          className="flex items-center gap-2 font-bold tracking-tight text-white cursor-pointer hover:opacity-90"
        >
          <div className="h-7 w-7 rounded-lg bg-gradient-to-tr from-indigo-600 via-primary-500 to-cyan-400 p-[1px] shadow-glow flex items-center justify-center">
            <div className="h-full w-full bg-[#090d16] rounded-lg flex items-center justify-center">
              <Cpu className="h-4 w-4 text-indigo-400" />
            </div>
          </div>
          <span className="hidden sm:inline text-sm font-extrabold tracking-wide bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
            STACKPILOT
          </span>
        </div>

        {/* View Switcher: Dashboard <-> Workspace */}
        {onSwitchView && (
          <div className="flex items-center p-0.5 bg-slate-900 border border-slate-800 rounded-lg">
            <button
              onClick={() => onSwitchView("dashboard")}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                currentView === "dashboard"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
              title="Return to Projects Dashboard"
            >
              <LayoutDashboard className="h-3.5 w-3.5" />
              <span className="hidden md:inline">Dashboard</span>
            </button>
            <button
              onClick={() => onSwitchView("workspace")}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                currentView === "workspace"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
              title="Open 3-Pane Workspace IDE"
            >
              <Code2 className="h-3.5 w-3.5" />
              <span className="hidden md:inline">Workspace</span>
            </button>
          </div>
        )}

        {/* Project Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => setProjectOpen(!projectOpen)}
            className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-surface/80 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-colors"
          >
            <FolderGit2 className="h-3.5 w-3.5 text-indigo-400" />
            <span className="font-medium max-w-[140px] truncate">{selectedProjectName}</span>
            <ChevronDown className="h-3 w-3 text-slate-500" />
          </button>

          {projectOpen && (
            <div className="absolute left-0 top-9 w-56 rounded-lg bg-surface border border-slate-700 shadow-2xl py-1.5 z-50 backdrop-blur-xl">
              <div className="px-3 py-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                Workspaces
              </div>
              {projects.map((p) => (
                <div
                  key={p}
                  onClick={() => {
                    if (onSelectProject) onSelectProject(p);
                    setProjectOpen(false);
                  }}
                  className="flex items-center justify-between px-3 py-1.5 text-xs text-slate-300 hover:bg-indigo-600/20 hover:text-white cursor-pointer"
                >
                  <span className="truncate">{p}</span>
                  {selectedProjectName === p && <Check className="h-3.5 w-3.5 text-indigo-400" />}
                </div>
              ))}
              <div className="border-t border-slate-800 my-1" />
              <button
                onClick={() => {
                  setProjectOpen(false);
                  if (onOpenNewProject) onOpenNewProject();
                }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-indigo-400 hover:bg-slate-800 font-medium"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>New Project / Import...</span>
              </button>
            </div>
          )}
        </div>

        {/* Git Branch Pill */}
        <div className="hidden lg:flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400 font-mono text-[11px]">
          <GitBranch className="h-3 w-3 text-slate-500" />
          <span>main</span>
        </div>

        {/* Sandbox Status Badge */}
        <div className="hidden xl:flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-950/40 border border-emerald-500/30 text-emerald-400 font-mono text-[10px]">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>Sandbox: Isolated</span>
        </div>
      </div>

      {/* Center: Command Palette / Universal Codebase Search */}
      <div className="flex-1 max-w-sm lg:max-w-md mx-3 hidden sm:block">
        <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-slate-900/90 border border-slate-800 hover:border-slate-700 cursor-pointer text-slate-400 transition-colors">
          <Search className="h-3.5 w-3.5 text-slate-500" />
          <span className="text-xs text-slate-400 flex-1 truncate">
            Search symbols, files, or ask AI...
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
            Ctrl K
          </span>
        </div>
      </div>

      {/* Right: Actions, Modal Triggers & Panels */}
      <div className="flex items-center gap-1.5">
        {/* Code Review Modal Trigger */}
        {onOpenCodeReview && (
          <button
            onClick={onOpenCodeReview}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-surface hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800 font-medium transition-colors"
            title="Open Code Review Audit Panel"
          >
            <FileCheck2 className="h-3.5 w-3.5 text-amber-400" />
            <span className="hidden xl:inline">Review</span>
          </button>
        )}

        {/* DocGen Modal Trigger */}
        {onOpenDocGen && (
          <button
            onClick={onOpenDocGen}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-surface hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800 font-medium transition-colors"
            title="Generate & Edit Documentation"
          >
            <FileText className="h-3.5 w-3.5 text-cyan-400" />
            <span className="hidden xl:inline">Docs</span>
          </button>
        )}

        {/* Diff Review Modal Trigger */}
        {onOpenDiffReview && (
          <button
            onClick={onOpenDiffReview}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-surface hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800 font-medium transition-colors"
            title="Review AI Generated Diffs"
          >
            <Split className="h-3.5 w-3.5 text-indigo-400" />
            <span className="hidden xl:inline">Diffs</span>
          </button>
        )}

        {/* Dependency Graph Modal Trigger */}
        {onOpenDependencyGraph && (
          <button
            onClick={onOpenDependencyGraph}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-surface hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800 font-medium transition-colors"
            title="Interactive Codebase Dependency Graph"
          >
            <Network className="h-3.5 w-3.5 text-purple-400" />
            <span className="hidden xl:inline">Graph</span>
          </button>
        )}

        {/* Run Tests Button */}
        <button
          onClick={onRunTests}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 border border-emerald-500/30 font-medium transition-colors"
          title="Run project test suite in sandbox"
        >
          <Play className="h-3 w-3 fill-emerald-400 text-emerald-400" />
          <span className="hidden md:inline">Run Tests</span>
        </button>

        <div className="h-4 w-[1px] bg-slate-800 mx-1 hidden sm:block" />

        {/* Panel Toggles */}
        <button
          onClick={onToggleBottomPanel}
          className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
          title="Toggle Terminal & Dock"
        >
          <PanelBottom className="h-4 w-4" />
        </button>

        <button
          onClick={onToggleRightSidebar}
          className="p-1.5 rounded hover:bg-indigo-600/20 text-indigo-400 hover:text-indigo-300"
          title="Toggle AI Copilot Panel"
        >
          <Sparkles className="h-4 w-4" />
        </button>

        {/* Settings Modal Trigger */}
        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title="Project Memory & Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        )}

        {/* User Profile */}
        <div className="h-7 w-7 rounded-full bg-gradient-to-tr from-indigo-500 to-cyan-500 p-[1px] ml-1">
          <div className="h-full w-full rounded-full bg-slate-900 flex items-center justify-center font-bold text-[10px] text-white">
            SP
          </div>
        </div>
      </div>
    </header>
  );
}
