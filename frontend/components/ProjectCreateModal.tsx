"use client";

import React, { useState } from "react";
import { X, FolderPlus, UploadCloud, GitBranch, ArrowRight, Check, AlertCircle } from "lucide-react";

export interface NewProjectPayload {
  name: string;
  sourceType: "blank" | "upload" | "git";
  template?: string;
  gitUrl?: string;
  gitBranch?: string;
  fileName?: string;
}

interface ProjectCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (project: NewProjectPayload) => void;
}

export function ProjectCreateModal({ isOpen, onClose, onSubmit }: ProjectCreateModalProps) {
  const [tab, setTab] = useState<"blank" | "upload" | "git">("blank");
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("FastAPI + Python");
  const [gitUrl, setGitUrl] = useState("");
  const [gitBranch, setGitBranch] = useState("main");
  const [gitToken, setGitToken] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleUploadSimulate = (fileName: string) => {
    setUploadedFile(fileName);
    setName(fileName.replace(/\.(zip|tar\.gz)$/, ""));
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev === null || prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        return prev + 25;
      });
    }, 200);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Please provide a project name.");
      return;
    }

    if (tab === "git" && !gitUrl.trim()) {
      setError("Please enter a valid Git repository URL.");
      return;
    }

    onSubmit({
      name: name.trim(),
      sourceType: tab,
      template: tab === "blank" ? template : undefined,
      gitUrl: tab === "git" ? gitUrl.trim() : undefined,
      gitBranch: tab === "git" ? gitBranch.trim() : undefined,
      fileName: uploadedFile || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md select-none animate-in fade-in duration-150">
      <div className="w-full max-w-xl bg-surface border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white">Create or Import Project</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Choose your project source to initiate codebase AST indexing
            </p>
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-white rounded-lg">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tab Selection */}
        <div className="grid grid-cols-3 border-b border-slate-800 bg-slate-900/60 p-1.5 gap-1.5 text-xs">
          <button
            type="button"
            onClick={() => {
              setTab("blank");
              setError(null);
            }}
            className={`flex items-center justify-center gap-2 py-2 rounded-lg font-medium transition-all ${
              tab === "blank"
                ? "bg-indigo-600 text-white shadow-glow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            }`}
          >
            <FolderPlus className="h-3.5 w-3.5" />
            <span>Blank Project</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setTab("upload");
              setError(null);
            }}
            className={`flex items-center justify-center gap-2 py-2 rounded-lg font-medium transition-all ${
              tab === "upload"
                ? "bg-indigo-600 text-white shadow-glow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            }`}
          >
            <UploadCloud className="h-3.5 w-3.5" />
            <span>Upload Archive</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setTab("git");
              setError(null);
            }}
            className={`flex items-center justify-center gap-2 py-2 rounded-lg font-medium transition-all ${
              tab === "git"
                ? "bg-indigo-600 text-white shadow-glow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            }`}
          >
            <GitBranch className="h-3.5 w-3.5" />
            <span>Import from Git</span>
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
          {error && (
            <div className="p-3 rounded-xl bg-rose-950/30 border border-rose-500/40 text-rose-300 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Project Name */}
          <div className="space-y-1.5">
            <label className="font-semibold text-slate-300">Project Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. payment-service-api"
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white placeholder:text-slate-600 outline-none focus:border-indigo-500"
            />
          </div>

          {/* 1. Blank Project Template Selection */}
          {tab === "blank" && (
            <div className="space-y-1.5">
              <label className="font-semibold text-slate-300">Starter Architecture Template</label>
              <select
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500 font-sans"
              >
                <option value="FastAPI + Python">FastAPI + Python (Async SQLAlchemy)</option>
                <option value="Next.js + TypeScript">Next.js 14 + TypeScript (App Router)</option>
                <option value="Express + Node.js">Express + TypeScript Microservice</option>
                <option value="Go + Gin Engine">Go + Gin REST API</option>
              </select>
            </div>
          )}

          {/* 2. Upload Drag and Drop Zone */}
          {tab === "upload" && (
            <div className="space-y-2">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragActive(false);
                  const files = e.dataTransfer.files;
                  if (files && files[0]) {
                    handleUploadSimulate(files[0].name);
                  }
                }}
                className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${
                  dragActive ? "border-indigo-500 bg-indigo-500/10" : "border-slate-800 bg-slate-900/40 hover:bg-slate-900"
                }`}
                onClick={() => handleUploadSimulate("my-project-archive.zip")}
              >
                <UploadCloud className="h-8 w-8 text-indigo-400 mb-2" />
                <p className="font-semibold text-slate-200">
                  {uploadedFile ? uploadedFile : "Drag and drop your project ZIP or folder here"}
                </p>
                <p className="text-[11px] text-slate-500 mt-1">Supports .zip, .tar.gz archives up to 250MB</p>
              </div>

              {uploadProgress !== null && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>Uploading archive...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 transition-all duration-200"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 3. Git Repository Import Fields */}
          {tab === "git" && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300">Git Repository URL</label>
                <input
                  type="text"
                  value={gitUrl}
                  onChange={(e) => {
                    setGitUrl(e.target.value);
                    if (!name) {
                      const parts = e.target.value.split("/");
                      const last = parts[parts.length - 1];
                      if (last) setName(last.replace(/\.git$/, ""));
                    }
                  }}
                  placeholder="https://github.com/org/repo.git"
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white placeholder:text-slate-600 outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="font-semibold text-slate-300">Branch</label>
                  <input
                    type="text"
                    value={gitBranch}
                    onChange={(e) => setGitBranch(e.target.value)}
                    placeholder="main"
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="font-semibold text-slate-300">Personal Access Token (Optional)</label>
                  <input
                    type="password"
                    value={gitToken}
                    onChange={(e) => setGitToken(e.target.value)}
                    placeholder="For private repositories"
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-white placeholder:text-slate-600 outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Footer Action */}
          <div className="pt-4 border-t border-slate-800 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-slate-400 hover:text-white font-medium"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-2 shadow-glow transition-all"
            >
              <span>Initialize & Index Codebase</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
