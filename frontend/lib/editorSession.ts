// Pure logic for the file editor: which buffers have unsaved edits, how a save is judged, and how the
// backend's language names map to Monaco's. No React and no network, so it is unit-tested directly.

export interface OpenFile {
  path: string;
  language: string;
  /** Content as last confirmed on disk. */
  saved: string;
  /** Content currently in the editor. */
  buffer: string;
  /**
   * SHA-256 of the file as it was on disk when `saved` was last read or written. Every save sends it as
   * base_sha256, so the server can refuse to overwrite a file that changed in the meantime. Empty when
   * the backend did not report one; such a file cannot be saved (see isSha256).
   */
  baseSha256: string;
  /**
   * Set when a save was accepted but the read-back showed the disk differs from what was submitted. The file
   * then counts as unsaved whatever its text looks like, and `baseSha256` stays the hash that was submitted, so
   * the next ordinary save is refused (409) instead of overwriting the unexpected disk version. Cleared only by
   * a verified save, a confirmed overwrite, or a confirmed reload.
   */
  unverified?: boolean;
  /**
   * How many times the file was replaced by a confirmed "Reload from disk" (absent = 0). The editor surface watches it
   * to drop the model's undo history after a reload, so Ctrl+Z / Ctrl+Y can never bring back text from before it.
   */
  reloads?: number;
}

export type SaveState =
  | { status: "idle" }
  | { status: "saving"; path: string }
  | { status: "verified"; path: string; bytes: number }
  | { status: "warning"; path: string; message: string }
  /** The file on disk changed since it was loaded (HTTP 409). The user's text is kept and unsaved. */
  | { status: "conflict"; path: string; message: string }
  | { status: "error"; path: string; message: string };

export const isDirty = (f: OpenFile): boolean => f.unverified === true || f.buffer !== f.saved;

export const hasUnsavedChanges = (files: OpenFile[]): boolean => files.some(isDirty);

export const byteLength = (text: string): number => new TextEncoder().encode(text).length;

/** True for a 64-character hexadecimal SHA-256 digest. */
export const isSha256 = (value: unknown): value is string => typeof value === "string" && /^[0-9a-fA-F]{64}$/.test(value);

export type SaveVerdict =
  | { kind: "verified"; bytes: number; sha256: string }
  | { kind: "length-mismatch"; sentBytes: number; reportedBytes: number }
  | { kind: "content-mismatch" }
  | { kind: "hash-mismatch" };

/**
 * Decide whether a save really landed. `written` is what the backend says it wrote (byte count and the
 * hash of the new content); `readBack` is what a fresh read of the file returned. "Verified" requires the
 * byte count, the content, and the hash reported by the write and by the read-back all to agree with what
 * was sent; anything else is reported as a problem rather than as a success. The verified hash is the
 * read-back one, i.e. what is really on disk.
 */
export function judgeSave(
  sent: string,
  written: { bytes: number; sha256: string },
  readBack: { content: string; sha256: string }
): SaveVerdict {
  const sentBytes = byteLength(sent);
  if (written.bytes !== sentBytes) return { kind: "length-mismatch", sentBytes, reportedBytes: written.bytes };
  if (readBack.content !== sent) return { kind: "content-mismatch" };
  if (!isSha256(readBack.sha256) || readBack.sha256.toLowerCase() !== String(written.sha256).toLowerCase()) {
    return { kind: "hash-mismatch" };
  }
  return { kind: "verified", bytes: sentBytes, sha256: readBack.sha256.toLowerCase() };
}

// Backend language names (see detect_language in backend/app/api/files.py) -> Monaco language ids.
// Monaco ships no TOML grammar, so it falls back to plain text.
const MONACO_LANGUAGE: Record<string, string> = {
  python: "python",
  typescript: "typescript",
  javascript: "javascript",
  json: "json",
  markdown: "markdown",
  go: "go",
  rust: "rust",
  java: "java",
  sql: "sql",
  html: "html",
  css: "css",
  yaml: "yaml",
  plaintext: "plaintext",
  toml: "plaintext",
};

export const monacoLanguage = (backendLanguage: string): string => MONACO_LANGUAGE[backendLanguage] ?? "plaintext";

/** Return the list with `path`'s buffer replaced; every other file is left as it was. */
export const withBuffer = (files: OpenFile[], path: string, buffer: string): OpenFile[] =>
  files.map((f) => (f.path === path ? { ...f, buffer } : f));

/**
 * Record that `sent` is now on disk with hash `sha256`. Only `saved` and `baseSha256` move: if the user kept
 * typing while the request was in flight, `buffer` still differs and the file correctly stays dirty.
 */
export const withSaved = (files: OpenFile[], path: string, sent: string, sha256: string): OpenFile[] =>
  files.map((f) => (f.path === path ? { ...f, saved: sent, baseSha256: sha256, unverified: false } : f));

/**
 * Mark a save as unverified: the read-back differed from what was submitted. Nothing else moves. The user's
 * text stays, `saved` stays, and above all `baseSha256` stays the hash that was SUBMITTED, never the hash of
 * the unexpected disk content, so the next ordinary save is rejected with 409 rather than silently
 * overwriting whatever is on disk. Only an explicit reload or overwrite resolves it.
 */
export const withUnverified = (files: OpenFile[], path: string): OpenFile[] =>
  files.map((f) => (f.path === path ? { ...f, unverified: true } : f));

/**
 * Replace the file's text with what is on disk (an explicit "reload"): the buffer becomes the disk content. The reload
 * counter goes up so the editor can forget the undo history of the text that was replaced (see `shouldResetHistory`).
 */
export const withReloaded = (files: OpenFile[], path: string, diskContent: string, sha256: string): OpenFile[] =>
  files.map((f) =>
    f.path === path
      ? { ...f, saved: diskContent, buffer: diskContent, baseSha256: sha256, unverified: false, reloads: reloadCount(f) + 1 }
      : f
  );

/** How many confirmed reloads this file has had. */
export const reloadCount = (f: OpenFile): number => f.reloads ?? 0;

/**
 * Should the editor drop a file's undo history now? Only when this file was reloaded since the editor last showed it:
 * `seen` is the reload count the editor saw for this model last time (undefined = it never showed the file, so the model
 * is brand new and has no history). A count that did not go up, or went down (file closed and reopened), changes nothing.
 */
export const shouldResetHistory = (seen: number | undefined, current: number): boolean =>
  seen !== undefined && current > seen;

/** After closing `path`, which file should become active (the neighbour, or null if none are left). */
export function nextActiveAfterClose(files: OpenFile[], closingPath: string, activePath: string | null): string | null {
  if (activePath !== closingPath) return activePath;
  const index = files.findIndex((f) => f.path === closingPath);
  const remaining = files.filter((f) => f.path !== closingPath);
  if (remaining.length === 0) return null;
  return remaining[Math.min(index, remaining.length - 1)].path;
}

// ---------------------------------------------------------------------------------------------------------
// Per-file save state. Each open file has its own result (saving / verified / warning / conflict / error),
// kept in a map keyed by the NORMALIZED path, so a conflict on file A survives anything done to file B.
// All helpers are pure: they return a new map and never mutate the one they are given.
// ---------------------------------------------------------------------------------------------------------

export type SaveStates = Readonly<Record<string, SaveState>>;

/**
 * The key a path is stored under: forward slashes, no leading "./" or "/", no doubled slashes. The backend
 * already reports paths this way; normalizing here means the same file can never end up under two keys
 * (and a conflict on it can never be "lost" under a differently spelled one).
 */
export function normalizePath(path: string): string {
  return path
    .replace(/\\/g, "/")
    .replace(/\/{2,}/g, "/")
    .replace(/^(\.\/)+/, "")
    .replace(/^\/+/, "");
}

const IDLE: SaveState = { status: "idle" };

/** The save state of one file ("idle" if it has none). */
export const saveStateFor = (states: SaveStates, path: string | null | undefined): SaveState =>
  path ? states[normalizePath(path)] ?? IDLE : IDLE;

/** Set one file's save state. Setting "idle" removes the entry. Other files are untouched. */
export function withSaveState(states: SaveStates, path: string, state: SaveState): SaveStates {
  const key = normalizePath(path);
  const { [key]: _previous, ...rest } = states;
  void _previous;
  return state.status === "idle" ? rest : { ...rest, [key]: state };
}

/**
 * After the user types in `path`: drop that file's old result (e.g. a "Saved" notice), but never an unresolved
 * conflict or a save in flight. Other files are untouched.
 */
export function afterEdit(states: SaveStates, path: string): SaveStates {
  const current = states[normalizePath(path)];
  if (!current || current.status === "saving" || current.status === "conflict") return states;
  return withSaveState(states, path, IDLE);
}

/** Forget a file's save state (its tab was closed). Other files are untouched. */
export const withoutSaveState = (states: SaveStates, path: string): SaveStates => withSaveState(states, path, IDLE);

/** The files that currently have an unresolved conflict. */
export const conflictPaths = (states: SaveStates): string[] =>
  Object.keys(states).filter((key) => states[key].status === "conflict");

/** True while any file has a save in flight. */
export const anySaving = (states: SaveStates): boolean => Object.values(states).some((s) => s.status === "saving");

// ---------------------------------------------------------------------------------------------------------
// Monaco model lifecycle. Monaco keeps one model (text + undo history) per file key and the editor wrapper never
// frees it when a tab is closed (it disposes only the CURRENT model when the whole editor unmounts). A reopened file
// then reuses the old model, whose undo history can bring back old or discarded text, and memory accumulates. The
// app therefore disposes the model of every file that is no longer open. The decisions are pure and live here.
// ---------------------------------------------------------------------------------------------------------

/**
 * The key an open file's Monaco model is stored under. It must equal the `path` the editor is mounted with
 * (EditorPanel passes `${projectKey}:${path}`; a wiring test keeps the two in step). Paths reported by the backend are
 * already normalized, so normalizing here changes nothing for them; it only guarantees one key per file.
 */
export const modelKey = (projectKey: string, path: string): string => `${projectKey}:${normalizePath(path)}`;

/** The model keys of a set of open files. */
export const modelKeysFor = (projectKey: string, files: readonly OpenFile[]): string[] =>
  files.map((file) => modelKey(projectKey, file.path));

/**
 * The keys that were open before and are not open now: each once, in their previous order. Pure: nothing is
 * disposed here, and the same inputs always give the same answer (so repeated effects are harmless).
 */
export function keysToDispose(previous: readonly string[], current: readonly string[]): string[] {
  const stillOpen = new Set(current);
  const seen = new Set<string>();
  const gone: string[] = [];
  for (const key of previous) {
    if (stillOpen.has(key) || seen.has(key)) continue;
    seen.add(key);
    gone.push(key);
  }
  return gone;
}

/** The small part of Monaco's API that disposal uses (the real `monaco` object satisfies it structurally). */
export interface MonacoModelApi {
  Uri: { parse(value: string): unknown };
  editor: {
    getModel(uri: never): { isDisposed(): boolean; dispose(): void } | null;
    getEditors(): ReadonlyArray<{ getModel(): unknown }>;
  };
}

export interface DisposeReport {
  /** Models that were disposed. */
  disposed: string[];
  /** Models still attached to an editor: NOT disposed, to be retried. */
  deferred: string[];
  /** Keys with nothing to do: reopened meanwhile, no such model, already disposed, or Monaco refused. */
  skipped: string[];
}

/**
 * Dispose the Monaco models for `keys`, except: a key that is open again (`stillOpenKeys`), a model that does not
 * exist or is already disposed, and, above all, a model that is still attached to an editor, which is never disposed
 * and is reported as `deferred`. A failing lookup or dispose never throws and never stops the other keys.
 */
export function disposeModels(monaco: MonacoModelApi, keys: readonly string[], stillOpenKeys: readonly string[]): DisposeReport {
  const open = new Set(stillOpenKeys);
  const report: DisposeReport = { disposed: [], deferred: [], skipped: [] };
  for (const key of keys) {
    if (open.has(key)) {
      report.skipped.push(key);
      continue;
    }
    try {
      const model = monaco.editor.getModel(monaco.Uri.parse(key) as never);
      if (!model || model.isDisposed()) {
        report.skipped.push(key);
        continue;
      }
      if (monaco.editor.getEditors().some((editor) => editor.getModel() === model)) {
        report.deferred.push(key);
        continue;
      }
      model.dispose();
      report.disposed.push(key);
    } catch {
      report.skipped.push(key);
    }
  }
  return report;
}
