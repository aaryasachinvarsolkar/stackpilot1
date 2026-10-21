"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, ExternalLink, Globe, Loader2, Play, RefreshCw, RotateCw, Server, Square, Terminal } from "lucide-react";
import {
  getPreviewInfo,
  getRunStatus,
  previewFileUrl,
  restartRun,
  runningAppUrl,
  startRun,
  stopRun,
  type PreviewInfo,
  type RunStatus,
} from "@/lib/api";

// The page runs in the browser, inside an iframe whose sandbox deliberately has NO "allow-same-origin": the project's
// JavaScript gets its own empty origin, so it cannot call the StackPilot API or read anything of this app. Its calls to its
// own backend are re-pointed (in the served copy only) at a forwarder that reaches the one port StackPilot started for it.
export const PREVIEW_SANDBOX = "allow-scripts allow-forms allow-modals allow-popups";

const BUSY_STATES = ["preparing", "installing", "starting"];

interface LivePreviewViewProps {
  projectId: string;
  info: PreviewInfo | null;
  loading: boolean;
  error: string | null;
  /** Changes whenever the iframe should load the files again. */
  version: number;
  /** The static page being shown (one of the candidates). */
  page: string | null;
  /** The user pressed Run (or the page started by itself): the static page is shown. */
  running: boolean;
  /** What last made the preview reload: shown so a change visibly arrives. */
  updatedNote: string | null;
  /** The project's backend: null while unknown. */
  run: RunStatus | null;
  runBusy: boolean;
  showLog: boolean;
  onRun: () => void;
  onPickPage: (path: string) => void;
  onOpenCode: () => void;
  onStartBackend: () => void;
  onStopBackend: () => void;
  onRestartBackend: () => void;
  onToggleLog: () => void;
}

function BackendBar({ info, run, runBusy, showLog, onStartBackend, onStopBackend, onRestartBackend, onToggleLog }: Pick<LivePreviewViewProps, "info" | "run" | "runBusy" | "showLog" | "onStartBackend" | "onStopBackend" | "onRestartBackend" | "onToggleLog">) {
  const button = "px-3 py-1 rounded-lg font-semibold flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed";
  if (!run) {
    return (
      <div className="shrink-0 px-4 py-1.5 border-b border-slate-800 text-[11px] text-slate-500" data-testid="backend-unknown">
        Backend controls are not available right now.
      </div>
    );
  }
  if (!run.plan && !run.plan_problem) {
    if (info?.kind === "static" && !info.needs_backend) {
      return (
        <div className="shrink-0 px-4 py-1.5 border-b border-slate-800 text-[11px] text-slate-500" data-testid="backend-none">
          Static site: there is no backend to start. The page below is the whole project.
        </div>
      );
    }
    return (
      <div className="shrink-0 px-4 py-2 border-b border-slate-800 text-[11px] text-slate-400" data-testid="backend-noplan">
        No way to start a backend was found for this project. If it has one, add a <span className="font-mono text-slate-200">stackpilot.json</span> with a
        <span className="font-mono text-slate-200"> start</span> command (and optionally <span className="font-mono text-slate-200">install</span>) to the project, e.g.{" "}
        <span className="font-mono text-slate-300">{`{"start": ["{python}", "app.py", "{port}"], "python": true}`}</span>
      </div>
    );
  }
  if (run.plan_problem) {
    return (
      <div className="shrink-0 px-4 py-2 border-b border-slate-800 text-[11px] text-amber-200" data-testid="backend-planproblem">
        {run.plan_problem}
      </div>
    );
  }
  const plan = run.plan!;
  const missing = run.missing_tools ?? [];
  const busy = BUSY_STATES.includes(run.state);
  const running = run.state === "running";
  const dot = running ? "bg-emerald-500" : busy ? "bg-amber-400 animate-pulse" : run.state === "failed" ? "bg-rose-500" : "bg-slate-600";
  const label = running ? `Backend running on port ${run.port}` : busy ? run.message || "Starting..." : run.state === "failed" ? run.message || "The backend stopped." : "Backend not running";

  return (
    <div className="shrink-0 border-b border-slate-800 text-xs" data-testid="backend-bar" data-state={run.state}>
      <div className="px-4 py-2 flex flex-wrap items-center gap-3">
        <span className={`h-2 w-2 rounded-full ${dot}`} />
        <span className="font-semibold text-slate-200" data-testid="backend-label">{label}</span>
        {!run.allowed || missing.length > 0 ? null : (
          <>
            {!running && !busy && (
              <button onClick={onStartBackend} disabled={runBusy} className={`${button} bg-emerald-600 hover:bg-emerald-500 text-white`} data-testid="backend-start">
                <Server className="h-3.5 w-3.5" /> {run.state === "failed" ? "Try again" : "Start backend"}
              </button>
            )}
            {running && (
              <button onClick={onRestartBackend} disabled={runBusy} className={`${button} bg-slate-800 hover:bg-slate-700 text-white`} data-testid="backend-restart">
                <RotateCw className="h-3.5 w-3.5" /> Restart
              </button>
            )}
            {(running || busy) && (
              <button onClick={onStopBackend} disabled={runBusy} className={`${button} bg-slate-800 hover:bg-slate-700 text-white`} data-testid="backend-stop">
                <Square className="h-3.5 w-3.5" /> Stop
              </button>
            )}
          </>
        )}
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-300" />}
        <button onClick={onToggleLog} className="ml-auto text-slate-400 hover:text-white flex items-center gap-1" data-testid="backend-log-toggle">
          <Terminal className="h-3.5 w-3.5" /> {showLog ? "Hide log" : "Show log"}
        </button>
      </div>
      {!run.allowed && (
        <div className="mx-4 mb-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-400/30 text-[11px] text-amber-100 space-y-1.5 leading-relaxed" data-testid="backend-blocked">
          <div className="font-semibold">Starting a backend is switched off.</div>
          <div>
            It runs the project&apos;s own code on your computer, so you turn it on yourself. Add this line to the backend&apos;s <span className="font-mono">.env</span> file, then restart the backend and reload this page:
          </div>
          <code className="block px-2 py-1 rounded bg-black/40 font-mono text-amber-200 select-all" data-testid="backend-blocked-line">ALLOW_RUNNING_PROJECT_CODE=true</code>
        </div>
      )}
      {missing.length > 0 && (
        <div className="mx-4 mb-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-400/30 text-[11px] text-amber-100 leading-relaxed" data-testid="backend-missing-tool">
          {run.missing_tools_help ?? `Needs ${missing.join(", ")}, which is not installed on this computer.`}
        </div>
      )}
      {plan.warnings.length > 0 && (
        <ul className="mx-4 mb-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-400/30 text-[11px] text-amber-100 leading-relaxed list-disc pl-6" data-testid="backend-warnings">
          {plan.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {!running && !busy && (
        <div className="px-4 pb-2 text-[11px] text-slate-500" data-testid="backend-plan">
          Will run ({plan.source}): {plan.install ? <span className="font-mono text-slate-400">{plan.install}</span> : null}
          {plan.install ? " then " : ""}
          <span className="font-mono text-slate-400">{plan.start}</span>. This runs the project&apos;s own code on your computer.
        </div>
      )}
      {showLog && (
        <pre className="mx-4 mb-2 p-2 max-h-48 overflow-auto rounded-lg bg-[#080c14] text-[10px] leading-snug font-mono text-slate-300 select-text whitespace-pre-wrap" data-testid="backend-log">
          {run.log.length ? run.log.join("\n") : "No output yet."}
        </pre>
      )}
    </div>
  );
}

/** Pure display of the live preview; `LivePreview` below loads the data and keeps the state. */
export function LivePreviewView(props: LivePreviewViewProps) {
  const { projectId, info, loading, error, version, page, running, updatedNote, run, onRun, onPickPage, onOpenCode } = props;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-slate-400" data-testid="live-loading">
        <RefreshCw className="h-4 w-4 animate-spin mr-2" /> Looking at your project...
      </div>
    );
  }
  if (error || !info) {
    return (
      <div className="h-full flex items-center justify-center p-8" data-testid="live-error">
        <div role="alert" className="max-w-md text-center space-y-3 text-xs">
          <AlertTriangle className="h-8 w-8 text-rose-300 mx-auto" />
          <p className="text-rose-200">{error ?? "The preview could not be prepared."}</p>
          <button onClick={onRun} className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold">Try again</button>
        </div>
      </div>
    );
  }

  const staticPage = info.kind === "static" && page ? page : null;
  const appRunning = run?.state === "running";
  // A page of the project itself wins; a project with no page of its own (a Next/Vite/Express app) is shown through the forwarder.
  const src = staticPage ? previewFileUrl(projectId, staticPage, version) : appRunning ? runningAppUrl(projectId, version) : null;
  const framed = src !== null && (staticPage ? running : appRunning);

  const toolbar = staticPage || appRunning ? (
    <div className="shrink-0 px-4 py-2 border-b border-slate-800 flex flex-wrap items-center gap-3 text-xs">
      <button onClick={onRun} className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-2" data-testid="live-run">
        {framed ? <RefreshCw className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        {framed ? "Refresh preview" : "Run project"}
      </button>
      {staticPage && info.candidates.length > 1 ? (
        <select
          value={staticPage}
          onChange={(e) => onPickPage(e.target.value)}
          className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 font-mono text-[11px] text-slate-200"
          aria-label="Page to show"
          data-testid="live-page-select"
        >
          {info.candidates.map((c) => (
            <option key={c.path} value={c.path}>{c.path}</option>
          ))}
        </select>
      ) : (
        <span className="font-mono text-[11px] text-slate-400">{staticPage ?? "through the running backend"}</span>
      )}
      {src && (
        <a href={src} target="_blank" rel="noopener noreferrer" className="text-slate-400 hover:text-white flex items-center gap-1" data-testid="live-open-tab">
          <ExternalLink className="h-3.5 w-3.5" /> Open in a new tab
        </a>
      )}
      <span className="text-slate-500 ml-auto" data-testid="live-note">
        {updatedNote ?? "Shows your saved files. Save or apply a change and it updates here."}
      </span>
    </div>
  ) : null;

  let body: React.ReactNode;
  if (framed) {
    body = (
      <iframe
        key={`${src}`}
        title="Project preview"
        src={src!}
        sandbox={PREVIEW_SANDBOX}
        referrerPolicy="no-referrer"
        className="flex-1 w-full bg-white border-0"
        data-testid="live-frame"
      />
    );
  } else if (staticPage) {
    body = (
      <div className="flex-1 flex items-center justify-center text-xs text-slate-500" data-testid="live-idle">
        Press &quot;Run project&quot; to show the page.
      </div>
    );
  } else {
    const server = info.kind === "server" || !!run?.plan;
    body = (
      <div className="flex-1 flex items-center justify-center p-8" data-testid={server ? "live-server" : "live-none"}>
        <div className="max-w-lg text-center space-y-3 text-xs">
          {server ? <Server className="h-8 w-8 text-amber-300 mx-auto" /> : <Globe className="h-8 w-8 text-slate-500 mx-auto" />}
          <h3 className="text-base font-bold text-white">{server ? "This project runs as a server" : "Nothing to show in the browser"}</h3>
          <p className="text-slate-400 leading-relaxed">{info.message}</p>
          {info.hints.length > 0 && (
            <ul className="text-left list-disc pl-6 space-y-1 text-slate-300" data-testid="live-hints">
              {info.hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          )}
          <button onClick={onOpenCode} className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold">Open the code</button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col min-h-0" data-testid={staticPage ? "live-static" : "live-shell"}>
      {toolbar}
      <BackendBar {...props} />
      {info.needs_backend && !appRunning && staticPage && (
        <div className="shrink-0 px-4 py-1.5 bg-amber-500/10 border-b border-amber-400/20 text-[11px] text-amber-200" data-testid="live-backend-note">
          {info.message}
        </div>
      )}
      {body}
    </div>
  );
}

interface LivePreviewProps {
  /** The project's ID (not its name). */
  projectId: string;
  /** Bumped by the workspace whenever a file was saved, applied or restored. */
  changeCount: number;
  onOpenCode: () => void;
}

export function LivePreview({ projectId, changeCount, onOpenCode }: LivePreviewProps) {
  const [info, setInfo] = useState<PreviewInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [version, setVersion] = useState(() => Date.now());
  const [updatedNote, setUpdatedNote] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [runBusy, setRunBusy] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const previousState = useRef<string>("idle");

  // Look at the project whenever it (or the number of tries) changes. A static page starts by itself: that is the "run".
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getPreviewInfo(projectId).then((r) => {
      if (cancelled) return;
      setLoading(false);
      if (!r.ok || !r.data) {
        setInfo(null);
        setError(r.message ?? "The preview could not be prepared.");
        return;
      }
      setInfo(r.data);
      setPage((current) => (current && r.data!.candidates.some((c) => c.path === current) ? current : r.data!.entry));
      setRunning(r.data.kind === "static");
      setVersion(Date.now());
    });
    return () => {
      cancelled = true;
    };
  }, [projectId, attempt]);

  // The backend's state: looked at once, then followed while it is changing (and slowly while it runs, to notice a crash).
  const state = run?.state ?? "idle";
  useEffect(() => {
    let cancelled = false;
    const look = async () => {
      const r = await getRunStatus(projectId);
      if (!cancelled) setRun(r.ok && r.data ? r.data : null);
    };
    if (run === null) {
      void look();
      return () => {
        cancelled = true;
      };
    }
    if (!BUSY_STATES.includes(state) && state !== "running") return;
    const timer = setTimeout(look, BUSY_STATES.includes(state) ? 1500 : 5000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [projectId, run, state]);

  // The backend just came up: load the page again so it picks up the live connection.
  useEffect(() => {
    if (previousState.current !== "running" && state === "running") {
      setVersion(Date.now());
      setUpdatedNote(`Backend started at ${new Date().toLocaleTimeString()}; page reloaded.`);
    }
    previousState.current = state;
  }, [state]);

  // A file was saved, applied or restored: load the page again so the change is visible straight away. A backend that does not
  // reload by itself is restarted first, and one that does gets a moment to pick the change up.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (running) {
      setVersion(Date.now());
      setUpdatedNote(`Updated at ${new Date().toLocaleTimeString()} after your change.`);
    }
    if (run?.state === "running" && run.allowed) {
      if (run.plan?.auto_reload) {
        const timer = setTimeout(() => {
          setVersion(Date.now());
          setUpdatedNote(`Backend reloaded after your change at ${new Date().toLocaleTimeString()}.`);
        }, 3000);
        return () => clearTimeout(timer);
      }
      void restartRun(projectId).then((r) => {
        if (r.ok && r.data) setRun(r.data);
      });
    }
  }, [changeCount]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (call: () => ReturnType<typeof startRun>, confirmText?: string) => {
    if (confirmText && !window.confirm(confirmText)) return;
    setRunBusy(true);
    const r = await call();
    setRunBusy(false);
    if (r.ok && r.data) setRun(r.data);
    else setRun((current) => (current ? { ...current, state: "failed", message: r.message ?? "That did not work.", log: [...current.log, r.message ?? "That did not work."] } : current));
  };

  const startBackend = () => {
    const plan = run?.plan;
    void act(
      () => startRun(projectId),
      plan
        ? `Start this project's backend?\n\nThis will ${plan.install ? `install its dependencies (${plan.install}) and ` : ""}run:\n${plan.start}\n\non your computer, in the project's folder. Only continue for a project you trust.`
        : undefined,
    );
  };

  const runAll = () => {
    if (error || !info) {
      setAttempt((n) => n + 1);
      return;
    }
    setRunning(true);
    setVersion(Date.now());
    setUpdatedNote(running ? `Refreshed at ${new Date().toLocaleTimeString()}.` : null);
  };

  return (
    <LivePreviewView
      projectId={projectId}
      info={info}
      loading={loading}
      error={error}
      version={version}
      page={page}
      running={running}
      updatedNote={updatedNote}
      run={run}
      runBusy={runBusy}
      showLog={showLog}
      onRun={runAll}
      onPickPage={(p) => {
        setPage(p);
        setVersion(Date.now());
      }}
      onOpenCode={onOpenCode}
      onStartBackend={startBackend}
      onStopBackend={() => void act(() => stopRun(projectId))}
      onRestartBackend={() => void act(() => restartRun(projectId))}
      onToggleLog={() => setShowLog((v) => !v)}
    />
  );
}
