"use client";

import React, { useState } from "react";
import { FileCode, X, Play, Copy, Check } from "lucide-react";

interface Tab {
  name: string;
  lang: string;
  content: string;
}

const TABS: Tab[] = [
  {
    name: "routes.py",
    lang: "python",
    content: `@router.get("/api/health")
async def detailed_health():
    """Readiness probe checking database connectivity and environment details."""
    db_status = await check_database_connection()
    return {
        "status": "healthy" if db_status["status"] == "connected" else "degraded",
        "database": db_status["status"],
        "database_type": db_status.get("type", "unknown"),
        "version": "0.1.0",
    }`,
  },
  {
    name: "main.py",
    lang: "python",
    content: `from fastapi import FastAPI
from app.config import settings
from app.api.routes import router

app = FastAPI(title="STACKPILOT API")
app.include_router(router)`,
  },
  {
    name: "config.py",
    lang: "python",
    content: `class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "sqlite+aiosqlite:///./stackpilot.db"
    LLM_PROVIDER: str = "openai"`,
  },
];

export function EditorPlaceholder() {
  const [activeTab, setActiveTab] = useState(0);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(TABS[activeTab].content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const lines = TABS[activeTab].content.split("\n");

  return (
    <div className="h-full flex flex-col bg-surface/50 border border-slate-800/80 rounded-xl overflow-hidden backdrop-blur-md">
      {/* Tab Bar */}
      <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-900/40">
        <div className="flex items-center overflow-x-auto">
          {TABS.map((tab, idx) => (
            <div
              key={tab.name}
              onClick={() => setActiveTab(idx)}
              className={`flex items-center gap-2 px-3 py-2 text-xs font-mono border-r border-slate-800/80 cursor-pointer select-none transition-colors ${
                activeTab === idx
                  ? "bg-surface/80 text-white border-t-2 border-t-indigo-500 font-semibold"
                  : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
              }`}
            >
              <FileCode className="h-3.5 w-3.5 text-indigo-400" />
              <span>{tab.name}</span>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2 px-3">
          <button
            onClick={handleCopy}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200 transition-colors"
            title="Copy code"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Editor Breadcrumbs */}
      <div className="px-4 py-1.5 border-b border-slate-800/60 text-[11px] font-mono text-slate-500 flex items-center gap-1.5 bg-slate-950/20">
        <span>app</span>
        <span>/</span>
        <span>api</span>
        <span>/</span>
        <span className="text-slate-300 font-semibold">{TABS[activeTab].name}</span>
      </div>

      {/* Editor Code Area */}
      <div className="flex-1 p-4 font-mono text-xs overflow-auto bg-slate-950/40 select-text">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, idx) => (
              <tr key={idx} className="hover:bg-slate-900/40">
                <td className="pr-4 text-right text-slate-600 select-none w-8 text-[11px]">{idx + 1}</td>
                <td className="text-slate-200 whitespace-pre leading-relaxed">{line}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Editor Status Bar */}
      <div className="px-4 py-1.5 border-t border-slate-800/80 bg-slate-900/60 text-[11px] font-mono text-slate-400 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span>UTF-8</span>
          <span>Python</span>
        </div>
        <div className="flex items-center gap-3">
          <span>Ln {lines.length}, Col 1</span>
          <span>Spaces: 4</span>
        </div>
      </div>
    </div>
  );
}
