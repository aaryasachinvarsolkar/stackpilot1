import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import {
  afterEdit,
  anySaving,
  byteLength,
  conflictPaths,
  disposeModels,
  hasUnsavedChanges,
  isDirty,
  isSha256,
  judgeSave,
  keysToDispose,
  modelKey,
  modelKeysFor,
  monacoLanguage,
  nextActiveAfterClose,
  normalizePath,
  reloadCount,
  saveStateFor,
  shouldResetHistory,
  withBuffer,
  withUnverified,
  withReloaded,
  withSaved,
  withSaveState,
  withoutSaveState,
  type MonacoModelApi,
  type OpenFile,
  type SaveState,
  type SaveStates,
} from "@/lib/editorSession";

const H1 = "1".repeat(64);
const H2 = "2".repeat(64);
const H3 = "3".repeat(64);

const file = (path: string, saved = "a", buffer = saved, baseSha256 = H1): OpenFile => ({
  path,
  language: "python",
  saved,
  buffer,
  baseSha256,
});

/** What the backend would report for a write of `text` that landed correctly. */
const landed = (text: string, sha256 = H2) => ({
  written: { bytes: byteLength(text), sha256 },
  readBack: { content: text, sha256 },
});

describe("dirty tracking", () => {
  it("a file is dirty only when the buffer differs from what is on disk", () => {
    expect(isDirty(file("a.py", "x", "x"))).toBe(false);
    expect(isDirty(file("a.py", "x", "x "))).toBe(true);
  });

  it("detects unsaved changes anywhere in the open files", () => {
    expect(hasUnsavedChanges([file("a.py"), file("b.py")])).toBe(false);
    expect(hasUnsavedChanges([file("a.py"), file("b.py", "x", "y")])).toBe(true);
    expect(hasUnsavedChanges([])).toBe(false);
  });

  it("editing one file leaves every other buffer untouched", () => {
    const before = [file("a.py", "1"), file("b.py", "2")];
    const after = withBuffer(before, "a.py", "edited");
    expect(after[0].buffer).toBe("edited");
    expect(after[1]).toBe(before[1]);
    expect(after[0].saved).toBe("1");
  });
});

describe("hashes", () => {
  it("recognises a 64-character hex digest and nothing else", () => {
    expect(isSha256("a".repeat(64))).toBe(true);
    expect(isSha256("A".repeat(64))).toBe(true);
    for (const bad of ["", "a".repeat(63), "a".repeat(65), "g".repeat(64), " " + "a".repeat(63), undefined, null, 123]) {
      expect(isSha256(bad)).toBe(false);
    }
  });
});

describe("judging a save", () => {
  it("is verified only when the reported size, the read-back content and the hashes all match what was sent", () => {
    const { written, readBack } = landed("hello\n");
    expect(judgeSave("hello\n", written, readBack)).toEqual({ kind: "verified", bytes: 6, sha256: H2 });
  });

  it("counts bytes, not characters, so non-ASCII text is checked correctly", () => {
    const text = "ünï ✓\r\n";
    expect(byteLength(text)).toBeGreaterThan(text.length);
    const { written, readBack } = landed(text);
    expect(judgeSave(text, written, readBack).kind).toBe("verified");
    expect(judgeSave(text, { ...written, bytes: text.length }, readBack).kind).toBe("length-mismatch");
  });

  it("reports a length mismatch when the backend wrote a different number of bytes", () => {
    const { readBack } = landed("hello");
    expect(judgeSave("hello", { bytes: 3, sha256: H2 }, readBack)).toEqual({ kind: "length-mismatch", sentBytes: 5, reportedBytes: 3 });
  });

  it("reports a content mismatch when the file read back differs, even if the size matches", () => {
    const { written } = landed("hello");
    expect(judgeSave("hello", written, { content: "hellp", sha256: H2 })).toEqual({ kind: "content-mismatch" });
  });

  it("does not treat a changed line ending as the same content", () => {
    const { written } = landed("a\r\nb");
    expect(judgeSave("a\r\nb", written, { content: "a\nb", sha256: H2 }).kind).not.toBe("verified");
  });

  it("reports a hash mismatch when the write and the read-back disagree about the file's hash", () => {
    const { written } = landed("hello");
    expect(judgeSave("hello", written, { content: "hello", sha256: H3 })).toEqual({ kind: "hash-mismatch" });
  });

  it("refuses to verify when the read-back carries no usable hash", () => {
    const { written } = landed("hello");
    expect(judgeSave("hello", written, { content: "hello", sha256: "" }).kind).toBe("hash-mismatch");
  });

  it("treats the hash case-insensitively and returns it lowercase", () => {
    const { written } = landed("x", "AB".repeat(32));
    expect(judgeSave("x", written, { content: "x", sha256: "ab".repeat(32) })).toEqual({ kind: "verified", bytes: 1, sha256: "ab".repeat(32) });
  });

  it("verifies an empty file", () => {
    const { written, readBack } = landed("");
    expect(judgeSave("", written, readBack)).toEqual({ kind: "verified", bytes: 0, sha256: H2 });
  });
});

describe("after a save", () => {
  it("marks the file clean and stores the verified hash when nothing was typed meanwhile", () => {
    const [f] = withSaved([file("a.py", "old", "new", H1)], "a.py", "new", H2);
    expect(isDirty(f)).toBe(false);
    expect(f.baseSha256).toBe(H2);
  });

  it("keeps the file dirty if the user kept typing while the save was in flight, but still moves the hash", () => {
    const typedMeanwhile = withBuffer([file("a.py", "old", "new", H1)], "a.py", "new plus more");
    const [f] = withSaved(typedMeanwhile, "a.py", "new", H2);
    expect(f.saved).toBe("new");
    expect(f.buffer).toBe("new plus more");
    expect(f.baseSha256).toBe(H2);
    expect(isDirty(f)).toBe(true);
  });

  it("an unverified save keeps the text, keeps the SUBMITTED base hash, and stays unsaved", () => {
    const [f] = withUnverified([file("a.py", "old", "typed", H1)], "a.py");
    expect(isDirty(f)).toBe(true);
    expect(f.buffer).toBe("typed");
    expect(f.saved).toBe("old");
    expect(f.baseSha256).toBe(H1); // never replaced by the hash of the unexpected disk content
    expect(f.unverified).toBe(true);
  });

  it("an unverified file is unsaved even when its text equals the saved copy (it cannot look clean)", () => {
    const [f] = withUnverified([file("a.py", "same", "same", H1)], "a.py");
    expect(f.buffer).toBe(f.saved);
    expect(isDirty(f)).toBe(true);
    expect(hasUnsavedChanges([f])).toBe(true);
  });

  it("typing keeps a file unverified", () => {
    const withTyping = withBuffer(withUnverified([file("a.py", "old", "typed", H1)], "a.py"), "a.py", "typed more");
    expect(withTyping[0].unverified).toBe(true);
    expect(withTyping[0].baseSha256).toBe(H1);
  });

  it("only a verified save, or a reload, clears the unverified mark", () => {
    const flagged = withUnverified([file("a.py", "old", "typed", H1)], "a.py");
    const saved = withSaved(flagged, "a.py", "typed", H2);
    expect(saved[0].unverified).toBe(false);
    expect(isDirty(saved[0])).toBe(false);
    const reloaded = withReloaded(flagged, "a.py", "disk", H3);
    expect(reloaded[0].unverified).toBe(false);
    expect(isDirty(reloaded[0])).toBe(false);
  });

  it("marking one file unverified leaves the others untouched", () => {
    const before = [file("a.py", "1", "1", H1), file("b.py", "2", "2", H1)];
    const after = withUnverified(before, "a.py");
    expect(after[1]).toBe(before[1]);
  });

  it("only changes the file that was saved", () => {
    const before = [file("a.py", "1", "1", H1), file("b.py", "2", "2b", H1)];
    const after = withSaved(before, "a.py", "1", H2);
    expect(after[1]).toBe(before[1]);
  });
});

describe("reloading from disk", () => {
  it("replaces the text and the saved copy with the disk content and takes the disk hash", () => {
    const [f] = withReloaded([file("a.py", "old", "my edits", H1)], "a.py", "disk version", H3);
    expect(f).toMatchObject({ saved: "disk version", buffer: "disk version", baseSha256: H3 });
    expect(isDirty(f)).toBe(false);
  });

  it("only changes the reloaded file", () => {
    const before = [file("a.py", "1", "1x", H1), file("b.py", "2", "2x", H1)];
    const after = withReloaded(before, "a.py", "fresh", H3);
    expect(after[1]).toBe(before[1]);
  });
});

describe("closing tabs", () => {
  const open = [file("a.py"), file("b.py"), file("c.py")];

  it("keeps the active file when a different tab is closed", () => {
    expect(nextActiveAfterClose(open, "a.py", "b.py")).toBe("b.py");
  });

  it("moves to the neighbour when the active tab is closed", () => {
    expect(nextActiveAfterClose(open, "b.py", "b.py")).toBe("c.py");
    expect(nextActiveAfterClose(open, "c.py", "c.py")).toBe("b.py");
    expect(nextActiveAfterClose(open, "a.py", "a.py")).toBe("b.py");
  });

  it("has no active file once the last tab is closed", () => {
    expect(nextActiveAfterClose([file("a.py")], "a.py", "a.py")).toBeNull();
  });
});

describe("language mapping", () => {
  it("maps backend names to Monaco ids and falls back to plain text", () => {
    expect(monacoLanguage("python")).toBe("python");
    expect(monacoLanguage("typescript")).toBe("typescript");
    expect(monacoLanguage("toml")).toBe("plaintext");
    expect(monacoLanguage("something-new")).toBe("plaintext");
  });

  it("covers every language the backend can report (guards against the two lists drifting apart)", () => {
    const source = readFileSync(new URL("../../backend/app/api/files.py", import.meta.url), "utf-8");
    const mapping = source.slice(source.indexOf("mapping = {"), source.indexOf("return mapping.get"));
    const reported = Array.from(new Set(mapping.match(/:\s*"[a-z]+"/g) ?? [])).map((m) => m.replace(/[^a-z]/g, ""));
    expect(reported.length).toBeGreaterThan(5);
    // The one language Monaco has no grammar for is allowed to fall back to plain text; every other
    // language the backend reports must keep its own highlighting, so a new backend language that is
    // missing from the Monaco map fails here instead of silently losing syntax colours.
    const noGrammar = ["toml"];
    reported.forEach((lang) => {
      expect(monacoLanguage(lang)).toBe(noGrammar.includes(lang) ? "plaintext" : lang);
    });
    expect(reported).toContain("python");
  });
});

// ---------------------------------------------------------------------------------------------------------
// Per-file save state: a conflict on one file must survive anything that happens to another file.
// ---------------------------------------------------------------------------------------------------------

const CONFLICT_A: SaveState = { status: "conflict", path: "a.py", message: "changed on disk" };
const VERIFIED_B: SaveState = { status: "verified", path: "b.py", bytes: 5 };
const SAVING_B: SaveState = { status: "saving", path: "b.py" };
const ERROR_B: SaveState = { status: "error", path: "b.py", message: "boom" };
const WARNING_B: SaveState = { status: "warning", path: "b.py", message: "not verified" };

describe("normalizePath", () => {
  it("leaves a normal project-relative path alone", () => {
    expect(normalizePath("app/api/routes.py")).toBe("app/api/routes.py");
  });

  it.each([
    ["app\\api\\routes.py", "app/api/routes.py"],
    ["./app/api/routes.py", "app/api/routes.py"],
    [".//app/api/routes.py", "app/api/routes.py"],
    ["/app/api/routes.py", "app/api/routes.py"],
    ["app//api///routes.py", "app/api/routes.py"],
    ["././app/x.py", "app/x.py"],
  ])("normalizes %j to %j", (raw, expected) => {
    expect(normalizePath(raw)).toBe(expected);
  });

  it("keeps case, so differently-cased names stay different files", () => {
    expect(normalizePath("App/Main.py")).not.toBe(normalizePath("app/main.py"));
  });

  it("is idempotent", () => {
    for (const p of ["a/b.py", "./a//b.py", "\\a\\b.py"]) expect(normalizePath(normalizePath(p))).toBe(normalizePath(p));
  });
});

describe("saveStateFor", () => {
  it("is idle for a file with no entry, for null, for undefined and for an empty path", () => {
    expect(saveStateFor({}, "a.py")).toEqual({ status: "idle" });
    expect(saveStateFor({ "a.py": CONFLICT_A }, null)).toEqual({ status: "idle" });
    expect(saveStateFor({ "a.py": CONFLICT_A }, undefined)).toEqual({ status: "idle" });
    expect(saveStateFor({ "a.py": CONFLICT_A }, "")).toEqual({ status: "idle" });
  });

  it("returns the file's own state, found through any spelling of its path", () => {
    const states: SaveStates = { "app/a.py": CONFLICT_A };
    expect(saveStateFor(states, "app/a.py")).toBe(CONFLICT_A);
    expect(saveStateFor(states, "./app/a.py")).toBe(CONFLICT_A);
    expect(saveStateFor(states, "app\\a.py")).toBe(CONFLICT_A);
  });

  it("never returns another file's state", () => {
    expect(saveStateFor({ "a.py": CONFLICT_A }, "b.py")).toEqual({ status: "idle" });
  });
});

describe("withSaveState", () => {
  it("sets one file's state and leaves every other file's state untouched", () => {
    const before: SaveStates = { "a.py": CONFLICT_A };
    const after = withSaveState(before, "b.py", VERIFIED_B);
    expect(after["a.py"]).toBe(CONFLICT_A);
    expect(after["b.py"]).toBe(VERIFIED_B);
  });

  it("replaces only the same file's previous state", () => {
    const after = withSaveState({ "a.py": CONFLICT_A, "b.py": SAVING_B }, "b.py", VERIFIED_B);
    expect(after["a.py"]).toBe(CONFLICT_A);
    expect(after["b.py"]).toBe(VERIFIED_B);
  });

  it("setting idle removes that file's entry (and only that one)", () => {
    const after = withSaveState({ "a.py": CONFLICT_A, "b.py": VERIFIED_B }, "b.py", { status: "idle" });
    expect(Object.keys(after)).toEqual(["a.py"]);
  });

  it("never mutates the map it was given", () => {
    const before: SaveStates = Object.freeze({ "a.py": CONFLICT_A });
    expect(() => withSaveState(before, "b.py", VERIFIED_B)).not.toThrow();
    expect(Object.keys(before)).toEqual(["a.py"]);
  });

  it("two spellings of one path share a single entry (a conflict can never hide under a second key)", () => {
    const after = withSaveState(withSaveState({}, "app/a.py", CONFLICT_A), ".\\app\\a.py", ERROR_B);
    expect(Object.keys(after)).toEqual(["app/a.py"]);
    expect(after["app/a.py"]).toBe(ERROR_B);
  });
});

describe("a conflict on A survives everything that happens to B", () => {
  const withConflictOnA = (): SaveStates => withSaveState({}, "a.py", CONFLICT_A);

  it("B starts saving, then verified", () => {
    let s = withConflictOnA();
    s = withSaveState(s, "b.py", SAVING_B);
    expect(s["a.py"]).toBe(CONFLICT_A);
    s = withSaveState(s, "b.py", VERIFIED_B);
    expect(s["a.py"]).toBe(CONFLICT_A);
  });

  it("B fails with an error or a warning", () => {
    for (const result of [ERROR_B, WARNING_B]) {
      expect(withSaveState(withConflictOnA(), "b.py", result)["a.py"]).toBe(CONFLICT_A);
    }
  });

  it("B is reloaded or resolved (its own state returns to idle)", () => {
    const s = withSaveState(withSaveState(withConflictOnA(), "b.py", CONFLICT_A_ON_B()), "b.py", { status: "idle" });
    expect(s["a.py"]).toBe(CONFLICT_A);
    expect(saveStateFor(s, "b.py")).toEqual({ status: "idle" });
  });

  it("the user types in B", () => {
    const s = afterEdit(withSaveState(withConflictOnA(), "b.py", VERIFIED_B), "b.py");
    expect(s["a.py"]).toBe(CONFLICT_A);
    expect(saveStateFor(s, "b.py")).toEqual({ status: "idle" });
  });

  it("B's tab is closed", () => {
    const s = withoutSaveState(withSaveState(withConflictOnA(), "b.py", VERIFIED_B), "b.py");
    expect(s["a.py"]).toBe(CONFLICT_A);
    expect(Object.keys(s)).toEqual(["a.py"]);
  });

  it("A and B can both be in conflict, and resolving one leaves the other", () => {
    let s = withSaveState(withConflictOnA(), "b.py", CONFLICT_A_ON_B());
    expect(conflictPaths(s).sort()).toEqual(["a.py", "b.py"]);
    s = withoutSaveState(s, "b.py");
    expect(conflictPaths(s)).toEqual(["a.py"]);
  });
});

function CONFLICT_A_ON_B(): SaveState {
  return { status: "conflict", path: "b.py", message: "changed on disk" };
}

describe("afterEdit", () => {
  it("drops that file's old result (a verified notice, a warning, an error)", () => {
    for (const result of [VERIFIED_B, WARNING_B, ERROR_B]) {
      expect(saveStateFor(afterEdit({ "b.py": result }, "b.py"), "b.py")).toEqual({ status: "idle" });
    }
  });

  it("never drops an unresolved conflict, even if the user keeps typing", () => {
    const states: SaveStates = { "a.py": CONFLICT_A };
    expect(afterEdit(states, "a.py")).toBe(states);
    expect(saveStateFor(afterEdit(afterEdit(states, "a.py"), "a.py"), "a.py")).toBe(CONFLICT_A);
  });

  it("never drops a save that is in flight", () => {
    const states: SaveStates = { "b.py": SAVING_B };
    expect(afterEdit(states, "b.py")).toBe(states);
  });

  it("does nothing to a file that has no state, and returns the same map", () => {
    const states: SaveStates = { "a.py": CONFLICT_A };
    expect(afterEdit(states, "b.py")).toBe(states);
  });

  it("only affects the edited file", () => {
    const after = afterEdit({ "a.py": CONFLICT_A, "b.py": VERIFIED_B, "c.py": WARNING_B }, "b.py");
    expect(after["a.py"]).toBe(CONFLICT_A);
    expect(after["c.py"]).toBe(WARNING_B);
    expect(after["b.py"]).toBeUndefined();
  });
});

describe("withoutSaveState / conflictPaths / anySaving", () => {
  it("removes only the named file's entry", () => {
    const after = withoutSaveState({ "a.py": CONFLICT_A, "b.py": VERIFIED_B }, "b.py");
    expect(after).toEqual({ "a.py": CONFLICT_A });
  });

  it("removing a file that has no entry is harmless", () => {
    expect(withoutSaveState({ "a.py": CONFLICT_A }, "zzz.py")).toEqual({ "a.py": CONFLICT_A });
  });

  it("lists exactly the files in conflict (not warnings, errors or saves)", () => {
    const states: SaveStates = { "a.py": CONFLICT_A, "b.py": ERROR_B, "c.py": WARNING_B, "d.py": SAVING_B, "e.py": VERIFIED_B };
    expect(conflictPaths(states)).toEqual(["a.py"]);
    expect(conflictPaths({})).toEqual([]);
  });

  it("reports a save in flight on ANY file (the basis of the global one-request-at-a-time guard)", () => {
    expect(anySaving({})).toBe(false);
    expect(anySaving({ "a.py": CONFLICT_A, "b.py": VERIFIED_B })).toBe(false);
    expect(anySaving({ "a.py": CONFLICT_A, "b.py": SAVING_B })).toBe(true);
  });
});

describe("a project switch starts from nothing", () => {
  it("an empty map has no conflicts and nothing in flight, whatever the previous project had", () => {
    const previousProject: SaveStates = { "app/main.py": CONFLICT_A, "b.py": SAVING_B };
    expect(conflictPaths(previousProject).length + Number(anySaving(previousProject))).toBeGreaterThan(0);
    const fresh: SaveStates = {};
    expect(conflictPaths(fresh)).toEqual([]);
    expect(anySaving(fresh)).toBe(false);
    expect(saveStateFor(fresh, "app/main.py")).toEqual({ status: "idle" });
  });
});

// ---------------------------------------------------------------------------------------------------------
// Monaco model lifecycle: which models are released when tabs close or the project changes.
// ---------------------------------------------------------------------------------------------------------

describe("modelKey / modelKeysFor", () => {
  it("is '<project>:<path>', exactly the key the editor is mounted with for a backend-reported path", () => {
    expect(modelKey("proj-1", "app/api/routes.py")).toBe("proj-1:app/api/routes.py");
  });

  it.each([
    ["app\\api\\routes.py", "proj-1:app/api/routes.py"],
    ["./app/api/routes.py", "proj-1:app/api/routes.py"],
    ["app//api///routes.py", "proj-1:app/api/routes.py"],
    ["/app/api/routes.py", "proj-1:app/api/routes.py"],
  ])("normalizes the path %j so one file can never have two keys", (raw, expected) => {
    expect(modelKey("proj-1", raw)).toBe(expected);
  });

  it("the same path in two projects gets two different keys (projects never share or dispose each other's models)", () => {
    expect(modelKey("proj-1", "a.py")).not.toBe(modelKey("proj-2", "a.py"));
  });

  it("different files get different keys; case is kept", () => {
    expect(modelKey("p", "a.py")).not.toBe(modelKey("p", "b.py"));
    expect(modelKey("p", "A.py")).not.toBe(modelKey("p", "a.py"));
  });

  it("modelKeysFor maps open files to keys in order, and is empty for no files", () => {
    const files = [file("b.py"), file("a/c.py")];
    expect(modelKeysFor("p", files)).toEqual(["p:b.py", "p:a/c.py"]);
    expect(modelKeysFor("p", [])).toEqual([]);
  });
});

describe("keysToDispose (which models to release)", () => {
  it("returns exactly the keys that are no longer open, in their previous order", () => {
    expect(keysToDispose(["p:a", "p:b", "p:c"], ["p:b"])).toEqual(["p:a", "p:c"]);
  });

  it("closing one tab releases only that tab", () => {
    expect(keysToDispose(["p:a", "p:b", "p:c"], ["p:a", "p:c"])).toEqual(["p:b"]);
  });

  it("returns nothing when nothing closed", () => {
    expect(keysToDispose(["p:a", "p:b"], ["p:a", "p:b"])).toEqual([]);
  });

  it("switching tabs (same files, any order) releases nothing", () => {
    expect(keysToDispose(["p:a", "p:b", "p:c"], ["p:c", "p:a", "p:b"])).toEqual([]);
  });

  it("opening a file releases nothing (new keys are ignored)", () => {
    expect(keysToDispose(["p:a"], ["p:a", "p:b"])).toEqual([]);
  });

  it("closing every tab releases every model", () => {
    expect(keysToDispose(["p:a", "p:b"], [])).toEqual(["p:a", "p:b"]);
  });

  it("nothing open before means nothing to release", () => {
    expect(keysToDispose([], ["p:a"])).toEqual([]);
    expect(keysToDispose([], [])).toEqual([]);
  });

  it("a project switch releases ALL of the previous project's models, and none of the new project's", () => {
    expect(keysToDispose(["old:a", "old:b"], ["new:a"])).toEqual(["old:a", "old:b"]);
    expect(keysToDispose(["old:a", "old:b"], [])).toEqual(["old:a", "old:b"]);
  });

  it("lists each key once even if the previous list repeats it", () => {
    expect(keysToDispose(["p:a", "p:a", "p:b"], [])).toEqual(["p:a", "p:b"]);
  });

  it("is idempotent under repeated effects (React Strict Mode): the second run, on the same files, finds nothing", () => {
    // what WorkspaceView's effect does: compare with the keys of the previous run, then remember the new keys
    let remembered = ["p:a", "p:b"];
    const run = (current: string[]) => {
      const gone = keysToDispose(remembered, current);
      remembered = current;
      return gone;
    };
    expect(run(["p:b"])).toEqual(["p:a"]);     // the tab for a was closed: a is released once
    expect(run(["p:b"])).toEqual([]);          // the effect runs again with the same files: nothing more to release
    expect(run(["p:b"])).toEqual([]);
  });

  it("never mutates its inputs", () => {
    const previous = Object.freeze(["p:a", "p:b"]);
    const current = Object.freeze(["p:b"]);
    expect(() => keysToDispose(previous, current)).not.toThrow();
    expect(previous).toEqual(["p:a", "p:b"]);
  });
});

/** A tiny fake of the Monaco API: models by key, and the models currently attached to editors. */
function fakeMonaco(spec: Record<string, { disposed?: boolean; throws?: boolean }>, attached: string[] = []) {
  const models = new Map<string, { key: string; disposed: boolean; isDisposed: () => boolean; dispose: ReturnType<typeof vi.fn> }>();
  for (const [key, opts] of Object.entries(spec)) {
    const model = {
      key,
      disposed: opts.disposed ?? false,
      isDisposed: () => model.disposed,
      dispose: vi.fn(() => {
        if (opts.throws) throw new Error("dispose failed");
        model.disposed = true;
      }),
    };
    models.set(key, model);
  }
  const parse = vi.fn((value: string) => ({ key: value }));
  const getModel = vi.fn((uri: { key: string }) => models.get(uri.key) ?? null);
  const api: MonacoModelApi = {
    Uri: { parse },
    editor: {
      getModel: getModel as unknown as MonacoModelApi["editor"]["getModel"],
      getEditors: () => attached.map((key) => ({ getModel: () => models.get(key) ?? null })),
    },
  };
  return { api, models, parse, getModel };
}

describe("disposeModels (never dispose an attached model)", () => {
  it("disposes the models of the keys that are no longer open", () => {
    const { api, models } = fakeMonaco({ "p:a": {}, "p:b": {} }, []);
    const report = disposeModels(api, ["p:a", "p:b"], []);
    expect(report).toEqual({ disposed: ["p:a", "p:b"], deferred: [], skipped: [] });
    expect(models.get("p:a")!.dispose).toHaveBeenCalledTimes(1);
    expect(models.get("p:b")!.dispose).toHaveBeenCalledTimes(1);
  });

  it("NEVER disposes a model that is still attached to an editor: it is deferred instead", () => {
    const { api, models } = fakeMonaco({ "p:a": {}, "p:b": {} }, ["p:a"]);
    const report = disposeModels(api, ["p:a", "p:b"], []);
    expect(report.deferred).toEqual(["p:a"]);
    expect(report.disposed).toEqual(["p:b"]);
    expect(models.get("p:a")!.dispose).not.toHaveBeenCalled();
    expect(models.get("p:a")!.disposed).toBe(false);
  });

  it("a model attached to a DIFFERENT editor instance still counts as attached", () => {
    const { api, models } = fakeMonaco({ "p:a": {}, "p:b": {} }, ["p:b", "p:a"]);
    disposeModels(api, ["p:a"], []);
    expect(models.get("p:a")!.dispose).not.toHaveBeenCalled();
  });

  it("an editor showing some other model does not protect this one", () => {
    const { api, models } = fakeMonaco({ "p:a": {}, "p:b": {} }, ["p:b"]);
    const report = disposeModels(api, ["p:a"], []);
    expect(report.disposed).toEqual(["p:a"]);
    expect(models.get("p:b")!.dispose).not.toHaveBeenCalled();
  });

  it("skips a key whose file was reopened in the meantime (its model is live again)", () => {
    const { api, models } = fakeMonaco({ "p:a": {}, "p:b": {} });
    const report = disposeModels(api, ["p:a", "p:b"], ["p:a"]);
    expect(report).toEqual({ disposed: ["p:b"], deferred: [], skipped: ["p:a"] });
    expect(models.get("p:a")!.dispose).not.toHaveBeenCalled();
  });

  it("skips keys with no model, and models that are already disposed", () => {
    const { api } = fakeMonaco({ "p:gone": { disposed: true } });
    const report = disposeModels(api, ["p:never-existed", "p:gone"], []);
    expect(report).toEqual({ disposed: [], deferred: [], skipped: ["p:never-existed", "p:gone"] });
  });

  it("is idempotent: a second call finds nothing left to dispose and disposes nothing twice", () => {
    const { api, models } = fakeMonaco({ "p:a": {} });
    disposeModels(api, ["p:a"], []);
    const second = disposeModels(api, ["p:a"], []);
    expect(second.disposed).toEqual([]);
    expect(models.get("p:a")!.dispose).toHaveBeenCalledTimes(1);
  });

  it("a model whose dispose throws does not stop the others and never throws out of the function", () => {
    const { api, models } = fakeMonaco({ "p:bad": { throws: true }, "p:ok": {} });
    let report!: ReturnType<typeof disposeModels>;
    expect(() => { report = disposeModels(api, ["p:bad", "p:ok"], []); }).not.toThrow();
    expect(report.disposed).toEqual(["p:ok"]);
    expect(report.skipped).toEqual(["p:bad"]);
    expect(models.get("p:ok")!.disposed).toBe(true);
  });

  it("a failing lookup is contained too", () => {
    const { api } = fakeMonaco({ "p:a": {} });
    (api.editor as { getModel: unknown }).getModel = () => { throw new Error("lookup failed"); };
    expect(() => disposeModels(api, ["p:a"], [])).not.toThrow();
    expect(disposeModels(api, ["p:a"], []).skipped).toEqual(["p:a"]);
  });

  it("looks each model up by parsing exactly the key it was given (the wrapper creates models with Uri.parse(key))", () => {
    const { api, parse } = fakeMonaco({ "proj:app/main.py": {} });
    disposeModels(api, ["proj:app/main.py"], []);
    expect(parse).toHaveBeenCalledWith("proj:app/main.py");
  });

  it("does nothing, and calls nothing, for an empty key list", () => {
    const { api, parse, getModel } = fakeMonaco({ "p:a": {} });
    expect(disposeModels(api, [], [])).toEqual({ disposed: [], deferred: [], skipped: [] });
    expect(parse).not.toHaveBeenCalled();
    expect(getModel).not.toHaveBeenCalled();
  });

  it("a deferred model can be disposed once it is detached (the retry path)", () => {
    const attached = ["p:a"];
    const { api, models } = fakeMonaco({ "p:a": {} }, attached);
    expect(disposeModels(api, ["p:a"], []).deferred).toEqual(["p:a"]);
    attached.length = 0;                                   // the editor has switched to another model
    expect(disposeModels(api, ["p:a"], []).disposed).toEqual(["p:a"]);
    expect(models.get("p:a")!.dispose).toHaveBeenCalledTimes(1);
  });
});

describe("the whole lifecycle with the pure pieces (close tabs, switch project, reopen)", () => {
  it("closing the active tab disposes only its model, after the editor has moved to the neighbour", () => {
    const { api, models } = fakeMonaco({ "p:a": {}, "p:b": {}, "p:c": {} }, ["p:a"]);   // editor now shows a (the neighbour)
    const gone = keysToDispose(["p:a", "p:b", "p:c"], ["p:a", "p:c"]);                    // b was closed
    expect(disposeModels(api, gone, ["p:a", "p:c"]).disposed).toEqual(["p:b"]);
    expect(models.get("p:a")!.disposed).toBe(false);
    expect(models.get("p:c")!.disposed).toBe(false);
  });

  it("a project switch disposes every old model except one the editor still shows, which is retried", () => {
    const attached = ["old:b"];
    const { api, models } = fakeMonaco({ "old:a": {}, "old:b": {}, "new:a": {} }, attached);
    const gone = keysToDispose(["old:a", "old:b"], ["new:a"]);
    const first = disposeModels(api, gone, ["new:a"]);
    expect(first.disposed).toEqual(["old:a"]);
    expect(first.deferred).toEqual(["old:b"]);
    attached.length = 0;
    expect(disposeModels(api, first.deferred, ["new:a"]).disposed).toEqual(["old:b"]);
    expect(models.get("new:a")!.disposed).toBe(false);
  });

  it("reopening a closed file after its model was disposed finds no model, so the editor creates a fresh one", () => {
    const { api } = fakeMonaco({ "p:a": {} });
    disposeModels(api, ["p:a"], []);
    const model = api.editor.getModel(api.Uri.parse("p:a") as never);
    expect(model === null || model.isDisposed()).toBe(true);
  });
});

// ---------------------------------------------------------------------------------------------------------
// Reload counter: the editor drops a file's undo history when it was reloaded from disk (see MonacoSurface).
// ---------------------------------------------------------------------------------------------------------

describe("reload counter (withReloaded / reloadCount)", () => {
  it("a file nobody reloaded has count 0", () => {
    expect(reloadCount(file("a.py"))).toBe(0);
  });

  it("each confirmed reload of a file adds exactly one", () => {
    const once = withReloaded([file("a.py", "old", "mine", H1)], "a.py", "disk 1", H2);
    expect(reloadCount(once[0])).toBe(1);
    const twice = withReloaded(once, "a.py", "disk 2", H3);
    expect(reloadCount(twice[0])).toBe(2);
  });

  it("only the reloaded file's counter moves; other files are untouched", () => {
    const files = [file("a.py", "x", "x", H1), file("b.py", "y", "y", H1)];
    const after = withReloaded(files, "a.py", "disk", H2);
    expect(reloadCount(after[0])).toBe(1);
    expect(after[1]).toBe(files[1]);
    expect(reloadCount(after[1])).toBe(0);
  });

  it("still sets exactly what a reload always set: buffer = saved = disk text, the new base hash, not unverified", () => {
    const [f] = withReloaded([{ ...file("a.py", "old", "my edits", H1), unverified: true }], "a.py", "disk text", H2);
    expect(f).toMatchObject({ saved: "disk text", buffer: "disk text", baseSha256: H2, unverified: false });
    expect(isDirty(f)).toBe(false);
  });

  it("saving, typing, marking unverified and marking saved never change the counter", () => {
    const start = withReloaded([file("a.py", "old", "old", H1)], "a.py", "disk", H2);
    for (const next of [
      withBuffer(start, "a.py", "typed"),
      withSaved(start, "a.py", "disk", H3),
      withUnverified(start, "a.py"),
    ]) expect(reloadCount(next[0])).toBe(1);
  });

  it("does not mutate the files it is given", () => {
    const files = [file("a.py", "old", "mine", H1)];
    const snapshot = JSON.stringify(files);
    withReloaded(files, "a.py", "disk", H2);
    expect(JSON.stringify(files)).toBe(snapshot);
  });
});

describe("shouldResetHistory (when the editor drops a model's undo history)", () => {
  it("yes: the file was reloaded since the editor last showed it", () => {
    expect(shouldResetHistory(0, 1)).toBe(true);
    expect(shouldResetHistory(1, 2)).toBe(true);
    expect(shouldResetHistory(0, 3)).toBe(true); // several reloads while another tab was active
  });

  it("no: the count did not change (tab switch, re-render, repeated effect)", () => {
    expect(shouldResetHistory(0, 0)).toBe(false);
    expect(shouldResetHistory(2, 2)).toBe(false);
  });

  it("no: the editor never showed this file, so its model is brand new and has no history", () => {
    expect(shouldResetHistory(undefined, 0)).toBe(false);
    expect(shouldResetHistory(undefined, 5)).toBe(false);
  });

  it("no: the count went DOWN (file closed and reopened gives a fresh file with count 0)", () => {
    expect(shouldResetHistory(2, 0)).toBe(false);
    expect(shouldResetHistory(3, 1)).toBe(false);
  });

  it("is idempotent under repeated effects (React Strict Mode): the second run on the same count does nothing", () => {
    const seen = new Map<string, number>();
    const run = (key: string, count: number) => {
      const reset = shouldResetHistory(seen.get(key), count);
      seen.set(key, count);
      return reset;
    };
    expect(run("p:a", 0)).toBe(false); // first time the editor shows the file
    expect(run("p:a", 1)).toBe(true);  // reloaded
    expect(run("p:a", 1)).toBe(false); // the same effect runs again
    expect(run("p:b", 1)).toBe(false); // another file is not affected by a's count
  });
});
