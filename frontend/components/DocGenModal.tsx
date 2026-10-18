"use client";

import React, { useState } from "react";
import { X, BookOpen, Save, Sparkles, FileText, Check, Copy } from "lucide-react";

export type DocType = "readme" | "api" | "architecture" | "functions";

interface DocGenModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaveToProject: (docType: DocType, content: string) => void;
}

const TEMPLATES: Record<DocType, { title: string; defaultContent: string }> = {
  readme: {
    title: "README.md",
    defaultContent: `# Project Documentation\n\n## Overview\nThis service provides high-performance API endpoints for task orchestration and health monitoring.\n\n## Quick Start\n\`\`\`bash\npip install -r requirements.txt\nuvicorn app.main:app --reload\n\`\`\`\n\n## Architecture\n- FastAPI Async Engine\n- PostgreSQL + pgvector Storage\n- Sandboxed Docker Runner`,
  },
  api: {
    title: "API_DOCUMENTATION.md",
    defaultContent: `# REST API Endpoints\n\n### GET /health\nLiveness probe.\n- Returns: 200 OK\n\n### GET /api/health\nReadiness check verifying database and storage connectivity.\n\n### POST /api/tasks\nEnqueue background computation jobs.`,
  },
  architecture: {
    title: "ARCHITECTURE_EXPLANATION.md",
    defaultContent: `# System Architecture\n\n## Data Flow\n1. Incoming requests enter FastAPI middleware\n2. AST parser analyzes repository structure\n3. Dense vector embeddings are retrieved via pgvector\n4. Sandboxed Docker container executes tests safely`,
  },
  functions: {
    title: "FUNCTION_REFERENCE.md",
    defaultContent: `# Function Reference\n\n### detailed_health()\nDefined in: app/api/routes.py:20\n- Checks active database connectivity.\n- Returns latency benchmarks and dialect type.\n\n### check_database_connection()\nDefined in: app/database/connection.py:27\n- Executes SELECT 1 test query on session pool.`,
  },
};

export function DocGenModal({ isOpen, onClose, onSaveToProject }: DocGenModalProps) {
  const [selectedType, setSelectedType] = useState<DocType>("readme");
  const [content, setContent] = useState(TEMPLATES.readme.defaultContent);
  const [isGenerating, setIsGenerating] = useState(false);
  const [saved, setSaved] = useState(false);

  if (!isOpen) return null;

  const handleSelectType = (type: DocType) => {
    setSelectedType(type);
    setContent(TEMPLATES[type].defaultContent);
    setSaved(false);
  };

  const handleGenerate = (type: DocType) => {
    setIsGenerating(true);
    setTimeout(() => {
      setContent(TEMPLATES[type].defaultContent + `\n\n<!-- Generated automatically by STACKPILOT at ${new Date().toLocaleTimeString()} -->`);
      setIsGenerating(false);
    }, 800);
  };

  const handleSave = () => {
    onSaveToProject(selectedType, content);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md select-none animate-in fade-in duration-150">
      <div className="w-full max-w-5xl h-[85vh] bg-surface border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
              <BookOpen className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Documentation Synthesis</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Automatically generate Markdown documentation based on indexed project AST
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors"
            >
              {saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
              <span>{saved ? "Saved to Project!" : "Save to Project"}</span>
            </button>
            <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-white rounded-lg">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Generator Controls */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800 bg-[#080c14] text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mr-2">Doc Type:</span>
            {(["readme", "api", "architecture", "functions"] as DocType[]).map((t) => (
              <button
                key={t}
                onClick={() => handleSelectType(t)}
                className={`px-3 py-1 rounded-lg font-medium transition-colors uppercase text-[11px] ${
                  selectedType === t
                    ? "bg-indigo-600 text-white font-semibold shadow-sm"
                    : "text-slate-400 hover:text-white hover:bg-slate-800/40"
                }`}
              >
                {t === "readme" ? "README.md" : t === "api" ? "API Docs" : t === "architecture" ? "Architecture" : "Function Docs"}
              </button>
            ))}
          </div>

          <button
            onClick={() => handleGenerate(selectedType)}
            disabled={isGenerating}
            className="flex items-center gap-1.5 px-3 py-1 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 rounded-lg text-xs font-semibold transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            <span>{isGenerating ? "Synthesizing..." : "Regenerate from AST"}</span>
          </button>
        </div>

        {/* Split View: Live Markdown Editor on Left | Rendered Preview on Right */}
        <div className="flex-1 grid grid-cols-2 divide-x divide-slate-800 overflow-hidden">
          {/* Markdown Source Editor */}
          <div className="flex flex-col bg-[#070a12]">
            <div className="p-2 border-b border-slate-800/80 text-[11px] font-mono text-slate-400 bg-slate-950/40">
              Markdown Source (Editable)
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="flex-1 p-4 bg-transparent text-slate-200 font-mono text-xs outline-none resize-none leading-relaxed"
            />
          </div>

          {/* Rendered Preview */}
          <div className="flex flex-col bg-[#090d16] overflow-hidden">
            <div className="p-2 border-b border-slate-800/80 text-[11px] font-mono text-slate-400 bg-slate-950/40">
              Rendered Documentation Preview
            </div>
            <div className="flex-1 p-6 overflow-y-auto space-y-4 text-xs text-slate-200 font-sans prose prose-invert max-w-none">
              <pre className="p-4 rounded-xl bg-slate-900 border border-slate-800 font-mono text-xs whitespace-pre-wrap">
                {content}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
