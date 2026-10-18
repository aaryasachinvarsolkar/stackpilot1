"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, Cpu, FileCode, Layers, Minimize2, Sparkles, Database, ArrowRight } from "lucide-react";

interface IndexingProgressModalProps {
  projectName: string;
  isOpen: boolean;
  onComplete: () => void;
  onRunInBackground: () => void;
}

export function IndexingProgressModal({
  projectName,
  isOpen,
  onComplete,
  onRunInBackground,
}: IndexingProgressModalProps) {
  const [progress, setProgress] = useState(15);
  const [scannedFiles, setScannedFiles] = useState(12);
  const [processedFiles, setProcessedFiles] = useState(8);
  const [functionsDetected, setFunctionsDetected] = useState(34);
  const [chunksCreated, setChunksCreated] = useState(62);
  const [currentFile, setCurrentFile] = useState("app/api/routes.py");
  const [isDone, setIsDone] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          setIsDone(true);
          return 100;
        }

        const next = prev + 15;
        setScannedFiles((s) => s + 4);
        setProcessedFiles((p) => p + 3);
        setFunctionsDetected((f) => f + 12);
        setChunksCreated((c) => c + 18);

        const files = [
          "app/database/connection.py",
          "app/models/base.py",
          "app/middleware/rateLimiter.ts",
          "tests/test_health.py",
          "app/main.py",
        ];
        setCurrentFile(files[Math.floor(Math.random() * files.length)] || "app/main.py");

        if (next >= 100) {
          clearInterval(interval);
          setIsDone(true);
          return 100;
        }
        return next;
      });
    }, 600);

    return () => clearInterval(interval);
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md select-none animate-in fade-in duration-150">
      <div className="w-full max-w-lg bg-surface border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Cpu className={`h-5 w-5 ${isDone ? "text-emerald-400" : "animate-spin"}`} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                {isDone ? "Codebase Indexing Complete" : `Indexing ${projectName}...`}
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                {isDone
                  ? "AST semantic graph and vector embeddings are ready"
                  : "Parsing AST symbols & generating vector embeddings"}
              </p>
            </div>
          </div>

          <button
            onClick={onRunInBackground}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title="Minimize & run in background"
          >
            <Minimize2 className="h-4 w-4" />
          </button>
        </div>

        {/* Progress Bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-mono">
            <span className="text-slate-400">Progress</span>
            <span className="text-white font-bold">{progress}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-slate-900 overflow-hidden border border-slate-800">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 via-primary-500 to-cyan-400 transition-all duration-300 shadow-glow"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-[11px] font-mono text-slate-500 truncate">
            {isDone ? "Ready for queries" : `Parsing AST: ${currentFile}`}
          </p>
        </div>

        {/* Live Indexing Telemetry Grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80">
            <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
              <FileCode className="h-3.5 w-3.5 text-indigo-400" />
              <span>Files Scanned</span>
            </div>
            <div className="text-lg font-bold text-white font-mono">{scannedFiles}</div>
          </div>

          <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80">
            <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-cyan-400" />
              <span>Files Processed</span>
            </div>
            <div className="text-lg font-bold text-white font-mono">{processedFiles}</div>
          </div>

          <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80">
            <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
              <Sparkles className="h-3.5 w-3.5 text-amber-400" />
              <span>AST Functions</span>
            </div>
            <div className="text-lg font-bold text-white font-mono">{functionsDetected}</div>
          </div>

          <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80">
            <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
              <Database className="h-3.5 w-3.5 text-emerald-400" />
              <span>Vector Chunks</span>
            </div>
            <div className="text-lg font-bold text-white font-mono">{chunksCreated}</div>
          </div>
        </div>

        {/* Bottom Actions */}
        <div className="pt-2 flex items-center justify-between">
          <button
            onClick={onRunInBackground}
            className="text-xs text-slate-400 hover:text-white underline decoration-slate-600 underline-offset-4"
          >
            Run in background
          </button>

          {isDone ? (
            <button
              onClick={onComplete}
              className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center gap-2 shadow-glow transition-all"
            >
              <span>Open Workspace</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          ) : (
            <span className="text-xs text-slate-500 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-indigo-500 animate-ping" />
              Analyzing repository...
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
