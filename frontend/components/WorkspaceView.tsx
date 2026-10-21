"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileCode,
  Folder,
  FolderOpen,
  FolderX,
  GitFork,
  FlaskConical,
  Code2,
  Eye,
  Layers,
  Bot,
  Play,
} from "lucide-react";
import {
  fetchFile,
  fetchProject,
  fetchTree,
  getChatStatus,
  saveFileContent,
  type ChatStatusData,
  type FileContentData,
  type ProjectApiItem,
  type TreeNode,
} from "@/lib/api";
import {
  afterEdit,
  anySaving,
  conflictPaths,
  disposeModels,
  hasUnsavedChanges,
  isDirty,
  isSha256,
  keysToDispose,
  modelKeysFor,
  nextActiveAfterClose,
  normalizePath,
  saveStateFor,
  withBuffer,
  withoutSaveState,
  withSaveState,
  type OpenFile,
  type SaveStates,
} from "@/lib/editorSession";
import { overwriteWithMine, reloadFromDisk, saveFile, type FlowContext, type FlowResult } from "@/lib/saveFlow";
import { EditorPanel } from "@/editor/EditorPanel";
import { SAMPLE_FILES, SAMPLE_FILE_BY_PATH, SAMPLE_PROJECT, SCENARIO, LAYER_BY_ID } from "@/lib/sampleScenario";
import { LayerGraph } from "@/components/LayerGraph";
import { ImpactAnalysis } from "@/components/ImpactAnalysis";
import { ModificationPreview } from "@/components/ModificationPreview";
import { AICopilotPanel } from "@/chat/AICopilotPanel";
import { RealProjectGraph } from "@/components/RealProjectGraph";
import { RealImpactView } from "@/components/RealImpactView";
import { LivePreview } from "@/components/LivePreview";
import { RealPreviewView } from "@/components/RealPreviewView";
import { useChangeFlow } from "@/lib/useChangeFlow";

export type ProjectRef = { kind: "real"; name: string } | { kind: "sample" };
type Tab = "run" | "code" | "graph" | "impact" | "preview";

interface TNode {
  name: string;
  path: string;
  type: "file" | "directory";
  children?: TNode[];
}

function treeFromPaths(paths: string[]): TNode[] {
  const root: TNode[] = [];
  for (const p of paths) {
    const parts = p.split("/");
    let level = root;
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join("/");
      const isFile = i === parts.length - 1;
      let node = level.find((n) => n.name === part && n.type === (isFile ? "file" : "directory"));
      if (!node) {
        node = { name: part, path, type: isFile ? "file" : "directory", children: isFile ? undefined : [] };
        level.push(node);
      }
      if (!isFile) level = node.children as TNode[];
    });
  }
  return root;
}

function firstFile(nodes: TNode[]): string | null {
  for (const n of nodes) {
    if (n.type === "file") return n.path;
    const inner = n.children ? firstFile(n.children) : null;
    if (inner) return inner;
  }
  return null;
}

type Loadable<T> =
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "missing"; message: string }
  | { status: "error"; message: string };

interface WorkspaceViewProps {
  project: ProjectRef;
  onBack: () => void;
  onOpenSample: () => void;
  /** Reports whether any open file has unsaved edits, so the app can warn before they are lost. */
  onDirtyChange?: (dirty: boolean) => void;
}

type Notice = { tone: "info" | "error"; text: string };

export function WorkspaceView({ project, onBack, onOpenSample, onDirtyChange }: WorkspaceViewProps) {
  const isSample = project.kind === "sample";
  const [tab, setTab] = useState<Tab>(project.kind === "real" ? "run" : "code");
  // Counts saves, applied changes and undos, so the live preview knows when to load the page again.
  const [changeCount, setChangeCount] = useState(0);
  const [scenarioSelected, setScenarioSelected] = useState(false);
  const [meta, setMeta] = useState<Loadable<ProjectApiItem>>({ status: "loading" });
  const [tree, setTree] = useState<Loadable<TNode[]>>({ status: "loading" });
  // The file shown in the editor (real project) or in the read-only sample viewer.
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [isAiOpen, setIsAiOpen] = useState(true);

  // Real-file editing state: every open file keeps its own buffer, so switching files never loses edits.
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  // Optional citation target line range to reveal in the active editor without changing content or dirty state.
  const [revealTarget, setRevealTarget] = useState<{ path: string; lineStart: number; lineEnd: number; token: number } | null>(null);
  // The result of the last save/reload/overwrite of EACH open file, keyed by normalized path. Keeping it per
  // file means a conflict on file A stays on A while you work on file B (see lib/editorSession.ts).
  const [saveStates, setSaveStates] = useState<SaveStates>({});
  // Bumped whenever another project is opened, so a slow response for the old project is ignored.
  const sessionRef = useRef(0);
  // The open files as of right now. Async code that outlives a render (opening the first file after the
  // tree loads) must read this, not the `openFiles` it closed over, which may belong to the previous project.
  const openFilesRef = useRef<OpenFile[]>([]);
  openFilesRef.current = openFiles;
  const saveStatesRef = useRef<SaveStates>({});
  saveStatesRef.current = saveStates;
  const flowBusyRef = useRef(false);

  const name = project.kind === "real" ? project.name : SAMPLE_PROJECT.name;

  // Reset when another project is opened
  useEffect(() => {
    sessionRef.current += 1;
    openFilesRef.current = [];
    saveStatesRef.current = {};
    setTab(project.kind === "real" ? "run" : "code");
    setScenarioSelected(false);
    setSelectedPath(null);
    setCollapsed(new Set());
    setOpenFiles([]);
    setNotice(null);
    setRevealTarget(null);
    setSaveStates({}); // save results and conflicts belong to one project's files
  }, [name, isSample]);

  // Monaco keeps a model (text + undo history) per file key and the editor wrapper never frees it when a tab closes, so a
  // reopened file would reuse the old model: its undo history can bring back old or discarded text (and, because the
  // base hash is the current disk hash, Save would then overwrite newer disk content without a conflict), and memory
  // grows. Dispose the model of every file that is no longer open, including everything on a project switch.
  const modelKeysRef = useRef<string[]>([]); // the model keys of the files open as of the last run of the effect below
  const releaseModels = (keys: string[], attempt = 0) => {
    // Dynamic import keeps the wrapper out of the initial bundle. __getMonacoInstance() never loads Monaco: it returns the
    // already-initialised instance, or null if the editor was never mounted (then no models exist and nothing happens).
    void import("@monaco-editor/react").then(({ loader }) => {
      const monaco = loader.__getMonacoInstance();
      if (!monaco) return;
      // Re-read the open keys NOW: a file reopened since is skipped, and a model still attached to an editor is never disposed.
      const { deferred } = disposeModels(monaco, keys, modelKeysRef.current);
      if (deferred.length > 0 && attempt < 5) window.setTimeout(() => releaseModels(deferred, attempt + 1), 50);
    });
  };
  useEffect(() => {
    const projectId = meta.status === "ok" ? meta.data.id : null;
    // With files open but no known project id the keys cannot be named: do nothing rather than guess. With NO files open
    // the answer is known without a project id (nothing is open), which is what releases a previous project's models.
    if (openFiles.length > 0 && projectId === null) return;
    const next = openFiles.length === 0 || projectId === null ? [] : modelKeysFor(projectId, openFiles);
    const gone = keysToDispose(modelKeysRef.current, next);
    modelKeysRef.current = next; // idempotent: running the effect again with the same files finds nothing to dispose
    if (gone.length > 0) releaseModels(gone);
  }, [openFiles, meta]); // releaseModels only reads refs, so it is not a dependency

  const dirty = hasUnsavedChanges(openFiles);
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  // The browser's own "leave this page?" prompt, so a refresh or closed tab cannot silently drop edits.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  /** Open a real file from disk in the editor (or just focus it if it is already open). */
  const openRealFile = async (projectId: string, path: string) => {
    if (openFilesRef.current.some((f) => f.path === path)) {
      setSelectedPath(path);
      setNotice(null);
      return;
    }
    const session = sessionRef.current;
    setNotice({ tone: "info", text: `Opening ${path}...` });
    const r = await fetchFile(projectId, path);
    if (session !== sessionRef.current) return;
    if (!r.ok || !r.data) {
      setNotice({ tone: "error", text: `Cannot open ${path}: ${r.message ?? "unknown error"}` });
      return;
    }
    const data: FileContentData = r.data;
    // Keep the server's hash of exactly what was loaded: every save is based on it. A response without a
    // valid hash leaves it empty, and such a file then refuses to save (nothing is sent without a hash).
    const baseSha256 = isSha256(data.sha256) ? data.sha256 : "";
    setOpenFiles((prev) =>
      prev.some((f) => f.path === data.path)
        ? prev
        : [...prev, { path: data.path, language: data.language, saved: data.content, buffer: data.content, baseSha256 }]
    );
    setSelectedPath(data.path);
    setNotice(null);
  };

  /** Used by the tree, citations and the graph: opens in the editor for real projects, selects for the sample. */
  const selectFile = (path: string) => {
    if (project.kind === "real") {
      if (meta.status === "ok") void openRealFile(meta.data.id, path);
    } else {
      setSelectedPath(path);
    }
  };

  /** Used by citations: opens in the editor and reveals line range */
  const handleOpenFileWithRange = (path: string, lineStart?: number, lineEnd?: number) => {
    selectFile(path);
    setTab("code");
    if (typeof lineStart === "number") {
      setRevealTarget({
        path,
        lineStart,
        lineEnd: typeof lineEnd === "number" ? lineEnd : lineStart,
        token: Date.now(),
      });
    } else {
      setRevealTarget(null);
    }
  };

  const closeFile = (path: string) => {
    const f = openFiles.find((x) => x.path === path);
    if (f && isDirty(f) && !window.confirm(`Discard unsaved changes to ${path}?`)) return;
    setSelectedPath(nextActiveAfterClose(openFiles, path, selectedPath));
    setOpenFiles((prev) => prev.filter((x) => x.path !== path));
    setSaveStates((prev) => withoutSaveState(prev, path)); // only this file's result goes away
    setNotice(null);
  };

  const editFile = (path: string, value: string) => {
    setOpenFiles((prev) => withBuffer(prev, path, value));
    // Typing clears THIS file's old result, but never an unresolved conflict (or a save in flight), and never
    // another file's state.
    setSaveStates((prev) => afterEdit(prev, path));
  };

  /**
   * Run one of the save flows (save / reload / overwrite, see lib/saveFlow.ts) for a file of the open real
   * project, then apply its result. The result's update is applied to the latest open files, so anything
   * typed while the request was in flight is kept, and a response for a project that is no longer open is ignored.
   */
  const runFlow = async (path: string, flow: (ctx: FlowContext, path: string) => Promise<FlowResult>, showSaving: boolean) => {
    // One save/reload/overwrite at a time across ALL files, so a double click (or a click on another file's
    // button) cannot start a second request while one is in flight.
    if (project.kind !== "real" || meta.status !== "ok" || flowBusyRef.current || anySaving(saveStatesRef.current)) return;
    const session = sessionRef.current;
    const ctx: FlowContext = {
      api: { fetchFile, saveFileContent },
      projectId: meta.data.id,
      getFiles: () => openFilesRef.current,
      confirm: (message) => window.confirm(message),
    };
    const previous = saveStateFor(saveStatesRef.current, path); // this file's state before the flow started
    flowBusyRef.current = true;
    try {
      if (showSaving) setSaveStates((prev) => withSaveState(prev, path, { status: "saving", path }));
      const result = await flow(ctx, path);
      if (session !== sessionRef.current) return;
      setOpenFiles(result.update);
      if (result.save && (result.save.status === "verified" || result.save.status === "warning")) setChangeCount((n) => n + 1);
      // Only THIS file's state changes, and only if its tab is still open (a closed file keeps no state).
      const stillOpen = openFilesRef.current.some((f) => normalizePath(f.path) === normalizePath(path));
      if (!stillOpen) setSaveStates((prev) => withoutSaveState(prev, path));
      else if (result.save) setSaveStates((prev) => withSaveState(prev, path, result.save!));
      // A cancelled confirmation (or nothing to save) returns no state: put back what this file had before,
      // e.g. its conflict banner.
      else if (showSaving) setSaveStates((prev) => withSaveState(prev, path, previous));
    } finally {
      flowBusyRef.current = false;
    }
  };

  /** After a guided change wrote or restored files: reload each open copy that has no unsaved edits. Edited copies keep
   *  their buffer and meet the normal "changed on disk" conflict if saved. */
  const handleFilesChanged = async (paths: string[]) => {
    setChangeCount((n) => n + 1);
    for (const path of paths) {
      const open = openFilesRef.current.find((f) => normalizePath(f.path) === normalizePath(path));
      if (!open) continue;
      if (isDirty(open)) {
        setNotice({ tone: "info", text: `${path} was changed on disk but you have unsaved edits in it; it was not reloaded.` });
        continue;
      }
      await runFlow(open.path, reloadFromDisk, false);
    }
  };

  // One guided-change flow for the whole workspace: the Agent panel, the Impact tab and the Preview tab all show it, so
  // switching tabs never loses the analysis or the prepared edits.
  const changeFlow = useChangeFlow(project.kind === "real" ? name : null, handleFilesChanged);
  const [chatStatus, setChatStatus] = useState<ChatStatusData | null>(null);
  useEffect(() => {
    if (project.kind !== "real") return;
    let cancelled = false;
    void getChatStatus(name).then((st) => {
      if (!cancelled) setChatStatus(st);
    });
    return () => {
      cancelled = true;
    };
  }, [project.kind, name]);
  const canSendChanges = !!chatStatus?.can_send;

  /** Save the active file with the hash it was loaded with, then read it back and compare before claiming success. */
  const saveActiveFile = () => (selectedPath ? runFlow(selectedPath, (ctx, p) => saveFile(ctx, p), true) : Promise.resolve());
  const reloadActiveFromDisk = (path: string) => runFlow(path, reloadFromDisk, false);
  const overwriteActiveWithMine = (path: string) => runFlow(path, overwriteWithMine, false);

  // Load real project metadata + file tree
  useEffect(() => {
    if (project.kind !== "real") {
      const nodes = treeFromPaths(SAMPLE_FILES.map((f) => f.path));
      setTree({ status: "ok", data: nodes });
      setSelectedPath(SAMPLE_FILE_BY_PATH["frontend/src/components/OrderList.tsx"].path);
      return;
    }
    let cancelled = false;
    setMeta({ status: "loading" });
    setTree({ status: "loading" });
    (async () => {
      const m = await fetchProject(project.name);
      if (cancelled) return;
      if (!m.ok || !m.data) {
        setMeta({ status: m.status === 404 ? "missing" : "error", message: m.message ?? "Unknown error" });
        setTree({ status: "error", message: m.message ?? "Unknown error" });
        return;
      }
      setMeta({ status: "ok", data: m.data });
      if (!m.data.workspace_exists) {
        setTree({ status: "missing", message: "This project's folder does not exist on disk." });
        return;
      }
      const t = await fetchTree(m.data.id);
      if (cancelled) return;
      if (!t.ok || !t.data) {
        setTree({ status: t.status === 404 ? "missing" : "error", message: t.message ?? "Unknown error" });
        return;
      }
      setTree({ status: "ok", data: t.data as TreeNode[] });
      const first = firstFile(t.data as TNode[]);
      if (first) await openRealFile(m.data.id, first);
    })();
    return () => {
      cancelled = true;
    };
  }, [project.kind, project.kind === "real" ? project.name : ""]);

  const sampleFile = isSample && selectedPath ? SAMPLE_FILE_BY_PATH[selectedPath] : undefined;
  const fileCount = useMemo(() => (tree.status === "ok" ? countFiles(tree.data) : 0), [tree]);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    ...(project.kind === "real" ? [{ id: "run" as Tab, label: "Run in Browser", icon: <Play className="h-3.5 w-3.5" /> }] : []),
    { id: "code", label: "Code", icon: <Code2 className="h-3.5 w-3.5" /> },
    { id: "graph", label: "Dependency Graph", icon: <GitFork className="h-3.5 w-3.5" /> },
    { id: "impact", label: "Impact Analysis", icon: <Layers className="h-3.5 w-3.5" /> },
    { id: "preview", label: "Modification Preview", icon: <Eye className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="h-full w-full flex flex-col min-h-0 bg-[#090d16] text-slate-200" data-testid="workspace-root" data-kind={project.kind}>
      {/* breadcrumb + status chips */}
      <div className="shrink-0 px-4 pt-3 pb-2 border-b border-slate-800 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex items-center gap-3">
          <nav className="flex items-center gap-1.5 text-xs text-slate-400" aria-label="Breadcrumb" data-testid="breadcrumbs">
            <button onClick={onBack} className="hover:text-white underline-offset-2 hover:underline">Projects</button>
            <ChevronRight className="h-3 w-3" />
            <span className="text-white font-semibold" data-testid="workspace-title">{isSample ? SAMPLE_PROJECT.title : name}</span>
          </nav>
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-semibold" data-testid="workspace-chips">
            {isSample ? (
              <>
                <Chip tone="violet">SAMPLE PROJECT</Chip>
                <Chip tone="slate">{SAMPLE_FILES.length} sample files</Chip>
              </>
            ) : meta.status === "ok" ? (
              <>
                {meta.data.workspace_exists ? <Chip tone="emerald">Real files on disk</Chip> : <Chip tone="amber">Folder missing on disk</Chip>}
                <Chip tone="slate">{meta.data.file_count} files</Chip>
              </>
            ) : meta.status === "loading" ? (
              <Chip tone="slate">Loading project...</Chip>
            ) : (
              <Chip tone="rose">project could not be loaded</Chip>
            )}
          </div>
        </div>

        {/* AI Copilot toggle button */}
        <button
          onClick={() => setIsAiOpen(!isAiOpen)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
            isAiOpen
              ? "bg-indigo-600/20 border-indigo-500/50 text-indigo-300 shadow-glow"
              : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"
          }`}
          data-testid="toggle-ai-copilot"
          title="Toggle AI Copilot Assistant"
        >
          <Bot className="h-3.5 w-3.5 text-indigo-400" />
          <span>AI Copilot</span>
        </button>
      </div>

      {/* tabs */}
      <div className="shrink-0 px-3 border-b border-slate-800 flex items-center justify-between" role="tablist" data-testid="workspace-tabs">
        <div className="flex items-center gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              data-testid={`tab-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors ${tab === t.id ? "border-indigo-500 text-white" : "border-transparent text-slate-400 hover:text-white"}`}
            >
              {t.icon}
              {t.label}
              {t.id !== "code" && isSample && <span className="ml-1 px-1.5 rounded bg-violet-500/20 text-violet-200 text-[9px]">sample</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 flex overflow-hidden" data-testid="workspace-content">
        {tab === "code" && (
          <div className="h-full w-full flex min-h-0 overflow-hidden">
            {/* 1. File Tree */}
            <div className="w-64 lg:w-72 shrink-0 border-r border-slate-800 bg-[#0b101b] flex flex-col min-h-0">
              <div className="px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-800 flex items-center justify-between">
                <span>{isSample ? "Sample files" : "Files on disk"}</span>
                {tree.status === "ok" && <span className="text-slate-600 font-mono">({fileCount})</span>}
              </div>
              <div className="flex-1 overflow-y-auto py-1 text-xs" data-testid="file-tree">
                {tree.status === "loading" && <p className="p-3 text-slate-500">Loading files...</p>}
                {tree.status === "ok" && tree.data.length === 0 && <p className="p-3 text-slate-500" data-testid="tree-empty">The project folder is empty.</p>}
                {tree.status === "ok" && (
                  <TreeView
                    nodes={tree.data}
                    depth={0}
                    selected={selectedPath}
                    collapsed={collapsed}
                    onToggle={(p) => setCollapsed((prev) => { const n = new Set(prev); n.has(p) ? n.delete(p) : n.add(p); return n; })}
                    onSelect={selectFile}
                  />
                )}
                {(tree.status === "missing" || tree.status === "error") && (
                  <p className="p-3 text-slate-500" data-testid="tree-unavailable">No files to show.</p>
                )}
              </div>
            </div>

            {/* 2. Code Viewer / Editor */}
            <div className="flex-1 min-w-0 flex flex-col min-h-0 bg-[#070a12] border-r border-slate-800" data-testid="code-viewer">
              {isSample && sampleFile ? (
                <CodeView
                  path={sampleFile.path}
                  language={sampleFile.language}
                  content={sampleFile.content}
                  chips={[<Chip key="s" tone="violet">sample file · read-only</Chip>, <Chip key="l" tone="slate">{LAYER_BY_ID[sampleFile.layer].label}</Chip>]}
                  highlight={scenarioSelected ? SCENARIO.from : undefined}
                />
              ) : !isSample && meta.status === "ok" && openFiles.length > 0 ? (
                <>
                  {notice && (
                    <div
                      className={`shrink-0 px-4 py-1.5 text-[11px] border-b ${notice.tone === "error" ? "bg-rose-500/10 border-rose-400/30 text-rose-200" : "bg-slate-800/60 border-slate-700 text-slate-300"}`}
                      data-testid="editor-notice"
                      role={notice.tone === "error" ? "alert" : "status"}
                    >
                      {notice.text}
                    </div>
                  )}
                  <div className="flex-1 min-h-0">
                    <EditorPanel
                      projectKey={meta.data.id}
                      files={openFiles}
                      activePath={selectedPath}
                      save={saveStateFor(saveStates, selectedPath)}
                      conflictPaths={conflictPaths(saveStates)}
                      onSelect={selectFile}
                      onClose={closeFile}
                      onChange={editFile}
                      onSave={saveActiveFile}
                      onReloadFromDisk={reloadActiveFromDisk}
                      onOverwriteWithMine={overwriteActiveWithMine}
                      revealTarget={revealTarget && revealTarget.path === selectedPath ? revealTarget : null}
                    />
                  </div>
                </>
              ) : (
                <ViewerEmpty
                  tree={tree}
                  meta={meta}
                  notice={notice}
                  isSample={isSample}
                  onOpenSample={onOpenSample}
                />
              )}
            </div>

            {/* 3. AI Copilot Panel (Real Live Connected Chatbot) */}
            {isAiOpen && (
              <AICopilotPanel
                projectId={name}
                isOpen={isAiOpen}
                onOpenFile={handleOpenFileWithRange}
                onOpenDiffView={() => setTab("preview")}
                flow={changeFlow}
              />
            )}
          </div>
        )}

        {tab === "graph" && (
          <div className="h-full w-full flex min-h-0 overflow-hidden">
            <div className="flex-1 min-w-0 flex flex-col min-h-0">
              {isSample ? (
                <LayerGraph showScenario={scenarioSelected} />
              ) : (
                <RealProjectGraph
                  projectId={name}
                  onSelectFile={(p) => {
                    selectFile(p);
                    setTab("code");
                  }}
                />
              )}
            </div>
            {isAiOpen && (
              <AICopilotPanel
                projectId={name}
                isOpen={isAiOpen}
                onOpenFile={handleOpenFileWithRange}
                onOpenDiffView={() => setTab("preview")}
                flow={changeFlow}
              />
            )}
          </div>
        )}
        {tab === "run" && project.kind === "real" && (
          meta.status === "ok" ? (
            <LivePreview projectId={meta.data.id} changeCount={changeCount} onOpenCode={() => setTab("code")} />
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-slate-400" data-testid="live-waiting">Loading the project...</div>
          )
        )}
        {tab === "impact" && (
          isSample ? (
            <ImpactAnalysis selected={scenarioSelected} onSelect={setScenarioSelected} onShowGraph={() => setTab("graph")} onShowPreview={() => setTab("preview")} />
          ) : (
            <RealImpactView
              flow={changeFlow}
              canSend={canSendChanges}
              blockedReason={chatStatus?.reason}
              onOpenFile={handleOpenFileWithRange}
              onShowGraph={() => setTab("graph")}
              onShowPreview={() => setTab("preview")}
            />
          )
        )}
        {tab === "preview" && (
          isSample ? (
            <ModificationPreview scenarioSelected={scenarioSelected} onGoToImpact={() => setTab("impact")} />
          ) : (
            <RealPreviewView flow={changeFlow} onOpenFile={handleOpenFileWithRange} onGoToImpact={() => setTab("impact")} />
          )
        )}
      </div>
    </div>
  );
}

function countFiles(nodes: TNode[]): number {
  return nodes.reduce((n, x) => n + (x.type === "file" ? 1 : countFiles(x.children ?? [])), 0);
}

function Chip({ tone, children }: { tone: "violet" | "slate" | "emerald" | "amber" | "rose"; children: React.ReactNode }) {
  const tones = {
    violet: "bg-violet-500/15 border-violet-400/40 text-violet-200",
    slate: "bg-slate-800/80 border-slate-700 text-slate-300",
    emerald: "bg-emerald-500/10 border-emerald-400/30 text-emerald-300",
    amber: "bg-amber-500/10 border-amber-400/40 text-amber-200",
    rose: "bg-rose-500/10 border-rose-400/40 text-rose-200",
  } as const;
  return <span className={`px-2 py-0.5 rounded-full border ${tones[tone]}`}>{children}</span>;
}

function TreeView({ nodes, depth, selected, collapsed, onToggle, onSelect }: { nodes: TNode[]; depth: number; selected: string | null; collapsed: Set<string>; onToggle: (p: string) => void; onSelect: (p: string) => void }) {
  return (
    <ul>
      {nodes.map((n) =>
        n.type === "directory" ? (
          <li key={n.path}>
            <button onClick={() => onToggle(n.path)} className="w-full flex items-center gap-1.5 py-1 pr-2 hover:bg-slate-800/60 text-slate-300" style={{ paddingLeft: 8 + depth * 14 }}>
              {collapsed.has(n.path) ? <ChevronRight className="h-3 w-3 text-slate-500" /> : <ChevronDown className="h-3 w-3 text-slate-500" />}
              {collapsed.has(n.path) ? <Folder className="h-3.5 w-3.5 text-indigo-300" /> : <FolderOpen className="h-3.5 w-3.5 text-indigo-300" />}
              <span className="truncate">{n.name}</span>
            </button>
            {!collapsed.has(n.path) && <TreeView nodes={n.children ?? []} depth={depth + 1} selected={selected} collapsed={collapsed} onToggle={onToggle} onSelect={onSelect} />}
          </li>
        ) : (
          <li key={n.path}>
            <button
              onClick={() => onSelect(n.path)}
              data-testid="tree-file"
              data-path={n.path}
              className={`w-full flex items-center gap-1.5 py-1 pr-2 font-mono text-[11px] ${selected === n.path ? "bg-indigo-600/20 text-white font-semibold" : "text-slate-300 hover:bg-slate-800/60"}`}
              style={{ paddingLeft: 22 + depth * 14 }}
            >
              <FileCode className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
              <span className="truncate">{n.name}</span>
            </button>
          </li>
        )
      )}
    </ul>
  );
}

function CodeView({ path, language, content, chips, highlight }: { path: string; language: string; content: string; chips: React.ReactNode[]; highlight?: string }) {
  const lines = content.replace(/\n$/, "").split("\n");
  const hits = highlight ? lines.filter((l) => l.includes(highlight)).length : 0;
  return (
    <>
      <div className="shrink-0 px-4 py-2 border-b border-slate-800 bg-[#090d16] flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-slate-100 break-all" data-testid="code-path">{path}</span>
        <span className="text-slate-500">{language} · {lines.length} lines</span>
        <span className="flex gap-1.5 text-[10px] font-semibold ml-auto">{chips}</span>
      </div>
      {highlight && (
        <div className="shrink-0 px-4 py-1.5 bg-amber-500/10 border-b border-amber-400/20 text-[11px] text-amber-200" data-testid="highlight-note">
          Sample change selected: {hits} line{hits === 1 ? "" : "s"} in this file mention <span className="font-mono">{highlight}</span>.
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-auto" data-testid="code-scroll">
        <pre className="py-3 text-[12px] leading-5 font-mono text-slate-200 min-w-max" data-testid="code-content">
          {lines.map((line, i) => (
            <div key={i} className={`flex ${highlight && line.includes(highlight) ? "bg-amber-500/10" : ""}`}>
              <span className="w-12 shrink-0 pr-3 text-right text-slate-600 select-none">{i + 1}</span>
              <span className="whitespace-pre pr-6">{line || " "}</span>
            </div>
          ))}
        </pre>
      </div>
    </>
  );
}

function ViewerEmpty({ tree, meta, notice, isSample, onOpenSample }: { tree: Loadable<TNode[]>; meta: Loadable<ProjectApiItem>; notice: Notice | null; isSample: boolean; onOpenSample: () => void }) {
  let title = "Select a file";
  let body = "Choose a file in the tree to view it.";
  let showSample = false;
  if (!isSample) {
    if (meta.status === "loading" || tree.status === "loading") {
      title = "Loading...";
      body = "Reading the project from the backend.";
    } else if (meta.status !== "ok") {
      title = "Project could not be loaded";
      body = meta.status === "missing" ? "The backend has no project with this name." : (meta as { message: string }).message;
    } else if (tree.status === "missing") {
      title = "This project's folder is missing on disk";
      body = "There are no source files to show.";
      showSample = true;
    } else if (tree.status === "error") {
      title = "Files could not be loaded";
      body = (tree as { message: string }).message;
    } else if (tree.status === "ok" && tree.data.length === 0) {
      title = "The project folder is empty";
      body = "There are no files to show yet.";
      showSample = true;
    } else if (notice?.tone === "info") {
      title = "Loading file...";
      body = "";
    } else if (notice?.tone === "error") {
      title = "This file cannot be shown";
      body = notice.text;
    }
  }
  return (
    <div className="flex-1 flex items-center justify-center p-8" data-testid="viewer-empty">
      <div className="max-w-md text-center space-y-3">
        <FolderX className="h-8 w-8 text-slate-600 mx-auto" />
        <h3 className="text-base font-bold text-white" data-testid="viewer-empty-title">{title}</h3>
        {body && <p className="text-xs text-slate-400 leading-relaxed">{body}</p>}
        {showSample && (
          <button onClick={onOpenSample} className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-2 mx-auto">
            <FlaskConical className="h-3.5 w-3.5" /> Open the sample project instead
          </button>
        )}
      </div>
    </div>
  );
}
