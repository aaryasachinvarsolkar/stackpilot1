import { describe, expect, it, vi } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { LivePreviewView, PREVIEW_SANDBOX } from "@/components/LivePreview";
import { previewFileUrl, runningAppUrl, type PreviewInfo, type RunStatus } from "@/lib/api";

const STATIC: PreviewInfo = {
  kind: "static", entry: "frontend/index.html", candidates: [{ path: "frontend/index.html" }, { path: "docs/index.html" }],
  hints: ["FastAPI backend (requirements.txt): needs a Python server"], needs_backend: true,
  message: "This page runs in the browser from your files. It also looks like it has a server part that is not started.",
};
const SERVER: PreviewInfo = { kind: "server", entry: null, candidates: [], hints: ["Next.js app (package.json): needs its dev server"], needs_backend: true, message: "This project needs a running server." };
const NONE: PreviewInfo = { kind: "none", entry: null, candidates: [], hints: [], needs_backend: false, message: "No web page (index.html) was found." };

const PLAN = { kind: "python", source: "uvicorn backend.app:app, as named in start_backend.ps1", install: "python -m pip install -r requirements.txt", start: "python -m uvicorn backend.app:app --port {port}", app_ports: [8000], auto_reload: false, fixed_port: null, requires: [], warnings: [] };
const RUN: RunStatus = { allowed: true, blocked_reason: null, state: "idle", message: "", plan: PLAN, plan_problem: null, missing_tools: [], missing_tools_help: null, port: null, started_at: null, log: [] };

function view(over: Partial<React.ComponentProps<typeof LivePreviewView>> = {}) {
  return renderToStaticMarkup(
    React.createElement(LivePreviewView, {
      projectId: "11111111-2222-3333-4444-555555555555", info: STATIC, loading: false, error: null, version: 7, page: "frontend/index.html",
      running: true, updatedNote: null, run: null, runBusy: false, showLog: false, onRun: vi.fn(), onPickPage: vi.fn(), onOpenCode: vi.fn(),
      onStartBackend: vi.fn(), onStopBackend: vi.fn(), onRestartBackend: vi.fn(), onToggleLog: vi.fn(), ...over,
    }),
  );
}

describe("live preview", () => {
  it("runs a static page in a sandboxed iframe that points at the served file and the current version", () => {
    const html = view();
    expect(html).toContain('data-testid="live-frame"');
    expect(html).toContain("/api/projects/11111111-2222-3333-4444-555555555555/preview/frontend/index.html?v=7");
    expect(html).toContain(`sandbox="${PREVIEW_SANDBOX}"`);
    expect(html).toContain("Refresh preview");
  });

  it("never lets the page share this app's origin", () => {
    expect(PREVIEW_SANDBOX).toContain("allow-scripts");
    expect(PREVIEW_SANDBOX).not.toContain("allow-same-origin");
    expect(PREVIEW_SANDBOX).not.toContain("allow-top-navigation");
    const source = readFileSync(new URL("../components/LivePreview.tsx", import.meta.url), "utf-8");
    expect((source.match(/sandbox=/g) ?? []).length).toBe(1);
    expect(source).not.toMatch(/dangerouslySetInnerHTML|allow-same-origin["'` ]\s*[,+]/);
  });

  it("before it is run, shows a Run project button and no frame", () => {
    const html = view({ running: false });
    expect(html).toContain("Run project");
    expect(html).toContain('data-testid="live-idle"');
    expect(html).not.toContain("<iframe");
  });

  it("offers every page it found and a way to open it in its own tab", () => {
    const html = view();
    expect(html).toContain('data-testid="live-page-select"');
    expect(html).toContain("docs/index.html");
    expect(html).toContain('data-testid="live-open-tab"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("warns when the page probably needs a server that is not started", () => {
    expect(view()).toContain('data-testid="live-backend-note"');
    expect(view({ info: { ...STATIC, needs_backend: false, hints: [] } })).not.toContain('data-testid="live-backend-note"');
  });

  it("shows when a change arrived", () => {
    expect(view({ updatedNote: "Updated at 10:00:00 after your change." })).toContain("Updated at 10:00:00 after your change.");
  });

  it("explains a server project instead of pretending to run it", () => {
    const html = view({ info: SERVER, page: null, running: false });
    expect(html).toContain('data-testid="live-server"');
    expect(html).toContain("runs as a server");
    expect(html).toContain("Next.js app");
    expect(html).not.toContain("<iframe");
  });

  it("says so when there is nothing to show", () => {
    const html = view({ info: NONE, page: null, running: false });
    expect(html).toContain('data-testid="live-none"');
    expect(html).not.toContain("<iframe");
  });

  it("shows a failure with a way to retry, and a loading state", () => {
    expect(view({ info: null, error: "The backend could not be reached" })).toContain("The backend could not be reached");
    expect(view({ loading: true })).toContain('data-testid="live-loading"');
  });

  it("builds file addresses that keep folders and escape odd characters", () => {
    expect(previewFileUrl("abc", "my site/index.html", 3)).toMatch(/\/api\/projects\/abc\/preview\/my%20site\/index\.html\?v=3$/);
    expect(previewFileUrl("abc", "a/b.html")).not.toContain("?v=");
  });

  it("builds the address of a running project that has no page of its own", () => {
    expect(runningAppUrl("abc", 4)).toMatch(/\/api\/projects\/abc\/app\/\?v=4$/);
  });
});

describe("the backend panel", () => {
  const bar = (run: RunStatus | null, over: Partial<React.ComponentProps<typeof LivePreviewView>> = {}) => view({ run, ...over });

  it("says when it cannot tell, and says so for a plain static site instead of showing nothing", () => {
    expect(bar(null)).toContain('data-testid="backend-unknown"');
    const plain = bar({ ...RUN, plan: null }, { info: { ...STATIC, needs_backend: false, hints: [] } });
    expect(plain).toContain('data-testid="backend-none"');
    expect(plain).toContain("no backend to start");
    expect(plain).not.toContain("backend-noplan");
  });

  it("explains how to add a start command when a backend is expected but cannot be started", () => {
    const html = bar({ ...RUN, plan: null });
    expect(html).toContain('data-testid="backend-noplan"');
    expect(html).toContain("stackpilot.json");
  });

  it("reports a broken stackpilot.json", () => {
    expect(bar({ ...RUN, plan: null, plan_problem: "stackpilot.json is not valid JSON." })).toContain("stackpilot.json is not valid JSON.");
  });

  it("when running code is not allowed, says exactly how to allow it and offers no start button", () => {
    const html = bar({ ...RUN, allowed: false, blocked_reason: "Running a project's code is turned off (ALLOW_RUNNING_PROJECT_CODE is false). Set ALLOW_RUNNING_PROJECT_CODE=true in .env" });
    expect(html).toContain('data-testid="backend-blocked"');
    expect(html).toContain('data-testid="backend-blocked-line"');
    expect(html).toContain(">ALLOW_RUNNING_PROJECT_CODE=true<");
    expect(html).toContain(".env");
    expect(html).not.toContain('data-testid="backend-start"');
  });

  it("offers Start backend with the exact commands it would run, and says they run on this computer", () => {
    const html = bar(RUN);
    expect(html).toContain('data-testid="backend-start"');
    expect(html).toContain("Start backend");
    expect(html).toContain("python -m pip install -r requirements.txt");
    expect(html).toContain("python -m uvicorn backend.app:app --port {port}");
    expect(html).toContain("runs the project&#x27;s own code on your computer");
  });

  it("shows progress while installing and starting, with a Stop button and no Start", () => {
    for (const state of ["preparing", "installing", "starting"] as const) {
      const html = bar({ ...RUN, state, message: "Installing the project's dependencies" });
      expect(html).toContain(`data-state="${state}"`);
      expect(html).toContain("Installing the project&#x27;s dependencies");
      expect(html).toContain('data-testid="backend-stop"');
      expect(html).not.toContain('data-testid="backend-start"');
    }
  });

  it("when running, shows the port with Restart and Stop, and the page reaches the backend", () => {
    const html = bar({ ...RUN, state: "running", port: 51234 });
    expect(html).toContain("Backend running on port 51234");
    expect(html).toContain('data-testid="backend-restart"');
    expect(html).toContain('data-testid="backend-stop"');
    expect(html).not.toContain('data-testid="backend-plan"');
  });

  it("a failed backend shows why and offers another try; the log is shown on request", () => {
    const failed = bar({ ...RUN, state: "failed", message: "Installing the dependencies failed (exit code 1).", log: ["[10:00:00] ERROR: No matching distribution"] }, { showLog: true });
    expect(failed).toContain("Installing the dependencies failed (exit code 1).");
    expect(failed).toContain("Try again");
    expect(failed).toContain('data-testid="backend-log"');
    expect(failed).toContain("No matching distribution");
    expect(bar({ ...RUN, state: "failed", message: "x", log: ["secret-looking line"] })).not.toContain("secret-looking line");
  });

  it("renders log lines as text, never as HTML", () => {
    const html = bar({ ...RUN, state: "running", port: 1, log: ["<img src=x onerror=alert(1)>"] }, { showLog: true });
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("shows a project with no page of its own through the running backend, in the same sandbox", () => {
    const html = view({ info: { ...SERVER }, page: null, running: false, run: { ...RUN, state: "running", port: 4000 } });
    expect(html).toContain('data-testid="live-frame"');
    expect(html).toContain("/api/projects/11111111-2222-3333-4444-555555555555/app/?v=7");
    expect(html).toContain(`sandbox="${PREVIEW_SANDBOX}"`);
    expect(html).not.toContain('data-testid="live-idle"');
  });

  it("a server project that is not running yet explains itself and still offers Start backend", () => {
    const html = view({ info: SERVER, page: null, running: false, run: RUN });
    expect(html).toContain('data-testid="live-server"');
    expect(html).toContain('data-testid="backend-start"');
    expect(html).not.toContain("<iframe");
  });

  it("is shown for every kind of project, never silently absent", () => {
    const cases: [string, Partial<React.ComponentProps<typeof LivePreviewView>>][] = [
      ["static, no backend", { info: { ...STATIC, needs_backend: false, hints: [] }, run: { ...RUN, plan: null } }],
      ["static with a backend", { run: RUN }],
      ["server only", { info: SERVER, page: null, running: false, run: RUN }],
      ["nothing runnable", { info: NONE, page: null, running: false, run: { ...RUN, plan: null } }],
      ["unknown", { run: null }],
    ];
    for (const [name, over] of cases) {
      const html = view(over);
      expect(html, name).toMatch(/data-testid="backend-(bar|none|noplan|unknown)"/);
    }
  });

  it("names a missing program (such as Go) with how to get it, and offers no Start button", () => {
    const help = "This project needs a program that is missing. 'go' is not installed (or not on PATH) on this computer. Install Go from https://go.dev/dl/ and restart the backend.";
    const html = bar({ ...RUN, plan: { ...PLAN, kind: "go", start: "go run .", install: null, requires: ["go"] }, missing_tools: ["go"], missing_tools_help: help });
    expect(html).toContain('data-testid="backend-missing-tool"');
    expect(html).toContain("Install Go from https://go.dev/dl/");
    expect(html).not.toContain('data-testid="backend-start"');
  });

  it("shows warnings found in the project, such as a framework missing from package.json", () => {
    const html = bar({ ...RUN, plan: { ...PLAN, kind: "node", warnings: ["package.json runs 'next' but does not list it as a dependency."] } });
    expect(html).toContain('data-testid="backend-warnings"');
    expect(html).toContain("does not list it as a dependency");
    expect(html).toContain('data-testid="backend-start"');
  });

  it("explains the allow switch only when it is actually off", () => {
    expect(bar(RUN)).not.toContain("backend-blocked");
  });
});
