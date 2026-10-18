"use client";

import React, { useState } from "react";
import { X, Settings, Brain, Key, Trash2, RotateCw, Check, ShieldAlert } from "lucide-react";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectName: string;
  onReindex: () => void;
}

export function SettingsModal({ isOpen, onClose, projectName, onReindex }: SettingsModalProps) {
  // Project Memory
  const [framework, setFramework] = useState("FastAPI");
  const [backend, setBackend] = useState("Python 3.13");
  const [database, setDatabase] = useState("PostgreSQL + pgvector");
  const [authMethod, setAuthMethod] = useState("JWT Bearer Tokens");
  const [testFramework, setTestFramework] = useState("Pytest");
  const [packageManager, setPackageManager] = useState("pip / requirements.txt");

  // Providers & Keys
  const [llmProvider, setLlmProvider] = useState("openai");
  const [llmKey, setLlmKey] = useState("sk-proj-••••••••••••••••••••••••");
  const [embeddingModel, setEmbeddingModel] = useState("text-embedding-3-small");

  const [saved, setSaved] = useState(false);

  if (!isOpen) return null;

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md select-none animate-in fade-in duration-150">
      <div className="w-full max-w-2xl h-[85vh] bg-surface border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Settings className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Project Settings & Memory</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Configure inferred architectural facts, LLM providers, and environment boundaries
              </p>
            </div>
          </div>

          <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-white rounded-lg">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Form Body */}
        <div className="flex-1 p-6 overflow-y-auto space-y-6 text-xs">
          {/* 1. Project Memory Section */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-indigo-400 font-bold uppercase tracking-wider text-[11px]">
              <Brain className="h-4 w-4" />
              <span>Project Memory (Inferred Architecture)</span>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed">
              STACKPILOT remembers these facts so the AI does not have to re-derive them on every request. You can correct or refine any field below:
            </p>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Framework</label>
                <input
                  type="text"
                  value={framework}
                  onChange={(e) => setFramework(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Backend Runtime</label>
                <input
                  type="text"
                  value={backend}
                  onChange={(e) => setBackend(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Database & Vector Storage</label>
                <input
                  type="text"
                  value={database}
                  onChange={(e) => setDatabase(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Authentication Method</label>
                <input
                  type="text"
                  value={authMethod}
                  onChange={(e) => setAuthMethod(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Test Framework</label>
                <input
                  type="text"
                  value={testFramework}
                  onChange={(e) => setTestFramework(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Package Manager</label>
                <input
                  type="text"
                  value={packageManager}
                  onChange={(e) => setPackageManager(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500 font-mono"
                />
              </div>
            </div>
          </div>

          <div className="border-t border-slate-800" />

          {/* 2. LLM Provider Configuration */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-cyan-400 font-bold uppercase tracking-wider text-[11px]">
              <Key className="h-4 w-4" />
              <span>AI Provider & Secret Keys</span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">LLM Provider</label>
                <select
                  value={llmProvider}
                  onChange={(e) => setLlmProvider(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500"
                >
                  <option value="openai">OpenAI (GPT-4o)</option>
                  <option value="anthropic">Anthropic (Claude 3.5 Sonnet)</option>
                  <option value="gemini">Google Gemini (Gemini 1.5 Pro)</option>
                  <option value="ollama">Local Ollama / Llama 3</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">API Key (Masked)</label>
                <input
                  type="password"
                  value={llmKey}
                  onChange={(e) => setLlmKey(e.target.value)}
                  placeholder="sk-proj-..."
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500 font-mono"
                />
              </div>
            </div>
          </div>

          <div className="border-t border-slate-800" />

          {/* 3. Danger Zone */}
          <div className="space-y-3 p-4 rounded-xl bg-rose-950/20 border border-rose-500/30">
            <div className="flex items-center gap-2 text-rose-400 font-bold uppercase tracking-wider text-[11px]">
              <ShieldAlert className="h-4 w-4" />
              <span>Danger Zone</span>
            </div>

            <div className="flex items-center justify-between pt-2">
              <div>
                <div className="font-semibold text-white">Re-Index Repository</div>
                <div className="text-[11px] text-slate-400">
                  Wipes and re-parses all Tree-sitter AST nodes and pgvector embeddings.
                </div>
              </div>
              <button
                onClick={() => {
                  onReindex();
                  onClose();
                }}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold flex items-center gap-1.5 transition-colors"
              >
                <RotateCw className="h-3.5 w-3.5" />
                <span>Re-Index Now</span>
              </button>
            </div>

            <div className="border-t border-rose-500/20 pt-3 flex items-center justify-between">
              <div>
                <div className="font-semibold text-rose-300">Delete Project</div>
                <div className="text-[11px] text-slate-400">
                  Permanently remove this project and its indexing data from STACKPILOT.
                </div>
              </div>
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded-lg bg-rose-600/30 hover:bg-rose-600 text-rose-200 font-semibold flex items-center gap-1.5 transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>Delete</span>
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-[#080c14] flex items-center justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-xl text-slate-400 hover:text-white">
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-2 shadow-glow transition-all"
          >
            {saved ? <Check className="h-4 w-4" /> : null}
            <span>{saved ? "Settings Saved!" : "Save Changes"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
