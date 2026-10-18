"use client";

import React, { useState } from "react";
import {
  X,
  Split,
  Eye,
  CheckCircle2,
  XCircle,
  FileCode,
  Sparkles,
  ArrowRight,
  Play,
  RotateCcw,
  Check,
} from "lucide-react";

interface DiffFile {
  name: string;
  path: string;
  summary: string;
  status: "pending" | "accepted" | "rejected";
  before: string[];
  after: string[];
}

interface DiffReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAcceptAll: () => void;
  onRunTests: () => void;
}

const SAMPLE_DIFFS: DiffFile[] = [
  {
    name: "routes.py",
    path: "app/api/routes.py",
    summary: "Add readiness health probe and database ping check per implementation plan step 1.",
    status: "pending",
    before: [
      `@router.get("/health")`,
      `async def health():`,
      `    return {"status": "ok"}`,
    ],
    after: [
      `@router.get("/api/health", summary="Detailed Readiness Probe")`,
      `async def detailed_health():`,
      `    """Readiness probe checking database connectivity and environment details."""`,
      `    db_status = await check_database_connection()`,
      `    return {`,
      `        "status": "healthy" if db_status["status"] == "connected" else "degraded",`,
      `        "database": db_status["status"],`,
      `        "database_type": db_status.get("type", "unknown"),`,
      `        "version": "0.1.0",`,
      `    }`,
    ],
  },
  {
    name: "rateLimiter.ts",
    path: "app/middleware/rateLimiter.ts",
    summary: "Create token bucket in-memory rate limiter per implementation plan step 2.",
    status: "pending",
    before: [],
    after: [
      `import { Request, Response, NextFunction } from "express";`,
      `export function rateLimiter(limit = 100, windowMs = 60000) {`,
      `  return (req: Request, res: Response, next: NextFunction) => {`,
      `    // Enforce request rate limit per IP client`,
      `    next();`,
      `  };`,
      `}`,
    ],
  },
];

export function DiffReviewModal({ isOpen, onClose, onAcceptAll, onRunTests }: DiffReviewModalProps) {
  const [files, setFiles] = useState<DiffFile[]>(SAMPLE_DIFFS);
  const [activeFileIndex, setActiveFileIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"unified" | "split">("unified");
  const [showPostAcceptPrompt, setShowPostAcceptPrompt] = useState(false);

  if (!isOpen) return null;

  const currentFile = files[activeFileIndex] || files[0];

  const handleDecision = (index: number, decision: "accepted" | "rejected") => {
    setFiles((prev) =>
      prev.map((f, i) => (i === index ? { ...f, status: decision } : f))
    );
  };

  const handleAcceptAllAndPrompt = () => {
    setFiles((prev) => prev.map((f) => ({ ...f, status: "accepted" })));
    setShowPostAcceptPrompt(true);
    onAcceptAll();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md select-none animate-in fade-in duration-150">
      <div className="w-full max-w-5xl h-[85vh] bg-surface border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Split className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <span>AI Proposed Modifications Review</span>
                <span className="text-xs font-mono font-normal px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                  {files.length} files modified
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Review code changes before applying to project workspace
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* View Mode Toggle */}
            <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs">
              <button
                onClick={() => setViewMode("unified")}
                className={`px-2.5 py-1 rounded font-medium ${
                  viewMode === "unified" ? "bg-indigo-600 text-white font-semibold" : "text-slate-400 hover:text-white"
                }`}
              >
                Unified Diff
              </button>
              <button
                onClick={() => setViewMode("split")}
                className={`px-2.5 py-1 rounded font-medium ${
                  viewMode === "split" ? "bg-indigo-600 text-white font-semibold" : "text-slate-400 hover:text-white"
                }`}
              >
                Side-by-Side
              </button>
            </div>

            <button
              onClick={handleAcceptAllAndPrompt}
              className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors"
            >
              <CheckCircle2 className="h-4 w-4" />
              <span>Accept All Changes</span>
            </button>

            <button
              onClick={() => {
                setFiles((prev) => prev.map((f) => ({ ...f, status: "rejected" })));
                onClose();
              }}
              className="px-3 py-1.5 bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 text-xs font-semibold rounded-lg border border-rose-500/30 transition-colors"
            >
              Reject All
            </button>

            <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Post Accept Verification Prompt Bar */}
        {showPostAcceptPrompt && (
          <div className="p-3 bg-emerald-950/40 border-b border-emerald-500/40 flex items-center justify-between text-xs text-emerald-300 animate-in slide-in-from-top-1">
            <span className="flex items-center gap-2 font-medium">
              <Check className="h-4 w-4 text-emerald-400" />
              Changes accepted into workspace! Would you like to run automated sandbox tests to verify nothing broke?
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  onRunTests();
                  onClose();
                }}
                className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg flex items-center gap-1 shadow-sm"
              >
                <Play className="h-3 w-3 fill-white" />
                <span>Run Sandbox Tests Now</span>
              </button>
              <button onClick={() => setShowPostAcceptPrompt(false)} className="text-slate-400 hover:text-white">
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Main Body */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left File List */}
          <div className="w-64 border-r border-slate-800 bg-[#080c14] flex flex-col p-3 space-y-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              MODIFIED FILES ({files.length})
            </span>

            <div className="space-y-1.5 flex-1 overflow-y-auto font-mono text-xs">
              {files.map((file, idx) => (
                <div
                  key={file.path}
                  onClick={() => setActiveFileIndex(idx)}
                  className={`p-2.5 rounded-xl border cursor-pointer transition-colors ${
                    activeFileIndex === idx
                      ? "bg-indigo-600/20 border-indigo-500/50 text-white font-semibold"
                      : "bg-surface/50 border-slate-800/80 text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate">{file.name}</span>
                    {file.status === "accepted" && <span className="text-emerald-400 text-[10px]">ACCEPTED</span>}
                    {file.status === "rejected" && <span className="text-rose-400 text-[10px]">REJECTED</span>}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5 truncate">{file.path}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Diff Viewer */}
          <div className="flex-1 flex flex-col bg-[#070b13] overflow-hidden">
            {/* Why Agent Changed This - Summary Header */}
            <div className="p-3 border-b border-slate-800/80 bg-slate-900/40 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-indigo-400" />
                <span className="text-slate-400">Agent Rationale:</span>
                <span className="text-white font-medium">{currentFile.summary}</span>
              </div>

              {/* Per-File Decision Buttons */}
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleDecision(activeFileIndex, "accepted")}
                  className={`px-2.5 py-1 rounded text-xs font-semibold flex items-center gap-1 transition-colors ${
                    currentFile.status === "accepted"
                      ? "bg-emerald-600 text-white"
                      : "bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30"
                  }`}
                >
                  <Check className="h-3.5 w-3.5" />
                  <span>Accept File</span>
                </button>
                <button
                  onClick={() => handleDecision(activeFileIndex, "rejected")}
                  className={`px-2.5 py-1 rounded text-xs font-semibold flex items-center gap-1 transition-colors ${
                    currentFile.status === "rejected"
                      ? "bg-rose-600 text-white"
                      : "bg-rose-600/20 text-rose-400 hover:bg-rose-600/30"
                  }`}
                >
                  <X className="h-3.5 w-3.5" />
                  <span>Reject File</span>
                </button>
              </div>
            </div>

            {/* Diff Lines Body */}
            <div className="flex-1 p-4 overflow-auto font-mono text-xs space-y-1">
              {viewMode === "unified" ? (
                <div>
                  {currentFile.before.map((line, idx) => (
                    <div key={`del-${idx}`} className="bg-rose-950/20 border-l-2 border-rose-500 px-3 py-0.5 text-rose-300">
                      <span className="text-rose-500 select-none mr-3">-</span>
                      <span>{line}</span>
                    </div>
                  ))}
                  {currentFile.after.map((line, idx) => (
                    <div key={`add-${idx}`} className="bg-emerald-950/20 border-l-2 border-emerald-500 px-3 py-0.5 text-emerald-300">
                      <span className="text-emerald-500 select-none mr-3">+</span>
                      <span>{line}</span>
                    </div>
                  ))}
                </div>
              ) : (
                /* Split Side-by-Side View */
                <div className="grid grid-cols-2 gap-2 h-full">
                  <div className="border border-slate-800 rounded-lg p-3 bg-slate-950/60 overflow-auto">
                    <div className="text-[10px] text-slate-500 font-bold uppercase mb-2">Original (Before)</div>
                    {currentFile.before.length > 0 ? (
                      currentFile.before.map((line, idx) => (
                        <div key={idx} className="text-rose-300 bg-rose-950/20 px-2 py-0.5 rounded">
                          {line}
                        </div>
                      ))
                    ) : (
                      <div className="text-slate-600 italic">File did not exist previously (New file)</div>
                    )}
                  </div>

                  <div className="border border-slate-800 rounded-lg p-3 bg-slate-950/60 overflow-auto">
                    <div className="text-[10px] text-slate-500 font-bold uppercase mb-2">Proposed (After)</div>
                    {currentFile.after.map((line, idx) => (
                      <div key={idx} className="text-emerald-300 bg-emerald-950/20 px-2 py-0.5 rounded">
                        {line}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
