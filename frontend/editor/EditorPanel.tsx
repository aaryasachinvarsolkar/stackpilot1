"use client";

import React, { useState } from "react";
import {
  FileCode,
  X,
  Copy,
  Check,
  Split,
  Eye,
  CheckCircle2,
  XCircle,
  GitFork,
  Search,
  Lock,
  Sparkles,
} from "lucide-react";
import { DependencyGraph } from "@/components/DependencyGraph";

interface EditorPanelProps {
  selectedFile: string;
  onSelectFile: (file: string) => void;
  onOpenBottomPanel: () => void;
  isAgentModifying?: boolean;
}

interface FileContentMap {
  [key: string]: {
    lang: string;
    code: string;
    hasDiff?: boolean;
    diffLines?: { type: "normal" | "add" | "del"; text: string }[];
  };
}

const FILE_CONTENTS: FileContentMap = {
  "routes.py": {
    lang: "python",
    hasDiff: true,
    code: `@router.get("/api/health", summary="Detailed Readiness Probe")
async def detailed_health():
    """Readiness probe checking database connectivity and environment details."""
    db_status = await check_database_connection()
    return {
        "status": "healthy" if db_status["status"] == "connected" else "degraded",
        "database": db_status["status"],
        "database_type": db_status.get("type", "unknown"),
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }`,
    diffLines: [
      { type: "del", text: `@router.get("/health")` },
      { type: "del", text: `async def health():` },
      { type: "del", text: `    return {"status": "ok"}` },
      { type: "add", text: `@router.get("/api/health", summary="Detailed Readiness Probe")` },
      { type: "add", text: `async def detailed_health():` },
      { type: "add", text: `    """Readiness probe checking database connectivity and environment details."""` },
      { type: "add", text: `    db_status = await check_database_connection()` },
      { type: "add", text: `    return {` },
      { type: "add", text: `        "status": "healthy" if db_status["status"] == "connected" else "degraded",` },
      { type: "add", text: `        "database": db_status["status"],` },
      { type: "add", text: `        "database_type": db_status.get("type", "unknown"),` },
      { type: "add", text: `        "version": "0.1.0",` },
      { type: "add", text: `        "timestamp": datetime.now(timezone.utc).isoformat(),` },
      { type: "add", text: `    }` },
    ],
  },
  "rateLimiter.ts": {
    lang: "typescript",
    hasDiff: true,
    code: `import { Request, Response, NextFunction } from "express";

interface RateLimitStore {
  [ip: string]: { count: number; resetTime: number };
}

const store: RateLimitStore = {};

export function rateLimiter(limit = 100, windowMs = 60000) {
  return (req: Request, res: Response, next: NextFunction) => {
    const ip = req.ip || "unknown";
    const now = Date.now();

    if (!store[ip] || now > store[ip].resetTime) {
      store[ip] = { count: 1, resetTime: now + windowMs };
      return next();
    }

    if (store[ip].count >= limit) {
      return res.status(429).json({ error: "Too many requests, try again later." });
    }

    store[ip].count++;
    next();
  };
}`,
    diffLines: [
      { type: "add", text: `import { Request, Response, NextFunction } from "express";` },
      { type: "add", text: `export function rateLimiter(limit = 100, windowMs = 60000) {` },
      { type: "add", text: `  return (req: Request, res: Response, next: NextFunction) => {` },
      { type: "add", text: `    // Enforce request rate limit per client IP` },
      { type: "add", text: `    next();` },
      { type: "add", text: `  };` },
      { type: "add", text: `}` },
    ],
  },
  "main.py": {
    lang: "python",
    code: `from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import router

app = FastAPI(title="STACKPILOT API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)`,
  },
  "config.py": {
    lang: "python",
    code: `class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    DATABASE_URL: str = "sqlite+aiosqlite:///./stackpilot.db"
    LLM_PROVIDER: str = "openai"
    EMBEDDING_PROVIDER: str = "openai"`,
  },
  "test_health.py": {
    lang: "python",
    code: `import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"`,
  },
  "requirements.txt": {
    lang: "text",
    code: `fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.8.0
pydantic-settings>=2.4.0
sqlalchemy>=2.0.32
aiosqlite>=0.20.0
asyncpg>=0.29.0
httpx>=0.27.0
pytest>=8.3.0`,
  },
};

export function EditorPanel({
  selectedFile,
  onSelectFile,
  onOpenBottomPanel,
  isAgentModifying = false,
}: EditorPanelProps) {
  const [openTabs, setOpenTabs] = useState<string[]>(["routes.py", "rateLimiter.ts", "main.py"]);
  const [showGraphView, setShowGraphView] = useState(false);
  const [inlineDiff, setInlineDiff] = useState(false);
  const [showFind, setShowFind] = useState(false);
  const [findQuery, setFindQuery] = useState("");

  const currentFile = FILE_CONTENTS[selectedFile] || {
    lang: "plaintext",
    code: `# File: ${selectedFile}\n# Content loaded...`,
  };

  const closeTab = (e: React.MouseEvent, tab: string) => {
    e.stopPropagation();
    const filtered = openTabs.filter((t) => t !== tab);
    setOpenTabs(filtered);
    if (selectedFile === tab && filtered.length > 0) {
      onSelectFile(filtered[0]);
    }
  };

  const lines = currentFile.code.split("\n");

  return (
    <div className="h-full flex flex-col bg-[#090d16] border-r border-slate-800 overflow-hidden select-none relative">
      {/* ---------------------------------------------------- */}
      {/* 1. TAB BAR + GRAPH VIEW TOGGLE                       */}
      {/* ---------------------------------------------------- */}
      <div className="h-9 border-b border-slate-800 bg-[#080c14] flex items-center justify-between">
        <div className="flex items-center overflow-x-auto h-full">
          {openTabs.map((tab) => {
            const isActive = selectedFile === tab && !showGraphView;
            const hasMod = tab === "routes.py" || tab === "rateLimiter.ts";

            return (
              <div
                key={tab}
                onClick={() => {
                  onSelectFile(tab);
                  setShowGraphView(false);
                }}
                className={`h-full flex items-center gap-2 px-3 text-xs font-mono border-r border-slate-800 cursor-pointer transition-colors group ${
                  isActive
                    ? "bg-[#090d16] text-white border-t-2 border-t-indigo-500 font-medium"
                    : "text-slate-400 hover:bg-slate-900/60 hover:text-slate-200"
                }`}
              >
                <FileCode
                  className={`h-3.5 w-3.5 ${
                    tab.endsWith(".ts")
                      ? "text-blue-400"
                      : tab.endsWith(".py")
                      ? "text-amber-400"
                      : "text-slate-400"
                  }`}
                />
                <span>{tab}</span>
                {hasMod && <span className="h-1.5 w-1.5 rounded-full bg-amber-400" title="Modified" />}
                <button
                  onClick={(e) => closeTab(e, tab)}
                  className="p-0.5 rounded hover:bg-slate-700/60 text-slate-500 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            );
          })}
        </div>

        {/* Right Tools: Graph View Toggle, Inline Diff & Search */}
        <div className="flex items-center gap-1.5 px-3">
          {/* Find / Replace toggle */}
          <button
            onClick={() => setShowFind(!showFind)}
            className={`p-1 rounded text-xs transition-colors ${
              showFind ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
            title="Find (Ctrl+F)"
          >
            <Search className="h-3.5 w-3.5" />
          </button>

          {/* Inline Diff Toggle */}
          {currentFile.hasDiff && !showGraphView && (
            <button
              onClick={() => setInlineDiff(!inlineDiff)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                inlineDiff
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30 font-semibold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              title="Toggle inline diff insertions & deletions directly in editor"
            >
              <Split className="h-3 w-3" />
              <span>Inline Diff</span>
            </button>
          )}

          {/* Graph View Toggle Button (Swaps editor without losing tabs) */}
          <button
            onClick={() => setShowGraphView(!showGraphView)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
              showGraphView
                ? "bg-indigo-600 text-white shadow-glow"
                : "bg-surface hover:bg-slate-800 text-slate-300 border border-slate-700/80"
            }`}
            title="Swap editor with interactive dependency graph view"
          >
            <GitFork className="h-3.5 w-3.5 text-indigo-400" />
            <span>Graph View</span>
          </button>
        </div>
      </div>

      {/* ---------------------------------------------------- */}
      {/* 2. FIND BAR (Ctrl+F)                                 */}
      {/* ---------------------------------------------------- */}
      {showFind && (
        <div className="h-8 border-b border-slate-800 bg-[#070b13] px-3 flex items-center gap-2 text-xs">
          <input
            type="text"
            placeholder="Find in current file..."
            value={findQuery}
            onChange={(e) => setFindQuery(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded px-2 py-0.5 text-white font-mono text-xs outline-none focus:border-indigo-500 w-64"
          />
          <span className="text-[11px] text-slate-500 font-mono">0 results</span>
          <button onClick={() => setShowFind(false)} className="text-slate-500 hover:text-white ml-auto">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 3. BREADCRUMBS & READ-ONLY BANNER                    */}
      {/* ---------------------------------------------------- */}
      <div className="h-7 border-b border-slate-800/80 bg-[#0a0f1d] px-3 flex items-center justify-between text-[11px] font-mono text-slate-400">
        <div className="flex items-center gap-1.5">
          <span>app</span>
          <span>/</span>
          {selectedFile.includes(".") && <span>{selectedFile.split(".")[0]}</span>}
          <span>/</span>
          <span className="text-slate-200 font-semibold">{selectedFile}</span>
        </div>

        {/* Read-Only Indicator When Agent is Modifying */}
        {isAgentModifying && (
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-sans font-semibold animate-pulse">
            <Lock className="h-3 w-3" />
            <span>Read-Only: AI Agent is currently modifying this file</span>
          </div>
        )}
      </div>

      {/* ---------------------------------------------------- */}
      {/* 4. MAIN EDITOR BODY / DEPENDENCY GRAPH               */}
      {/* ---------------------------------------------------- */}
      <div className="flex-1 overflow-auto bg-[#070b13] font-mono text-xs select-text relative">
        {showGraphView ? (
          <DependencyGraph
            onSelectNode={(path) => {
              const fileName = path.split("/").pop() || path;
              if (FILE_CONTENTS[fileName]) {
                onSelectFile(fileName);
                setShowGraphView(false);
              }
            }}
          />
        ) : inlineDiff && currentFile.diffLines ? (
          /* Inline Diff Highlight Mode */
          <div className="p-3 space-y-0.5">
            {currentFile.diffLines.map((line, idx) => (
              <div
                key={idx}
                className={`flex items-start px-2 py-0.5 font-mono text-xs ${
                  line.type === "del"
                    ? "bg-rose-950/30 text-rose-300 border-l-2 border-rose-500"
                    : line.type === "add"
                    ? "bg-emerald-950/30 text-emerald-300 border-l-2 border-emerald-500"
                    : "text-slate-300"
                }`}
              >
                <span className="w-8 select-none text-slate-600 text-[11px]">{idx + 1}</span>
                <span className="w-4 select-none font-bold mr-2 text-slate-500">
                  {line.type === "del" ? "-" : line.type === "add" ? "+" : " "}
                </span>
                <span className="whitespace-pre leading-relaxed">{line.text}</span>
              </div>
            ))}
          </div>
        ) : (
          /* Monaco Style Standard Code Area */
          <div className="p-3">
            <table className="w-full border-collapse">
              <tbody>
                {lines.map((line, idx) => (
                  <tr key={idx} className="hover:bg-slate-900/40">
                    <td className="pr-4 text-right text-slate-600 select-none w-10 text-[11px] align-top">
                      {idx + 1}
                    </td>
                    <td className="text-slate-200 whitespace-pre leading-relaxed">{line}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ---------------------------------------------------- */}
      {/* 5. STATUS BAR                                        */}
      {/* ---------------------------------------------------- */}
      <div className="h-6 border-t border-slate-800 bg-[#080c14] px-3 flex items-center justify-between text-[11px] font-mono text-slate-500">
        <div className="flex items-center gap-3">
          <span className="text-slate-400">UTF-8</span>
          <span className="text-slate-400 capitalize">{currentFile.lang}</span>
          <button onClick={onOpenBottomPanel} className="hover:text-slate-300 cursor-pointer">
            Sandbox Terminal
          </button>
        </div>
        <div className="flex items-center gap-3">
          <span>Ln {lines.length}, Col 1</span>
          <span>Spaces: 4</span>
        </div>
      </div>
    </div>
  );
}
