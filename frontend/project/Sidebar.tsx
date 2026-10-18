"use client";

import React, { useState } from "react";
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  Search,
  ChevronRight,
  ChevronDown,
  Plus,
  RefreshCw,
  Upload,
  GitBranch,
  GitCommit,
  PlayCircle,
  Sparkles,
  Edit2,
  Trash2,
  FilePlus,
} from "lucide-react";
import { SidebarView } from "@/components/ActivityBar";

interface SidebarProps {
  activeView: SidebarView;
  selectedFile: string;
  onSelectFile: (file: string) => void;
  isOpen: boolean;
  onUploadClick?: () => void;
}

interface ContextMenuState {
  x: number;
  y: number;
  fileName: string;
}

export function Sidebar({ activeView, selectedFile, onSelectFile, isOpen, onUploadClick }: SidebarProps) {
  const [openFolders, setOpenFolders] = useState<Record<string, boolean>>({
    app: true,
    api: true,
    controllers: true,
    middleware: true,
    tests: true,
  });

  const [searchQuery, setSearchQuery] = useState("");
  const [commitMessage, setCommitMessage] = useState("");
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  if (!isOpen) return null;

  const toggleFolder = (name: string) => {
    setOpenFolders((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  const handleContextMenu = (e: React.MouseEvent, fileName: string) => {
    e.preventDefault();
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      fileName,
    });
  };

  const closeContextMenu = () => {
    setContextMenu(null);
  };

  return (
    <aside
      onClick={closeContextMenu}
      className="w-64 h-full bg-[#0b101b] border-r border-slate-800 flex flex-col select-none text-xs z-20 relative"
    >
      {/* ---------------------------------------------------- */}
      {/* 1. FILE EXPLORER VIEW                                */}
      {/* ---------------------------------------------------- */}
      {activeView === "files" && (
        <>
          <div className="p-3 border-b border-slate-800 flex items-center justify-between">
            <span className="font-bold uppercase tracking-wider text-slate-300">EXPLORER</span>
            <div className="flex items-center gap-1">
              <button className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white" title="New File">
                <Plus className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={onUploadClick}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
                title="Upload Archive"
              >
                <Upload className="h-3.5 w-3.5" />
              </button>
              <button className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white" title="Refresh">
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div className="p-2 border-b border-slate-800/80">
            <div className="flex items-center gap-1.5 px-2 py-1 bg-slate-900 border border-slate-800 rounded-md">
              <Search className="h-3.5 w-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search files by name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-transparent border-none outline-none text-slate-200 w-full placeholder:text-slate-600 text-xs font-sans"
              />
            </div>
          </div>

          <div className="flex-1 p-2 overflow-y-auto font-mono">
            <div className="text-[10px] font-semibold text-slate-500 px-2 py-1 uppercase tracking-wider">
              WORKSPACE
            </div>

            {/* Folder: app */}
            <div>
              <div
                onClick={() => toggleFolder("app")}
                className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800/60 cursor-pointer text-slate-300"
              >
                {openFolders.app ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                {openFolders.app ? <FolderOpen className="h-3.5 w-3.5 text-indigo-400" /> : <Folder className="h-3.5 w-3.5 text-indigo-400" />}
                <span>app</span>
              </div>

              {openFolders.app && (
                <div className="pl-4 border-l border-slate-800/80 ml-2.5 space-y-0.5 mt-0.5">
                  {/* api */}
                  <div
                    onClick={() => toggleFolder("api")}
                    className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800/60 cursor-pointer text-slate-300"
                  >
                    {openFolders.api ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                    {openFolders.api ? <FolderOpen className="h-3.5 w-3.5 text-indigo-400" /> : <Folder className="h-3.5 w-3.5 text-indigo-400" />}
                    <span>api</span>
                  </div>

                  {openFolders.api && (
                    <div className="pl-4 border-l border-slate-800/80 ml-2.5 space-y-0.5">
                      <div
                        onClick={() => onSelectFile("routes.py")}
                        onContextMenu={(e) => handleContextMenu(e, "routes.py")}
                        className={`flex items-center justify-between px-2 py-1 rounded cursor-pointer ${
                          selectedFile === "routes.py"
                            ? "bg-indigo-600/20 text-indigo-300 font-semibold"
                            : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <FileCode className="h-3.5 w-3.5 text-cyan-400" />
                          <span>routes.py</span>
                        </div>
                        {/* Pending AI Change Indicator Dot */}
                        <div className="flex items-center gap-1">
                          <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" title="Pending AI Changes" />
                          <span className="text-[10px] text-amber-400 font-bold">M</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* middleware */}
                  <div
                    onClick={() => toggleFolder("middleware")}
                    className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800/60 cursor-pointer text-slate-300"
                  >
                    {openFolders.middleware ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                    {openFolders.middleware ? <FolderOpen className="h-3.5 w-3.5 text-indigo-400" /> : <Folder className="h-3.5 w-3.5 text-indigo-400" />}
                    <span>middleware</span>
                  </div>

                  {openFolders.middleware && (
                    <div className="pl-4 border-l border-slate-800/80 ml-2.5 space-y-0.5">
                      <div
                        onClick={() => onSelectFile("rateLimiter.ts")}
                        onContextMenu={(e) => handleContextMenu(e, "rateLimiter.ts")}
                        className={`flex items-center justify-between px-2 py-1 rounded cursor-pointer ${
                          selectedFile === "rateLimiter.ts"
                            ? "bg-indigo-600/20 text-indigo-300 font-semibold"
                            : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <FileCode className="h-3.5 w-3.5 text-emerald-400" />
                          <span>rateLimiter.ts</span>
                        </div>
                        {/* AI Created File Indicator */}
                        <div className="flex items-center gap-1">
                          <span className="h-2 w-2 rounded-full bg-emerald-400" title="Created by AI Agent" />
                          <span className="text-[10px] text-emerald-400 font-bold">U</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Top-level files */}
                  <div
                    onClick={() => onSelectFile("main.py")}
                    onContextMenu={(e) => handleContextMenu(e, "main.py")}
                    className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer ${
                      selectedFile === "main.py"
                        ? "bg-indigo-600/20 text-indigo-300 font-semibold"
                        : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                    }`}
                  >
                    <FileCode className="h-3.5 w-3.5 text-cyan-400" />
                    <span>main.py</span>
                  </div>

                  <div
                    onClick={() => onSelectFile("config.py")}
                    onContextMenu={(e) => handleContextMenu(e, "config.py")}
                    className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer ${
                      selectedFile === "config.py"
                        ? "bg-indigo-600/20 text-indigo-300 font-semibold"
                        : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                    }`}
                  >
                    <FileCode className="h-3.5 w-3.5 text-cyan-400" />
                    <span>config.py</span>
                  </div>
                </div>
              )}
            </div>

            {/* Folder: tests */}
            <div>
              <div
                onClick={() => toggleFolder("tests")}
                className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-slate-800/60 cursor-pointer text-slate-300"
              >
                {openFolders.tests ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                {openFolders.tests ? <FolderOpen className="h-3.5 w-3.5 text-indigo-400" /> : <Folder className="h-3.5 w-3.5 text-indigo-400" />}
                <span>tests</span>
              </div>

              {openFolders.tests && (
                <div className="pl-4 border-l border-slate-800/80 ml-2.5 space-y-0.5">
                  <div
                    onClick={() => onSelectFile("test_health.py")}
                    onContextMenu={(e) => handleContextMenu(e, "test_health.py")}
                    className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer ${
                      selectedFile === "test_health.py"
                        ? "bg-indigo-600/20 text-indigo-300 font-semibold"
                        : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                    }`}
                  >
                    <FileCode className="h-3.5 w-3.5 text-amber-400" />
                    <span>test_health.py</span>
                  </div>
                </div>
              )}
            </div>

            {/* requirements.txt */}
            <div
              onClick={() => onSelectFile("requirements.txt")}
              onContextMenu={(e) => handleContextMenu(e, "requirements.txt")}
              className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer ${
                selectedFile === "requirements.txt"
                  ? "bg-indigo-600/20 text-indigo-300 font-semibold"
                  : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
              }`}
            >
              <FileText className="h-3.5 w-3.5 text-slate-400" />
              <span>requirements.txt</span>
            </div>
          </div>
        </>
      )}

      {/* ---------------------------------------------------- */}
      {/* 2. SOURCE CONTROL (GIT) VIEW                        */}
      {/* ---------------------------------------------------- */}
      {activeView === "git" && (
        <div className="flex-1 flex flex-col p-3 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="font-bold uppercase tracking-wider text-slate-300">SOURCE CONTROL</span>
            <div className="flex items-center gap-1 font-mono text-[11px] text-slate-400">
              <GitBranch className="h-3.5 w-3.5 text-indigo-400" />
              <span>main</span>
            </div>
          </div>

          <div className="space-y-2">
            <textarea
              value={commitMessage}
              onChange={(e) => setCommitMessage(e.target.value)}
              placeholder="Commit message (e.g. feat: add rate limiter)..."
              rows={3}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-white placeholder:text-slate-600 outline-none focus:border-indigo-500 font-mono resize-none"
            />
            <button className="w-full py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white font-semibold transition-colors flex items-center justify-center gap-1.5 shadow-glow">
              <GitCommit className="h-3.5 w-3.5" />
              <span>Commit Changes</span>
            </button>
          </div>

          <div className="space-y-2 flex-1 overflow-y-auto">
            <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              <span>CHANGES</span>
              <span className="text-indigo-400 font-mono">2 files</span>
            </div>

            <div
              onClick={() => onSelectFile("routes.py")}
              className="flex items-center justify-between p-2 rounded-lg bg-surface hover:bg-slate-800/60 cursor-pointer border border-slate-800"
            >
              <div className="flex items-center gap-2">
                <FileCode className="h-3.5 w-3.5 text-cyan-400" />
                <span className="font-mono text-xs text-slate-200">routes.py</span>
              </div>
              <span className="text-[10px] font-bold text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded">
                MODIFIED
              </span>
            </div>

            <div
              onClick={() => onSelectFile("rateLimiter.ts")}
              className="flex items-center justify-between p-2 rounded-lg bg-surface hover:bg-slate-800/60 cursor-pointer border border-slate-800"
            >
              <div className="flex items-center gap-2">
                <FileCode className="h-3.5 w-3.5 text-emerald-400" />
                <span className="font-mono text-xs text-slate-200">rateLimiter.ts</span>
              </div>
              <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                UNTRACKED
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 3. SEMANTIC CODEBASE SEARCH VIEW                     */}
      {/* ---------------------------------------------------- */}
      {activeView === "search" && (
        <div className="flex-1 flex flex-col p-3 space-y-3">
          <div className="font-bold uppercase tracking-wider text-slate-300 border-b border-slate-800 pb-2">
            SEMANTIC SEARCH
          </div>

          <div className="relative">
            <Search className="h-3.5 w-3.5 text-slate-500 absolute left-2.5 top-2.5" />
            <input
              type="text"
              placeholder="e.g. detailed health check route"
              className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder:text-slate-600 outline-none focus:border-indigo-500"
            />
          </div>

          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            SEARCH RESULTS (RAG)
          </div>

          <div className="space-y-2 overflow-y-auto flex-1 font-mono text-xs">
            <div
              onClick={() => onSelectFile("routes.py")}
              className="p-2 rounded-lg bg-surface border border-slate-800 hover:border-indigo-500/40 cursor-pointer"
            >
              <div className="flex items-center justify-between text-indigo-300 font-semibold">
                <span>detailed_health()</span>
                <span className="text-[10px] text-slate-500">score: 0.94</span>
              </div>
              <div className="text-slate-400 text-[11px] mt-1">app/api/routes.py:20</div>
            </div>

            <div
              onClick={() => onSelectFile("main.py")}
              className="p-2 rounded-lg bg-surface border border-slate-800 hover:border-indigo-500/40 cursor-pointer"
            >
              <div className="flex items-center justify-between text-indigo-300 font-semibold">
                <span>app.include_router</span>
                <span className="text-[10px] text-slate-500">score: 0.88</span>
              </div>
              <div className="text-slate-400 text-[11px] mt-1">app/main.py:42</div>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 4. SANDBOX TEST RUNNER VIEW                          */}
      {/* ---------------------------------------------------- */}
      {activeView === "tests" && (
        <div className="flex-1 flex flex-col p-3 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="font-bold uppercase tracking-wider text-slate-300">TEST SUITES</span>
            <button className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-600 text-white font-semibold text-[10px]">
              <PlayCircle className="h-3 w-3" />
              <span>Run All</span>
            </button>
          </div>

          <div className="space-y-2 flex-1 overflow-y-auto font-mono text-xs">
            <div className="p-2.5 rounded-lg bg-surface border border-slate-800 space-y-1.5">
              <div className="flex items-center justify-between font-semibold text-white">
                <span className="truncate">tests/test_health.py</span>
                <span className="text-emerald-400 text-[10px]">PASSED</span>
              </div>
              <div className="text-[11px] text-slate-400 flex items-center justify-between">
                <span>3 tests</span>
                <span>0.16s</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* RIGHT-CLICK CONTEXT MENU (Section 5a)                */}
      {/* ---------------------------------------------------- */}
      {contextMenu && (
        <div
          className="fixed z-50 w-44 rounded-lg bg-slate-900 border border-slate-700 shadow-2xl py-1 text-xs text-slate-300 backdrop-blur-xl select-none"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-3 py-1 text-[10px] font-mono text-slate-500 truncate border-b border-slate-800 mb-1">
            {contextMenu.fileName}
          </div>
          <button
            onClick={() => closeContextMenu()}
            className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-indigo-600 hover:text-white"
          >
            <FilePlus className="h-3.5 w-3.5" />
            <span>New File Here</span>
          </button>
          <button
            onClick={() => closeContextMenu()}
            className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-indigo-600 hover:text-white"
          >
            <Edit2 className="h-3.5 w-3.5" />
            <span>Rename File</span>
          </button>
          <button
            onClick={() => closeContextMenu()}
            className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-rose-600 hover:text-white text-rose-400"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>Delete File</span>
          </button>
        </div>
      )}
    </aside>
  );
}
