"use client";

import React, { useEffect, useRef } from "react";
import Editor, { loader, type OnMount } from "@monaco-editor/react";
import { MONACO_ASSET_PATH, installMonacoCancellationHandler } from "@/lib/monacoCancellation";
import { shouldResetHistory } from "@/lib/editorSession";

// Serve Monaco from this app (public/monaco, copied by scripts/copy-monaco.mjs), not from a CDN.
loader.config({ paths: { vs: MONACO_ASSET_PATH } });

interface MonacoSurfaceProps {
  /** Unique per project + file. Monaco keeps one model (text, undo history, cursor) per key. */
  modelKey: string;
  value: string;
  language: string;
  /** Goes up each time this file is replaced by a confirmed "Reload from disk". */
  reloadCount: number;
  onChange: (value: string) => void;
  onSave: () => void;
  /** Optional citation target line range to reveal and select without modifying content. */
  revealTarget?: { lineStart: number; lineEnd: number; token: number } | null;
}

export default function MonacoSurface({ modelKey, value, language, reloadCount, onChange, onSave, revealTarget }: MonacoSurfaceProps) {
  // The editor is mounted once, so the Ctrl+S command must call the latest handler.
  const saveRef = useRef(onSave);
  saveRef.current = onSave;

  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null);
  const reloadsSeen = useRef(new Map<string, number>()); // model key -> reload count last shown by this editor

  // After a confirmed reload the file's text was replaced through an ordinary (undoable) edit, so Ctrl+Z would bring back
  // the text from before the reload while the base hash already is the current disk hash: Save would then overwrite newer
  // disk content without a conflict. Setting the same text on the model drops its undo/redo history (and nothing else),
  // so neither can cross the reload. Edits made afterwards undo normally. Runs after the wrapper has applied the new text.
  useEffect(() => {
    const seen = reloadsSeen.current.get(modelKey);
    reloadsSeen.current.set(modelKey, reloadCount);
    if (!shouldResetHistory(seen, reloadCount)) return;
    const model = editorRef.current?.getModel();
    const monaco = monacoRef.current;
    // Only ever touch the model of THIS file, and only while it is alive.
    if (!model || !monaco || model.isDisposed() || model.uri.toString() !== monaco.Uri.parse(modelKey).toString()) return;
    model.setValue(value);
  }, [modelKey, reloadCount]); // `value` is deliberately not a dependency: it is the reloaded text of this very render

  // Reveal citation line range when requested. Safe: strictly checks that the active model URI
  // matches modelKey so async tab switches never select lines in the wrong file.
  // Never touches text, undo history, dirty state, base hashes or save flows.
  useEffect(() => {
    if (!revealTarget) return;
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    const model = editor?.getModel();
    if (!editor || !monaco || !model || model.isDisposed()) return;
    if (model.uri.toString() !== monaco.Uri.parse(modelKey).toString()) return;

    const lineCount = model.getLineCount();
    const startLine = Math.max(1, Math.min(revealTarget.lineStart, lineCount));
    const endLine = Math.max(startLine, Math.min(revealTarget.lineEnd, lineCount));

    editor.revealRangeInCenter({
      startLineNumber: startLine,
      startColumn: 1,
      endLineNumber: endLine,
      endColumn: model.getLineMaxColumn(endLine),
    });
    editor.setSelection({
      startLineNumber: startLine,
      startColumn: 1,
      endLineNumber: endLine,
      endColumn: model.getLineMaxColumn(endLine),
    });
  }, [modelKey, revealTarget]);

  // Monaco rejects an internal promise with an expected "Canceled" error when the model is switched right after a
  // cursor move (a pending 50 ms highlight is cancelled). Mark exactly that signature as handled while the editor is
  // mounted; everything else stays visible. Reference-counted, so remounts never leave duplicate listeners.
  useEffect(() => installMonacoCancellationHandler(window, window.location.origin), []);

  return (
    <Editor
      height="100%"
      theme="vs-dark"
      path={modelKey}
      language={language}
      value={value}
      onChange={(next) => onChange(next ?? "")}
      onMount={(editor, monaco) => {
        editorRef.current = editor;
        monacoRef.current = monaco;
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => saveRef.current());
      }}
      loading={<div className="p-4 text-xs text-slate-500">Loading editor...</div>}
      options={{
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 13,
        scrollBeyondLastLine: false,
        renderWhitespace: "selection",
      }}
    />
  );
}
