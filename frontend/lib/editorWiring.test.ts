// Source-level tripwire for the React wiring of the save-conflict flows. The behaviour itself is tested in
// saveFlow.test.ts (and in the browser run); this only fails if someone bypasses the flows in the UI code
// again, e.g. by calling the save API directly without the loaded hash, or by dropping a conflict action.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (rel: string) => readFileSync(new URL(`../${rel}`, import.meta.url), "utf-8");
const WORKSPACE = read("components/WorkspaceView.tsx");
const PANEL = read("editor/EditorPanel.tsx");
const API = read("lib/api.ts");

describe("the editor saves only through the conflict-safe flows", () => {
  it("the save API requires the base hash and sends it as base_sha256", () => {
    expect(API).toMatch(/saveFileContent = \(nameOrId: string, path: string, content: string, baseSha256: string\)/);
    expect(API).toContain("base_sha256: baseSha256");
  });

  it("WorkspaceView never calls the save API directly; it goes through saveFile / reloadFromDisk / overwriteWithMine", () => {
    expect(WORKSPACE).not.toMatch(/await saveFileContent\(/);
    expect(WORKSPACE).toContain("saveFile(ctx, p)");
    expect(WORKSPACE).toContain("runFlow(path, reloadFromDisk");
    expect(WORKSPACE).toContain("runFlow(path, overwriteWithMine");
  });

  it("a file's hash is taken from the server's response when it is opened, and an unusable hash is left empty", () => {
    expect(WORKSPACE).toContain("isSha256(data.sha256) ? data.sha256 : \"\"");
    expect(WORKSPACE).toContain("baseSha256 }");
  });

  it("flows read the open files at call time and results are applied to the latest state", () => {
    expect(WORKSPACE).toContain("getFiles: () => openFilesRef.current");
    expect(WORKSPACE).toContain("setOpenFiles(result.update)");
  });

  it("typing goes through afterEdit, which never dismisses an unresolved conflict and only touches that file", () => {
    expect(WORKSPACE).toContain("setSaveStates((prev) => afterEdit(prev, path))");
  });

  it("save state is kept per file: there is no single global save state any more", () => {
    expect(WORKSPACE).not.toMatch(/useState<SaveState>/);
    expect(WORKSPACE).not.toMatch(/\bsetSave\(/);
    expect(WORKSPACE).toContain("useState<SaveStates>({})");
  });

  it("each result is written only to its own file's entry", () => {
    expect(WORKSPACE).toContain("withSaveState(prev, path, result.save!)");
    expect(WORKSPACE).toContain('withSaveState(prev, path, { status: "saving", path })');
  });

  it("closing a file forgets only that file's state", () => {
    expect(WORKSPACE).toContain("setSaveStates((prev) => withoutSaveState(prev, path))");
  });

  it("switching projects resets all save and conflict state", () => {
    expect(WORKSPACE).toMatch(/setSaveStates\(\{\}\);[^\n]*project's files/);
    expect(WORKSPACE).toContain("saveStatesRef.current = {};");
  });

  it("the one-request-at-a-time guard is global: a busy flag AND any file saving", () => {
    expect(WORKSPACE).toContain("flowBusyRef.current || anySaving(saveStatesRef.current)");
  });

  it("the editor is given the ACTIVE file's state and the list of conflicted files for the tab markers", () => {
    expect(WORKSPACE).toContain("save={saveStateFor(saveStates, selectedPath)}");
    expect(WORKSPACE).toContain("conflictPaths={conflictPaths(saveStates)}");
    expect(PANEL).toContain('data-testid="conflict-marker"');
    expect(PANEL).toContain("data-conflict={conflicted}");
  });

  it("the editor shows both explicit conflict actions, and both are wired to handlers", () => {
    for (const id of ["conflict-banner", "conflict-reload", "conflict-overwrite"]) expect(PANEL).toContain(`data-testid="${id}"`);
    expect(PANEL).toContain("Reload from disk");
    expect(PANEL).toContain("Overwrite disk with my text");
    expect(WORKSPACE).toContain("onReloadFromDisk={reloadActiveFromDisk}");
    expect(WORKSPACE).toContain("onOverwriteWithMine={overwriteActiveWithMine}");
  });

  it("the banner says the edits are kept and not saved", () => {
    expect(PANEL).toContain("Your edits are still here");
    expect(PANEL).toContain("been saved");
  });
});

// ---------------------------------------------------------------------------------------------------------
// Monaco's expected-cancellation handler (lib/monacoCancellation.ts). Behaviour is unit-tested there; these checks
// only fail if the wiring is dropped, widened, or if the fix is "achieved" by switching the feature off.
// ---------------------------------------------------------------------------------------------------------
const SURFACE = read("editor/MonacoSurface.tsx");
const CANCELLATION = read("lib/monacoCancellation.ts");
// Negative checks ("must not contain X") look at CODE only: a comment that explains why X is absent must not trip them.
const stripComments = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'])\/\/.*$/gm, "$1");
const SURFACE_CODE = stripComments(SURFACE);
const CANCELLATION_CODE = stripComments(CANCELLATION);

describe("Monaco cancellation handler: registration and cleanup", () => {
  it("is registered in an effect that returns the release function, so unmount removes it", () => {
    expect(SURFACE).toMatch(
      /useEffect\(\s*\(\)\s*=>\s*installMonacoCancellationHandler\(window,\s*window\.location\.origin\),\s*\[\]\s*\)/
    );
    expect(SURFACE).toContain('from "@/lib/monacoCancellation"');
  });

  it("is registered once per editor mount, with no other global error handlers", () => {
    expect((SURFACE_CODE.match(/installMonacoCancellationHandler\(/g) ?? []).length).toBe(1);
    expect(SURFACE_CODE).not.toMatch(/window\.onerror|onunhandledrejection\s*=|addEventListener\(\s*["']error["']/);
  });

  it("the loader and the handler share one Monaco asset path constant (no hard-coded copy to drift)", () => {
    expect(SURFACE).toContain("loader.config({ paths: { vs: MONACO_ASSET_PATH } })");
    expect(SURFACE_CODE).not.toContain('"/monaco/vs"');
    expect(CANCELLATION).toContain('export const MONACO_ASSET_PATH = "/monaco/vs"');
  });
});

describe("Monaco cancellation handler: stays narrow", () => {
  it("only ever listens for 'unhandledrejection'", () => {
    expect(CANCELLATION).toContain('"unhandledrejection"');
    expect(CANCELLATION_CODE).not.toMatch(/addEventListener\(\s*["'](?!unhandledrejection)/);
  });

  it("never stops propagation, so other listeners still receive every event", () => {
    expect(CANCELLATION_CODE).not.toMatch(/stopPropagation|stopImmediatePropagation/);
  });

  it("does not touch global error plumbing (stack depth, onerror, console)", () => {
    expect(CANCELLATION_CODE).not.toMatch(/stackTraceLimit|window\.onerror|console\.(error|warn)/);
  });

  it("requires the name AND the message AND a Monaco top frame (never one of them alone)", () => {
    expect(CANCELLATION).toContain("reason.name !== CANCELED || reason.message !== CANCELED");
    expect(CANCELLATION).toContain("isMonacoFrame(top, origin)");
    expect(CANCELLATION).toContain("reason instanceof Error");
  });
});

describe("occurrence highlighting is preserved (the fix must not switch the feature off)", () => {
  it("MonacoSurface does not configure occurrencesHighlight at all, so Monaco's default (on) applies", () => {
    expect(SURFACE_CODE).not.toMatch(/occurrencesHighlight/);
  });

  it("the helper does not touch editor options", () => {
    expect(CANCELLATION_CODE).not.toMatch(/occurrencesHighlight|updateOptions/);
  });
});

// ---------------------------------------------------------------------------------------------------------
// Monaco model disposal (WorkspaceView + lib/editorSession.ts). The decisions are unit-tested in editorSession.test.ts
// and checked in a real browser; these tests only fail if the wiring is dropped or made unsafe.
// ---------------------------------------------------------------------------------------------------------
const SESSION = read("lib/editorSession.ts");
const WORKSPACE_CODE = stripComments(WORKSPACE);

describe("Monaco model disposal: the effect", () => {
  it("compares the open keys with those of the previous run and remembers the new ones (idempotent under repeated effects)", () => {
    expect(WORKSPACE).toContain("const modelKeysRef = useRef<string[]>([])");
    expect(WORKSPACE).toContain("keysToDispose(modelKeysRef.current, next)");
    expect(WORKSPACE).toContain("modelKeysRef.current = next;");
  });

  it("names the keys with the shared helper and the project id, and never guesses when the id is unknown", () => {
    expect(WORKSPACE).toContain("modelKeysFor(projectId, openFiles)");
    expect(WORKSPACE).toContain("if (openFiles.length > 0 && projectId === null) return;");
  });

  it("with no files open it releases everything without needing a project id (this is what frees a previous project's models)", () => {
    expect(WORKSPACE).toContain("openFiles.length === 0 || projectId === null ? [] : modelKeysFor(projectId, openFiles)");
  });

  it("runs on changes to the open files (and the project metadata), nothing else", () => {
    expect(WORKSPACE).toContain("}, [openFiles, meta]);");
  });
});

describe("Monaco model disposal: safety", () => {
  it("disposes only through disposeModels, which refuses attached models; the component never calls dispose() itself", () => {
    expect(WORKSPACE).toContain("disposeModels(monaco, keys, modelKeysRef.current)");
    expect(WORKSPACE_CODE).not.toMatch(/\.dispose\(\)/);
  });

  it("re-reads the open keys at disposal time (a file reopened meanwhile is skipped)", () => {
    expect(WORKSPACE).toContain("modelKeysRef.current)");
    expect(WORKSPACE).not.toMatch(/disposeModels\(monaco, keys, (next|openFiles)/);
  });

  it("retries a model that was still attached, a bounded number of times", () => {
    expect(WORKSPACE).toContain("deferred.length > 0 && attempt < 5");
    expect(WORKSPACE).toContain("releaseModels(deferred, attempt + 1)");
  });

  it("gets Monaco from the loader's non-loading accessor via a dynamic import: it can never start loading Monaco (no CDN, no network)", () => {
    expect(WORKSPACE).toContain('import("@monaco-editor/react")');
    expect(WORKSPACE).toContain("loader.__getMonacoInstance()");
    expect(WORKSPACE_CODE).not.toMatch(/loader\.init\(|loader\.config\(/);
    expect(WORKSPACE_CODE).not.toMatch(/from "@monaco-editor\/react"/); // no static import: the wrapper stays out of the initial bundle
  });

  it("does nothing when Monaco was never initialised (null instance)", () => {
    expect(WORKSPACE).toContain("if (!monaco) return;");
  });
});

describe("Monaco model disposal: the key matches the one the editor is mounted with", () => {
  it("EditorPanel mounts the editor with '<projectKey>:<path>' ...", () => {
    expect(PANEL).toContain("modelKey={`${projectKey}:${active.path}`}");
  });

  it("... and the shared helper builds '<projectKey>:<normalized path>' (identical for backend-reported paths)", () => {
    expect(SESSION).toContain("export const modelKey = (projectKey: string, path: string): string => `${projectKey}:${normalizePath(path)}`;");
  });

  it("WorkspaceView passes the project's id as the editor's projectKey (the same id the keys are built from)", () => {
    expect(WORKSPACE).toContain("projectKey={meta.data.id}");
  });
});

// ---------------------------------------------------------------------------------------------------------
// Undo history after "Reload from disk" (MonacoSurface + EditorPanel + lib/editorSession.ts). The behaviour is checked in
// a real browser; these tests fail if the wiring is dropped, widened, or the reset is made to touch the wrong model.
// ---------------------------------------------------------------------------------------------------------
const SESSION_CODE = stripComments(SESSION);

describe("undo history after a reload: the wiring", () => {
  it("EditorPanel gives the editor the active file's reload count", () => {
    expect(PANEL).toContain("reloadCount={reloadCount(active)}");
  });

  it("the surface remembers, per model key, the reload count it last showed", () => {
    expect(SURFACE).toContain("reloadsSeen = useRef(new Map<string, number>())");
    expect(SURFACE).toContain("reloadsSeen.current.get(modelKey)");
    expect(SURFACE).toContain("reloadsSeen.current.set(modelKey, reloadCount)");
  });

  it("the decision comes from the shared pure helper, and the effect runs only when the key or the count changes", () => {
    expect(SURFACE).toContain("shouldResetHistory(seen, reloadCount)");
    expect(SURFACE).toContain("}, [modelKey, reloadCount]);");
  });

  it("drops the history by setting the reloaded text on the model", () => {
    expect(SURFACE_CODE).toContain("model.setValue(value);");
  });

  it("only ever touches this file's own, live model", () => {
    expect(SURFACE_CODE).toContain("model.isDisposed()");
    expect(SURFACE_CODE).toContain("model.uri.toString() !== monaco.Uri.parse(modelKey).toString()");
  });

  it("does not dispose, re-key or recreate the model, and does not touch options", () => {
    expect(SURFACE_CODE).not.toMatch(/\.dispose\(|createModel|updateOptions|executeEdits|pushUndoStop/);
  });

  it("the reload counter is bumped only by withReloaded, never by the save paths", () => {
    expect((SESSION_CODE.match(/reloads:/g) ?? []).length).toBe(1);
    expect(SESSION_CODE).toMatch(/withReloaded[\s\S]*reloads: reloadCount\(f\) \+ 1/);
  });

  it("the cancellation handler and the save flow files are not involved", () => {
    expect(SURFACE).toContain("installMonacoCancellationHandler(window, window.location.origin)");
    expect(stripComments(read("lib/saveFlow.ts"))).not.toMatch(/setValue|\breloads\b|\bundo\b/i);
  });
});
