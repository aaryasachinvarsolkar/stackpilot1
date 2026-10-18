"use client";

import React, { useState } from "react";
import {
  X,
  ShieldAlert,
  Bug,
  Zap,
  CheckCircle2,
  FileCode,
  ArrowRight,
  Sparkles,
  AlertTriangle,
  Layers,
  Wrench,
  Check,
} from "lucide-react";

export type FindingCategory = "security" | "bug" | "perf" | "quality" | "maintainability" | "testing";
export type Severity = "critical" | "high" | "medium" | "low";

export interface ReviewFinding {
  id: string;
  category: FindingCategory;
  severity: Severity;
  title: string;
  description: string;
  file: string;
  line: number;
  suggestion: string;
  applied?: boolean;
}

interface CodeReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onJumpToFile: (file: string, line: number) => void;
  onApplySuggestion: (finding: ReviewFinding) => void;
}

const SAMPLE_FINDINGS: ReviewFinding[] = [
  {
    id: "f-1",
    category: "security",
    severity: "high",
    title: "Client IP Spoofing Risk in Rate Limiter",
    description: "Reading raw req.ip without validating trust proxy settings allows attackers to spoof client IP via forged X-Forwarded-For headers, bypassing rate limits.",
    file: "app/middleware/rateLimiter.ts",
    line: 9,
    suggestion: "const clientIp = req.headers['x-forwarded-for']?.toString().split(',')[0].trim() || req.socket.remoteAddress;",
  },
  {
    id: "f-2",
    category: "perf",
    severity: "medium",
    title: "Unbounded In-Memory Token Bucket Map",
    description: "The in-memory rate limit store does not implement an eviction policy for expired IPs, leading to potential memory leak under high IP turnover.",
    file: "app/middleware/rateLimiter.ts",
    line: 7,
    suggestion: "// Schedule periodic cleanup timer to prune expired entries every 5 minutes",
  },
  {
    id: "f-3",
    category: "testing",
    severity: "medium",
    title: "Missing 429 Throttle Unit Test",
    description: "Existing test suite verifies status 200 health checks, but does not assert 429 response when request limits are exceeded.",
    file: "tests/test_health.py",
    line: 35,
    suggestion: "async def test_rate_limiter_throttles(): response = await client.get('/api/health'); assert response.status_code == 429",
  },
  {
    id: "f-4",
    category: "maintainability",
    severity: "low",
    title: "Hardcoded default fallback values",
    description: "Default windowMs and limit values should be injected via Pydantic settings rather than hardcoded magic numbers.",
    file: "app/middleware/rateLimiter.ts",
    line: 8,
    suggestion: "export function rateLimiter(limit = settings.RATE_LIMIT, windowMs = settings.RATE_WINDOW_MS)",
  },
];

export function CodeReviewModal({ isOpen, onClose, onJumpToFile, onApplySuggestion }: CodeReviewModalProps) {
  const [findings, setFindings] = useState<ReviewFinding[]>(SAMPLE_FINDINGS);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  if (!isOpen) return null;

  const categories = [
    { id: "all", label: "All Findings", count: findings.length },
    { id: "security", label: "Security", count: findings.filter((f) => f.category === "security").length },
    { id: "bug", label: "Bugs", count: findings.filter((f) => f.category === "bug").length },
    { id: "perf", label: "Performance", count: findings.filter((f) => f.category === "perf").length },
    { id: "testing", label: "Testing Gaps", count: findings.filter((f) => f.category === "testing").length },
    { id: "maintainability", label: "Maintainability", count: findings.filter((f) => f.category === "maintainability").length },
  ];

  const filtered = selectedCategory === "all" ? findings : findings.filter((f) => f.category === selectedCategory);

  const handleApply = (finding: ReviewFinding) => {
    setFindings((prev) =>
      prev.map((f) => (f.id === finding.id ? { ...f, applied: true } : f))
    );
    onApplySuggestion(finding);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md select-none animate-in fade-in duration-150">
      <div className="w-full max-w-4xl h-[80vh] bg-surface border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <ShieldAlert className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <span>Automated Code Review Audit</span>
                <span className="text-xs font-mono font-normal px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20">
                  {findings.length} findings
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Structured static & semantic analysis of project changes
              </p>
            </div>
          </div>

          <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-white rounded-lg">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Category Tabs */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-800 bg-[#080c14] overflow-x-auto text-xs">
          {categories.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelectedCategory(c.id)}
              className={`px-3 py-1 rounded-lg font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap ${
                selectedCategory === c.id
                  ? "bg-indigo-600 text-white font-semibold shadow-sm"
                  : "text-slate-400 hover:text-white hover:bg-slate-800/40"
              }`}
            >
              <span>{c.label}</span>
              <span className="text-[10px] opacity-75 font-mono">({c.count})</span>
            </button>
          ))}
        </div>

        {/* Findings List */}
        <div className="flex-1 p-6 overflow-y-auto space-y-4">
          {filtered.map((finding) => (
            <div
              key={finding.id}
              className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3 hover:border-slate-700 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                        finding.severity === "high"
                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                          : finding.severity === "medium"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                          : "bg-blue-500/10 text-blue-400 border border-blue-500/30"
                      }`}
                    >
                      {finding.severity}
                    </span>
                    <span className="text-sm font-bold text-white">{finding.title}</span>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed">{finding.description}</p>
                </div>

                <button
                  onClick={() => {
                    onJumpToFile(finding.file, finding.line);
                    onClose();
                  }}
                  className="flex items-center gap-1.5 text-xs font-mono text-indigo-400 hover:text-indigo-300 bg-indigo-500/10 hover:bg-indigo-500/20 px-2.5 py-1 rounded-lg border border-indigo-500/20 transition-colors flex-shrink-0"
                  title="Jump to code line in editor"
                >
                  <FileCode className="h-3.5 w-3.5" />
                  <span>{finding.file}:{finding.line}</span>
                </button>
              </div>

              {/* Code Suggestion Box */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-semibold text-slate-400">Suggested Fix:</span>
                <div className="p-3 rounded-lg bg-[#070a12] border border-slate-800 font-mono text-xs text-emerald-300 overflow-x-auto">
                  {finding.suggestion}
                </div>
              </div>

              {/* Actions Footer */}
              <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs">
                <span className="text-slate-500 font-mono text-[11px]">Rule: AST-SEC-{finding.id}</span>
                {finding.applied ? (
                  <span className="text-emerald-400 font-semibold flex items-center gap-1">
                    <Check className="h-3.5 w-3.5" /> Suggestion Applied
                  </span>
                ) : (
                  <button
                    onClick={() => handleApply(finding)}
                    className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg flex items-center gap-1.5 shadow-sm transition-colors"
                  >
                    <Wrench className="h-3.5 w-3.5" />
                    <span>Apply Suggestion</span>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
