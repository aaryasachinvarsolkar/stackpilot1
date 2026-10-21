"use client";

import React, { useEffect, useState, useRef } from "react";
import { Loader2, X, Upload, GitBranch, Sparkles, FolderArchive, ArrowRight } from "lucide-react";
import { createProject, uploadProjectZip, importGitProject, type ProjectApiItem } from "@/lib/api";

const TEMPLATES = ["FastAPI + Python", "Next.js + TypeScript", "Go Microservice"];
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;
const RESERVED = new Set(["con", "prn", "aux", "nul", ...Array.from({ length: 9 }, (_, i) => `com${i + 1}`), ...Array.from({ length: 9 }, (_, i) => `lpt${i + 1}`)]);

export function validateProjectName(name: string): string | null {
  if (!name) return "Enter a project name.";
  if (!NAME_RE.test(name)) return "Use 1-100 characters: letters, digits, '.', '_' or '-'. Start with a letter or digit; no spaces or slashes.";
  if (name.endsWith(".")) return "The name must not end with a dot.";
  if (RESERVED.has(name.split(".")[0].toLowerCase())) return "That name is reserved by the operating system.";
  return null;
}

interface CreateProjectDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (project: ProjectApiItem) => void;
}

type Mode = "template" | "upload" | "git";

export function CreateProjectDialog({ open, onClose, onCreated }: CreateProjectDialogProps) {
  const [mode, setMode] = useState<Mode>("template");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState(TEMPLATES[0]);
  const [gitUrl, setGitUrl] = useState("");
  const [gitBranch, setGitBranch] = useState("main");
  const [selectedZip, setSelectedZip] = useState<File | null>(null);

  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setMode("template");
    setName("");
    setDescription("");
    setTemplate(TEMPLATES[0]);
    setGitUrl("");
    setGitBranch("main");
    setSelectedZip(null);
    setTouched(false);
    setBusy(false);
    setServerError(null);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) return null;

  const problem = validateProjectName(name);

  const handleZipChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedZip(file);
      if (!name) {
        const baseName = file.name.replace(/\.zip$/i, "").replace(/[^a-zA-Z0-9._-]/g, "-").slice(0, 50);
        setName(baseName);
      }
    }
  };

  const handleGitUrlChange = (url: string) => {
    setGitUrl(url);
    if (!name && url) {
      const match = url.trim().match(/github\.com[/:][\w.-]+\/([\w.-]+)/);
      if (match) {
        const repo = match[1].replace(/\.git$/, "");
        setName(repo);
      }
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setServerError(null);
    if (problem) return;

    setBusy(true);

    try {
      if (mode === "template") {
        const res = await createProject({ name, description: description.trim() || undefined, template });
        setBusy(false);
        if (res.ok && res.data) {
          onCreated(res.data);
        } else {
          setServerError(res.message ?? "The project could not be created.");
        }
      } else if (mode === "upload") {
        if (!selectedZip) {
          setBusy(false);
          setServerError("Please select a .zip archive to upload.");
          return;
        }
        const formData = new FormData();
        formData.append("file", selectedZip);
        formData.append("name", name);
        if (description) formData.append("description", description);

        const res = await uploadProjectZip(formData);
        setBusy(false);
        if (res.ok && res.data) {
          onCreated(res.data);
        } else {
          setServerError(res.message ?? "Failed to extract and create project from ZIP.");
        }
      } else if (mode === "git") {
        if (!gitUrl.trim()) {
          setBusy(false);
          setServerError("Please provide a GitHub repository link.");
          return;
        }
        const res = await importGitProject({
          name,
          git_url: gitUrl.trim(),
          branch: gitBranch.trim() || "main",
          description: description.trim() || undefined,
        });
        setBusy(false);
        if (res.ok && res.data) {
          onCreated(res.data);
        } else {
          setServerError(res.message ?? "Failed to import GitHub repository. Ensure it is public.");
        }
      }
    } catch (err: any) {
      setBusy(false);
      setServerError(err?.message || "An unexpected error occurred.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" role="dialog" aria-modal="true" data-testid="create-dialog">
      <form onSubmit={submit} className="w-full max-w-lg rounded-2xl bg-[#0d131f] border border-slate-700 shadow-2xl p-6 space-y-4 text-xs" noValidate>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="create-title" className="text-base font-bold text-white flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-indigo-400" />
              <span>Create / Import Project</span>
            </h2>
            <p className="text-slate-400 mt-0.5">Scaffold a starter, upload an existing ZIP archive, or clone from GitHub.</p>
          </div>
          <button type="button" onClick={onClose} disabled={busy} aria-label="Close" className="text-slate-400 hover:text-white disabled:opacity-40">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Source Mode Tabs */}
        <div className="grid grid-cols-3 gap-1 p-1 bg-slate-900 border border-slate-800 rounded-xl">
          <button
            type="button"
            onClick={() => setMode("template")}
            className={`py-2 rounded-lg font-semibold flex items-center justify-center gap-1.5 transition-colors ${
              mode === "template" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
            }`}
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>Starter</span>
          </button>
          <button
            type="button"
            onClick={() => setMode("upload")}
            className={`py-2 rounded-lg font-semibold flex items-center justify-center gap-1.5 transition-colors ${
              mode === "upload" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
            }`}
          >
            <Upload className="h-3.5 w-3.5" />
            <span>Upload ZIP</span>
          </button>
          <button
            type="button"
            onClick={() => setMode("git")}
            className={`py-2 rounded-lg font-semibold flex items-center justify-center gap-1.5 transition-colors ${
              mode === "git" ? "bg-indigo-600 text-white shadow-sm" : "text-slate-400 hover:text-white"
            }`}
          >
            <GitBranch className="h-3.5 w-3.5" />
            <span>GitHub URL</span>
          </button>
        </div>

        {/* 1. ZIP File Selector */}
        {mode === "upload" && (
          <div className="space-y-2">
            <span className="font-semibold text-slate-300">ZIP File Archive</span>
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-700 hover:border-indigo-500 rounded-xl p-4 text-center cursor-pointer transition-colors bg-slate-900/50"
            >
              <FolderArchive className="h-8 w-8 text-indigo-400 mx-auto mb-2" />
              {selectedZip ? (
                <div className="text-white font-medium">
                  Selected: <span className="text-indigo-300">{selectedZip.name}</span> ({(selectedZip.size / 1024).toFixed(1)} KB)
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="text-slate-300 font-medium">Click to browse or drag & drop .zip file</p>
                  <p className="text-[11px] text-slate-500">Extracts source files and auto-detects dependencies</p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                onChange={handleZipChange}
                className="hidden"
              />
            </div>
          </div>
        )}

        {/* 2. GitHub URL Input */}
        {mode === "git" && (
          <div className="space-y-2">
            <label className="block space-y-1">
              <span className="font-semibold text-slate-300">GitHub Repository URL</span>
              <input
                value={gitUrl}
                onChange={(e) => handleGitUrlChange(e.target.value)}
                placeholder="https://github.com/facebook/react"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white outline-none focus:border-indigo-500"
              />
            </label>
            <label className="block space-y-1">
              <span className="font-semibold text-slate-300">Branch</span>
              <input
                value={gitBranch}
                onChange={(e) => setGitBranch(e.target.value)}
                placeholder="main"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white outline-none focus:border-indigo-500"
              />
            </label>
          </div>
        )}

        {/* 3. Starter Template dropdown */}
        {mode === "template" && (
          <label className="block space-y-1">
            <span className="font-semibold text-slate-300">Starter template</span>
            <select
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              disabled={busy}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white outline-none focus:border-indigo-500"
            >
              {TEMPLATES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
        )}

        {/* Project Name */}
        <label className="block space-y-1">
          <span className="font-semibold text-slate-300">Project Name</span>
          <input
            data-testid="create-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setTouched(true)}
            disabled={busy}
            placeholder="my-cool-project"
            className={`w-full bg-slate-900 border rounded-lg px-3 py-2 text-white outline-none focus:border-indigo-500 ${
              touched && problem ? "border-rose-500" : "border-slate-700"
            }`}
          />
          {touched && problem && <span className="block text-rose-300" data-testid="create-name-error">{problem}</span>}
        </label>

        {/* Description */}
        <label className="block space-y-1">
          <span className="font-semibold text-slate-300">
            Description <span className="font-normal text-slate-500">(optional)</span>
          </span>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={busy}
            placeholder="High-performance backend or frontend repository"
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white outline-none focus:border-indigo-500"
          />
        </label>

        {serverError && (
          <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-500/40 text-rose-200" role="alert">
            <strong>Action failed:</strong> {serverError}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-2 disabled:opacity-60 shadow-glow"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            <span>
              {busy
                ? "Working..."
                : mode === "upload"
                ? "Upload"
                : mode === "git"
                ? "Import"
                : "Create Project"}
            </span>
            {!busy && <ArrowRight className="h-3.5 w-3.5" />}
          </button>
        </div>
      </form>
    </div>
  );
}
