"use client";

import React, { useState } from "react";
import {
  Bot,
  Send,
  Sparkles,
  FileCode,
  CheckCircle2,
  Play,
  RotateCcw,
  Check,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  Layers,
  Wrench,
  ChevronRight,
  Split,
  FileText,
  Square,
  RotateCw,
  FolderGit2,
  ExternalLink,
  Terminal,
  XCircle,
} from "lucide-react";

interface AICopilotPanelProps {
  onOpenFile: (file: string) => void;
  onOpenDiffView: () => void;
  isOpen: boolean;
}

export function AICopilotPanel({ onOpenFile, onOpenDiffView, isOpen }: AICopilotPanelProps) {
  const [activeTab, setActiveTab] = useState<"agent" | "chat" | "review">("agent");
  const [promptInput, setPromptInput] = useState("");
  const [planApproved, setPlanApproved] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  
  // Sensitive approval state
  const [approvalStatus, setApprovalStatus] = useState<"pending" | "approved" | "rejected">("pending");
  const [showFilesDrawer, setShowFilesDrawer] = useState(false);

  if (!isOpen) return null;

  const groundedFiles = [
    "app/api/routes.py",
    "app/core/config.py",
    "app/db/session.py",
    "app/models/user.py",
    "app/middleware/auth.py",
    "tests/test_health.py",
  ];

  const planSteps = [
    { id: 1, text: "Inspect existing route definitions in app/api/routes.py", tool: "read_file", status: "completed" },
    { id: 2, text: "Generate rate-limiting middleware in app/middleware/rateLimiter.ts", tool: "create_file", status: "completed" },
    { id: 3, text: "Attach middleware to protected endpoints and update responses", tool: "modify_file", status: planApproved ? "running" : "pending" },
    { id: 4, text: "Run test suite inside Docker sandbox container to verify", tool: "run_tests", status: "pending" },
  ];

  const handleApprovePlan = () => {
    setPlanApproved(true);
    setIsExecuting(true);
    setTimeout(() => {
      setIsExecuting(false);
    }, 1800);
  };

  const handleRegenerate = () => {
    setIsExecuting(true);
    setTimeout(() => {
      setIsExecuting(false);
    }, 1500);
  };

  const handleStopExecution = () => {
    setIsExecuting(false);
  };

  return (
    <div className="w-80 lg:w-96 h-full bg-[#0b101b] border-l border-slate-800 flex flex-col select-none text-xs z-20">
      {/* ---------------------------------------------------- */}
      {/* 1. COPILOT HEADER & MODE SELECTOR                    */}
      {/* ---------------------------------------------------- */}
      <div className="p-3 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-lg bg-gradient-to-tr from-indigo-500 to-cyan-500 p-[1px] shadow-glow flex items-center justify-center">
            <div className="h-full w-full bg-slate-900 rounded-lg flex items-center justify-center">
              <Bot className="h-3.5 w-3.5 text-indigo-400" />
            </div>
          </div>
          <span className="font-bold uppercase tracking-wider text-slate-200">AI COPILOT</span>
        </div>

        <div className="flex items-center gap-1 p-0.5 bg-slate-900 border border-slate-800 rounded-lg">
          <button
            onClick={() => setActiveTab("agent")}
            className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
              activeTab === "agent" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
            }`}
          >
            Agent
          </button>
          <button
            onClick={() => setActiveTab("chat")}
            className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
              activeTab === "chat" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setActiveTab("review")}
            className={`px-2 py-1 rounded text-[11px] font-semibold transition-colors ${
              activeTab === "review" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
            }`}
          >
            Review
          </button>
        </div>
      </div>

      {/* ---------------------------------------------------- */}
      {/* CONTEXT INDICATOR BAR (Grounded Files Indicator)      */}
      {/* ---------------------------------------------------- */}
      <div className="px-3 py-2 bg-indigo-950/20 border-b border-indigo-900/30 flex items-center justify-between">
        <button
          onClick={() => setShowFilesDrawer(!showFilesDrawer)}
          className="flex items-center gap-1.5 text-[11px] text-indigo-300 hover:text-indigo-200 transition-colors"
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="font-medium">Using {groundedFiles.length} grounded files from project</span>
        </button>
        <span className="text-[10px] text-slate-500 font-mono">AST+RAG</span>
      </div>

      {/* Files Drawer Modal / Collapse */}
      {showFilesDrawer && (
        <div className="p-2.5 bg-slate-900/90 border-b border-slate-800 space-y-1 text-[11px] max-h-36 overflow-y-auto font-mono">
          <div className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center justify-between">
            <span>Context Grounded Files</span>
            <button
              onClick={() => setShowFilesDrawer(false)}
              className="text-slate-500 hover:text-slate-300"
            >
              ✕
            </button>
          </div>
          {groundedFiles.map((f) => (
            <div
              key={f}
              onClick={() => {
                onOpenFile(f.split("/").pop() || f);
                setShowFilesDrawer(false);
              }}
              className="flex items-center gap-1.5 p-1 rounded hover:bg-slate-800 text-slate-300 hover:text-indigo-300 cursor-pointer transition-colors"
            >
              <FileCode className="h-3 w-3 text-indigo-400" />
              <span className="truncate">{f}</span>
            </div>
          ))}
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 2. TAB: AGENT (PLANNER + TOOL CALLING)               */}
      {/* ---------------------------------------------------- */}
      {activeTab === "agent" && (
        <div className="flex-1 flex flex-col p-3 space-y-3 overflow-y-auto">
          {/* Active Goal / Prompt Card */}
          <div className="p-3 rounded-xl bg-surface/80 border border-slate-800 space-y-2">
            <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Sparkles className="h-3 w-3" />
                <span>ACTIVE ENGINEERING TASK</span>
              </div>
              {isExecuting && (
                <span className="flex items-center gap-1 text-[10px] text-amber-400 font-mono animate-pulse">
                  <RotateCw className="h-2.5 w-2.5 animate-spin" /> executing
                </span>
              )}
            </div>
            <p className="text-slate-200 font-medium leading-relaxed">
              Add rate limiting middleware to protected routes and write verification tests.
            </p>
          </div>

          {/* Numbered Implementation Plan */}
          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-300">
                IMPLEMENTATION PLAN
              </span>
              <span
                className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                  planApproved
                    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
                    : "bg-indigo-500/10 text-indigo-300 border-indigo-500/20"
                }`}
              >
                {planApproved ? "APPROVED" : "REQUIRES APPROVAL"}
              </span>
            </div>

            <div className="space-y-2">
              {planSteps.map((step) => (
                <div key={step.id} className="flex items-start gap-2 text-slate-300 text-xs leading-snug">
                  <span
                    className={`flex-shrink-0 w-4 h-4 rounded-full text-[10px] font-mono font-bold flex items-center justify-center mt-0.5 ${
                      step.status === "completed"
                        ? "bg-emerald-500/20 text-emerald-400"
                        : step.status === "running"
                        ? "bg-amber-500/20 text-amber-400 animate-pulse"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {step.status === "completed" ? "✓" : step.id}
                  </span>
                  <div className="flex-1">
                    <span className={step.status === "completed" ? "text-slate-400 line-through" : "text-slate-200"}>
                      {step.text}
                    </span>
                    <span className="ml-1.5 px-1 py-0.2 rounded bg-slate-800/80 text-indigo-300 font-mono text-[9px]">
                      {step.tool}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Approval Gate Action */}
            {!planApproved ? (
              <div className="pt-2 border-t border-slate-800/80 flex items-center gap-2">
                <button
                  onClick={handleApprovePlan}
                  className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold text-xs transition-colors flex items-center justify-center gap-1.5 shadow-sm"
                >
                  <Check className="h-3.5 w-3.5" />
                  <span>Approve Plan & Execute</span>
                </button>
              </div>
            ) : (
              <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-emerald-400 font-medium">
                <span className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Plan approved by user
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleRegenerate}
                    className="text-slate-400 hover:text-indigo-300 text-[11px] flex items-center gap-1"
                    title="Regenerate step"
                  >
                    <RotateCw className="h-3 w-3" /> Re-run
                  </button>
                  <button
                    onClick={() => setPlanApproved(false)}
                    className="text-slate-400 hover:text-slate-200 text-[11px]"
                  >
                    Modify
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* SENSITIVE OPERATION APPROVAL REQUEST CARD (e.g. Git push / Shell) */}
          <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-amber-400 font-bold text-[10px] uppercase tracking-wider">
                <ShieldAlert className="h-3.5 w-3.5" />
                <span>APPROVAL REQUIRED: SENSITIVE ACTION</span>
              </div>
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                SANDBOX ESCAPE GUARD
              </span>
            </div>

            <div className="p-2 rounded bg-slate-900/90 border border-slate-800 font-mono text-[11px] text-slate-300 flex items-center gap-2">
              <Terminal className="h-3.5 w-3.5 text-amber-400 flex-shrink-0" />
              <code className="text-amber-300 truncate">git push origin feat/rate-limiting</code>
            </div>

            <p className="text-[11px] text-slate-400 leading-snug">
              StackPilot agent requests permission to push commits upstream to remote repository.
            </p>

            {approvalStatus === "pending" ? (
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={() => setApprovalStatus("approved")}
                  className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold text-xs transition-colors flex items-center justify-center gap-1 shadow-sm"
                >
                  <Check className="h-3 w-3" />
                  <span>Allow Action</span>
                </button>
                <button
                  onClick={() => setApprovalStatus("rejected")}
                  className="flex-1 py-1.5 bg-rose-900/40 hover:bg-rose-900/60 border border-rose-700/50 text-rose-300 rounded-lg font-semibold text-xs transition-colors flex items-center justify-center gap-1"
                >
                  <XCircle className="h-3 w-3" />
                  <span>Reject</span>
                </button>
              </div>
            ) : approvalStatus === "approved" ? (
              <div className="p-1.5 rounded bg-emerald-950/30 border border-emerald-500/30 text-emerald-400 flex items-center gap-1.5 text-[11px] font-medium">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>Action approved and executed in sandbox container.</span>
              </div>
            ) : (
              <div className="p-1.5 rounded bg-rose-950/30 border border-rose-500/30 text-rose-400 flex items-center gap-1.5 text-[11px] font-medium">
                <XCircle className="h-3.5 w-3.5" />
                <span>Action blocked by user. Execution aborted.</span>
              </div>
            )}
          </div>

          {/* Controlled Tool Call Audit Log */}
          {planApproved && (
            <div className="p-3 rounded-xl bg-surface/40 border border-slate-800 space-y-2">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Wrench className="h-3 w-3 text-indigo-400" />
                <span>TOOL EXECUTION AUDIT LOG</span>
              </div>

              <div className="space-y-1.5 font-mono text-[11px]">
                <div className="p-1.5 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between text-slate-300">
                  <span>read_file(&quot;app/api/routes.py&quot;)</span>
                  <span className="text-emerald-400 font-bold">200 OK</span>
                </div>
                <div className="p-1.5 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between text-slate-300">
                  <span>create_file(&quot;rateLimiter.ts&quot;)</span>
                  <span className="text-emerald-400 font-bold">Created</span>
                </div>
                <div className="p-1.5 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between text-slate-300">
                  <span>run_tests(&quot;pytest&quot;)</span>
                  <span className="text-emerald-400 font-bold">Passed</span>
                </div>
              </div>

              {/* Quick Jump to Diff */}
              <button
                onClick={onOpenDiffView}
                className="w-full mt-2 py-1.5 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 rounded-lg font-semibold text-xs flex items-center justify-center gap-1.5 transition-colors"
              >
                <Split className="h-3.5 w-3.5 text-indigo-400" />
                <span>Review Generated Diff in Editor</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 3. TAB: CHAT (CODEBASE RAG)                          */}
      {/* ---------------------------------------------------- */}
      {activeTab === "chat" && (
        <div className="flex-1 flex flex-col p-3 space-y-3 overflow-y-auto">
          <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1.5">
            <span className="text-indigo-400 font-bold text-[10px] uppercase tracking-wider">
              GROUNDED CODEBASE QUERY
            </span>
            <p className="text-slate-300 leading-relaxed text-xs">
              Where is the detailed health check route located?
            </p>
          </div>

          <div className="p-3 rounded-xl bg-surface/60 border border-slate-800 space-y-2">
            <div className="flex items-center gap-1.5 text-cyan-400 font-semibold text-xs">
              <Bot className="h-3.5 w-3.5" />
              <span>STACKPILOT Assistant</span>
            </div>
            <p className="text-slate-200 text-xs leading-relaxed">
              The health check endpoint is defined in <code className="text-indigo-300 bg-slate-800 px-1 py-0.5 rounded font-mono">detailed_health()</code>.
              It executes a lightweight probe against the database and reports dialect information.
            </p>

            <div className="pt-2 border-t border-slate-800/80">
              <span className="text-[10px] text-slate-500 font-semibold uppercase block mb-1">
                CITATIONS
              </span>
              <div
                onClick={() => onOpenFile("routes.py")}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-slate-800/80 hover:bg-indigo-600/20 border border-slate-700/60 text-indigo-300 hover:text-white cursor-pointer font-mono text-[11px] transition-colors"
              >
                <FileCode className="h-3 w-3 text-cyan-400" />
                <span>app/api/routes.py:20-33</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 4. TAB: CODE REVIEW AUDIT                            */}
      {/* ---------------------------------------------------- */}
      {activeTab === "review" && (
        <div className="flex-1 p-3 space-y-3 overflow-y-auto">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="font-bold uppercase tracking-wider text-slate-300">CODE REVIEW FINDINGS</span>
            <span className="text-emerald-400 font-mono text-[10px]">1 ADVISORY</span>
          </div>

          <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-1.5">
            <div className="flex items-center gap-1.5 text-amber-400 font-semibold text-xs">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span>Security Advisory</span>
            </div>
            <p className="text-slate-300 text-xs leading-relaxed">
              Ensure reverse proxy forwards the real client IP (via <code className="font-mono text-amber-300">X-Forwarded-For</code>)
              so rate limiting functions reliably behind load balancers.
            </p>
            <div className="text-[11px] font-mono text-slate-400 mt-1">
              File: app/middleware/rateLimiter.ts:9
            </div>
          </div>

          <div className="p-3 rounded-xl bg-surface/40 border border-slate-800 space-y-1.5">
            <div className="flex items-center gap-1.5 text-emerald-400 font-semibold text-xs">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>Architecture & Maintainability</span>
            </div>
            <p className="text-slate-300 text-xs">
              Modular structure respects decoupled dependency injection and clean separation of concerns.
            </p>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 5. GENERATE & STOP CONTROLS (Floating when executing) */}
      {/* ---------------------------------------------------- */}
      {isExecuting && (
        <div className="px-3 py-1.5 bg-slate-900 border-t border-slate-800 flex items-center justify-between">
          <span className="text-[11px] text-amber-400 font-mono animate-pulse flex items-center gap-1">
            <RotateCw className="h-3 w-3 animate-spin" /> Agent generating...
          </span>
          <button
            onClick={handleStopExecution}
            className="flex items-center gap-1 px-2 py-0.5 rounded bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 border border-rose-500/30 text-[11px] font-medium"
          >
            <Square className="h-2.5 w-2.5 fill-rose-400" /> Stop
          </button>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* 6. PROMPT INPUT BAR                                  */}
      {/* ---------------------------------------------------- */}
      <div className="p-2 border-t border-slate-800 bg-[#080c14]">
        <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 focus-within:border-indigo-500 transition-colors">
          <input
            type="text"
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            placeholder={
              activeTab === "agent"
                ? "Describe task (e.g. add auth middleware)..."
                : activeTab === "chat"
                ? "Ask anything about this project..."
                : "Request code review on changes..."
            }
            className="flex-1 bg-transparent border-none outline-none text-xs text-white placeholder:text-slate-600 font-sans"
          />
          <button
            className="p-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white transition-colors shadow-glow"
            title="Submit request"
          >
            <Send className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
