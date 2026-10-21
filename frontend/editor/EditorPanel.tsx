"use client";

import React from "react";
import dynamic from "next/dynamic";
import { AlertTriangle, Check, FileCode, Loader2, Save, X } from "lucide-react";
import { isDirty, monacoLanguage, normalizePath, reloadCount, type OpenFile, type SaveState } from "@/lib/editorSession";

export type { SaveState };

// Monaco touches `window`, so it is only ever loaded in the browser.
const MonacoSurface = dynamic(() => import("./MonacoSurface"), {
  ssr: false,
  loading: () => <div className="p-4 text-xs text-slate-500">Loading editor...</div>,
});

interface EditorPanelProps {
  /** Distinguishes models of different projects that contain the same relative path. */
  projectKey: string;
  files: OpenFile[];
  activePath: string | null;
  /** The save state of the ACTIVE file only (each file keeps its own; see lib/editorSession.ts). */
  save: SaveState;
  /** Paths with an unresolved conflict, so their tabs can show it even while another file is active. */
  conflictPaths?: string[];
  onSelect: (path: string) => void;
  onClose: (path: string) => void;
  onChange: (path: string, value: string) => void;
  onSave: () => void;
  /** Conflict action: replace the editor's text with what is on disk (the caller confirms first). */
  onReloadFromDisk: (path: string) => void;
  /** Conflict action: overwrite the file on disk with the editor's text (the caller confirms first). */
  onOverwriteWithMine: (path: string) => void;
  /** Optional citation target line range to reveal and select without modifying content. */
  revealTarget?: { lineStart: number; lineEnd: number; token: number } | null;
}

const baseName = (p: string) => p.split("/").pop() || p;

/** Real file editor: Monaco over the buffers held by the workspace. Edits stay in memory until saved. */
export function EditorPanel({
  projectKey,
  files,
  activePath,
  save,
  conflictPaths = [],
  onSelect,
  onClose,
  onChange,
  onSave,
  onReloadFromDisk,
  onOverwriteWithMine,
  revealTarget,
}: EditorPanelProps) {
  const active = files.find((f) => f.path === activePath) ?? null;
  const saving = save.status === "saving";
  const message = active && save.status !== "idle" && save.path === active.path ? save : null;
  const conflict = message?.status === "conflict" ? message : null;

  return (
    <div className="h-full flex flex-col min-h-0" data-testid="editor-panel">
      <div className="shrink-0 flex items-stretch overflow-x-auto border-b border-slate-800 bg-[#080c14]" role="tablist" data-testid="editor-tabs">
        {files.map((f) => {
          const isActive = f.path === activePath;
          const dirty = isDirty(f);
          const conflicted = conflictPaths.includes(normalizePath(f.path));
          return (
            <div
              key={f.path}
              role="tab"
              aria-selected={isActive}
              data-testid="editor-tab"
              data-path={f.path}
              data-dirty={dirty}
              data-conflict={conflicted}
              title={conflicted ? `${f.path}: changed on disk, unresolved conflict` : f.path}
              onClick={() => onSelect(f.path)}
              className={`group flex items-center gap-2 pl-3 pr-1.5 py-1.5 text-xs font-mono border-r border-slate-800 cursor-pointer ${
                isActive ? "bg-[#070a12] text-white border-t-2 border-t-indigo-500" : "text-slate-400 hover:bg-slate-900/60 hover:text-slate-200 border-t-2 border-t-transparent"
              }`}
            >
              <FileCode className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
              <span className="whitespace-nowrap">{baseName(f.path)}</span>
              {dirty && <span className="h-1.5 w-1.5 rounded-full bg-amber-400" aria-label="unsaved changes" data-testid="dirty-dot" />}
              {conflicted && (
                <AlertTriangle className="h-3 w-3 text-amber-400 shrink-0" aria-label="unresolved conflict: the file changed on disk" data-testid="conflict-marker" />
              )}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onClose(f.path);
                }}
                aria-label={`Close ${f.path}`}
                className="p-0.5 rounded text-slate-500 hover:text-white hover:bg-slate-700/60"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          );
        })}
      </div>

      {active ? (
        <>
          <div className="shrink-0 px-4 py-2 border-b border-slate-800 bg-[#090d16] flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="font-mono text-slate-100 break-all" data-testid="code-path">{active.path}</span>
            <div className="flex items-center gap-2">
              {message?.status === "verified" && (
                <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium" data-testid="save-status" data-state="verified">
                  <Check className="h-3 w-3" /> Saved. Read back {message.bytes} bytes from disk and they match.
                </span>
              )}
              {message?.status === "warning" && (
                <span className="flex items-center gap-1 text-[11px] text-amber-300 font-medium" data-testid="save-status" data-state="warning">
                  <AlertTriangle className="h-3 w-3" /> {message.message}
                </span>
              )}
              {message?.status === "error" && (
                <span className="flex items-center gap-1 text-[11px] text-rose-300 font-medium" data-testid="save-status" data-state="error">
                  <AlertTriangle className="h-3 w-3" /> Not saved: {message.message}
                </span>
              )}
              {conflict && (
                <span className="flex items-center gap-1 text-[11px] text-amber-300 font-medium" data-testid="save-status" data-state="conflict">
                  <AlertTriangle className="h-3 w-3" /> Not saved: the file changed on disk
                </span>
              )}
              <button
                onClick={onSave}
                disabled={!isDirty(active) || saving}
                data-testid="save-button"
                title="Save to disk (Ctrl+S)"
                className="flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed text-white font-semibold text-xs transition-colors"
              >
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                <span>{saving ? "Saving..." : "Save"}</span>
              </button>
            </div>
          </div>

          {conflict && (
            <div
              className="shrink-0 px-4 py-2 border-b border-amber-400/30 bg-amber-500/10 text-xs text-amber-100 flex flex-wrap items-center gap-x-4 gap-y-2"
              role="alert"
              data-testid="conflict-banner"
            >
              <p className="flex-1 min-w-[16rem] leading-relaxed">
                <strong>This file changed on disk after you opened it.</strong> Your edits are still here and have{" "}
                <strong>not</strong> been saved; nothing on disk was changed. Choose what to do:
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onReloadFromDisk(active.path)}
                  data-testid="conflict-reload"
                  title="Replace my text with the file as it is on disk (asks before discarding my edits)"
                  className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-100 font-semibold"
                >
                  Reload from disk
                </button>
                <button
                  onClick={() => onOverwriteWithMine(active.path)}
                  data-testid="conflict-overwrite"
                  title="Replace the file on disk with my text (asks first)"
                  className="px-2.5 py-1 rounded bg-rose-700 hover:bg-rose-600 border border-rose-500 text-white font-semibold"
                >
                  Overwrite disk with my text
                </button>
              </div>
            </div>
          )}

          <div className="flex-1 min-h-0" data-testid="monaco-host">
            <MonacoSurface
              modelKey={`${projectKey}:${active.path}`}
              value={active.buffer}
              reloadCount={reloadCount(active)}
              language={monacoLanguage(active.language)}
              onChange={(value) => onChange(active.path, value)}
              onSave={onSave}
              revealTarget={revealTarget}
            />
          </div>

          <div className="shrink-0 h-6 border-t border-slate-800 bg-[#080c14] px-3 flex items-center justify-between text-[11px] font-mono text-slate-500">
            <span>UTF-8 · {monacoLanguage(active.language)}</span>
            <span data-testid="dirty-state">{isDirty(active) ? "unsaved changes" : "no unsaved changes"}</span>
          </div>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center text-xs text-slate-500" data-testid="editor-no-file">
          No file open. Pick a file in the tree.
        </div>
      )}
    </div>
  );
}
