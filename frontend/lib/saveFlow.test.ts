// The editor's save / reload / overwrite flows (lib/saveFlow.ts) against an in-memory fake of the backend
// that enforces the same rules as the real Step 1 endpoint: PUT needs the hash the file had when loaded,
// answers 409 if the file changed, 404 if it is gone, and never creates a file; GET returns the hash.
// The fake also records every call, so tests can assert what was (and was not) sent.
import { createHash } from "node:crypto";
import { beforeEach, describe, expect, it } from "vitest";
import type { ApiResult, FileContentData, FileSaveData } from "@/lib/api";
import { byteLength, isDirty, isSha256, withBuffer, type OpenFile, type SaveState } from "@/lib/editorSession";
import {
  NO_HASH_MESSAGE,
  overwriteConfirmText,
  overwriteWithMine,
  reloadConfirmText,
  reloadFromDisk,
  saveFile,
  type FileApi,
  type FlowContext,
  type FlowResult,
} from "@/lib/saveFlow";

const sha = (text: string) => createHash("sha256").update(Buffer.from(text, "utf-8")).digest("hex");
const PATH = "app/main.py";

/** In-memory stand-in for the backend's file endpoints. */
class FakeBackend {
  disk = new Map<string, string>();
  calls: string[] = [];
  /** Runs at the start of every PUT, before the server looks at it: simulates a writer or typing mid-request. */
  duringSave?: () => void;
  /** Runs at the start of every GET. */
  duringFetch?: () => void;
  /** If set, the next PUT gets exactly this response without touching the disk. */
  scriptedSave?: ApiResult<FileSaveData>;
  /** If set, every GET after the first successful PUT fails with this. */
  failReadBackWith?: ApiResult<FileContentData>;
  /** If set, the next GET reports this hash instead of the real one (a server that contradicts itself). */
  nextFetchSha256?: string;
  private saved = false;

  constructor(initial: Record<string, string>) {
    for (const [p, c] of Object.entries(initial)) this.disk.set(p, c);
  }

  api: FileApi = {
    fetchFile: async (_id, path) => {
      this.calls.push(`fetch:${path}`);
      this.duringFetch?.();
      if (this.saved && this.failReadBackWith) return this.failReadBackWith;
      const content = this.disk.get(path);
      if (content === undefined) return { ok: false, status: 404, message: `File '${path}' not found.` };
      const reported = this.nextFetchSha256 ?? sha(content);
      this.nextFetchSha256 = undefined;
      return {
        ok: true,
        status: 200,
        data: { path, file_name: path.split("/").pop()!, content, line_count: 1, language: "python", sha256: reported },
      };
    },
    saveFileContent: async (_id, path, content, base) => {
      this.calls.push(`save:${path}:${base}`);
      this.duringSave?.();
      if (this.scriptedSave) {
        const r = this.scriptedSave;
        this.scriptedSave = undefined;
        return r;
      }
      const current = this.disk.get(path);
      if (current === undefined) {
        return { ok: false, status: 404, message: `File '${path}' does not exist. This endpoint only updates existing files; it never creates files or folders.` };
      }
      if (base !== sha(current)) {
        return { ok: false, status: 409, message: "The file changed on disk since it was loaded, so it was not overwritten. Nothing was written." };
      }
      this.disk.set(path, content);
      this.saved = true;
      return { ok: true, status: 200, data: { status: "saved", path, bytes_written: byteLength(content), sha256: sha(content) } };
    },
  };
}

/** The editor side: the open files, the save state, and a scripted confirm dialog. */
class Editor {
  files: OpenFile[] = [];
  save: SaveState = { status: "idle" };
  confirms: boolean[] = [];
  confirmMessages: string[] = [];

  constructor(public backend: FakeBackend) {}

  /** Open a file the way WorkspaceView does: keep the hash the server reported. */
  async open(path: string, overrides: Partial<OpenFile> = {}) {
    const r = await this.backend.api.fetchFile("p", path);
    const d = r.data!;
    this.files.push({ path, language: d.language, saved: d.content, buffer: d.content, baseSha256: isSha256(d.sha256) ? d.sha256 : "", ...overrides });
    this.backend.calls.length = 0; // only count what the flows do
  }

  type(path: string, text: string) {
    this.files = withBuffer(this.files, path, text);
  }

  get ctx(): FlowContext {
    return {
      api: this.backend.api,
      projectId: "p",
      getFiles: () => this.files,
      confirm: (message) => {
        this.confirmMessages.push(message);
        return this.confirms.length ? this.confirms.shift()! : false;
      },
    };
  }

  apply(result: FlowResult) {
    this.files = result.update(this.files);
    if (result.save) this.save = result.save;
  }

  file(path = PATH) {
    return this.files.find((f) => f.path === path)!;
  }
}

let backend: FakeBackend;
let editor: Editor;
const ORIGINAL = "print('v1')\n";

beforeEach(async () => {
  backend = new FakeBackend({ [PATH]: ORIGINAL, "other.py": "other\n" });
  editor = new Editor(backend);
  await editor.open(PATH);
});

describe("successful save", () => {
  it("sends the hash the file was loaded with, writes the text, and reports a verified save", async () => {
    editor.type(PATH, "print('v2')\n");
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(backend.calls[0]).toBe(`save:${PATH}:${sha(ORIGINAL)}`);
    expect(backend.disk.get(PATH)).toBe("print('v2')\n");
    expect(editor.save).toEqual({ status: "verified", path: PATH, bytes: byteLength("print('v2')\n") });
  });

  it("stores the verified hash from the server and marks the file clean", async () => {
    editor.type(PATH, "print('v2')\n");
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(editor.file().baseSha256).toBe(sha("print('v2')\n"));
    expect(editor.file().saved).toBe("print('v2')\n");
    expect(isDirty(editor.file())).toBe(false);
  });

  it("chains: the next save is based on the hash from the previous save, with no reload in between", async () => {
    editor.type(PATH, "v2\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    editor.type(PATH, "v3\n");
    editor.apply(await saveFile(editor.ctx, PATH));

    const saves = backend.calls.filter((c) => c.startsWith("save:"));
    expect(saves).toEqual([`save:${PATH}:${sha(ORIGINAL)}`, `save:${PATH}:${sha("v2\n")}`]);
    expect(backend.disk.get(PATH)).toBe("v3\n");
    expect(editor.save.status).toBe("verified");
  });

  it("keeps text typed while the request was in flight, and keeps the file marked unsaved", async () => {
    editor.type(PATH, "v2\n");
    backend.duringSave = () => editor.type(PATH, "v2\nplus what I typed meanwhile");
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(backend.disk.get(PATH)).toBe("v2\n");
    expect(editor.file().buffer).toBe("v2\nplus what I typed meanwhile");
    expect(editor.file().saved).toBe("v2\n");
    expect(editor.file().baseSha256).toBe(sha("v2\n"));
    expect(isDirty(editor.file())).toBe(true);
  });

  it("sends nothing when there is nothing to save", async () => {
    const result = await saveFile(editor.ctx, PATH);
    expect(backend.calls).toEqual([]);
    expect(result.save).toBeUndefined();
  });

  it("sends nothing for a file that is not open", async () => {
    await saveFile(editor.ctx, "nope.py");
    expect(backend.calls).toEqual([]);
  });
});

describe("stale hash (the file changed on disk after it was loaded)", () => {
  beforeEach(() => {
    editor.type(PATH, "my edit\n");
    backend.disk.set(PATH, "someone else's edit\n"); // another editor, a git checkout, a formatter...
  });

  it("reports a conflict, not a plain error", async () => {
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("conflict");
    expect((editor.save as { message: string }).message).toContain("changed on disk");
  });

  it("keeps the user's text and keeps the file marked unsaved", async () => {
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.file().buffer).toBe("my edit\n");
    expect(isDirty(editor.file())).toBe(true);
  });

  it("does not move the stored hash or the saved copy (they still describe what was loaded)", async () => {
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.file().baseSha256).toBe(sha(ORIGINAL));
    expect(editor.file().saved).toBe(ORIGINAL);
  });

  it("leaves the other writer's content on disk and makes no read-back request", async () => {
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(backend.disk.get(PATH)).toBe("someone else's edit\n");
    expect(backend.calls).toEqual([`save:${PATH}:${sha(ORIGINAL)}`]);
  });

  it("keeps conflicting on every retry until the user resolves it (no silent overwrite)", async () => {
    editor.apply(await saveFile(editor.ctx, PATH));
    editor.type(PATH, "my edit, continued\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("conflict");
    expect(backend.disk.get(PATH)).toBe("someone else's edit\n");
    expect(editor.file().buffer).toBe("my edit, continued\n");
  });
});

describe("missing or invalid hash", () => {
  it("refuses to save a file that was loaded without a hash and sends NOTHING", async () => {
    await editor.open("other.py", { baseSha256: "" });
    editor.type("other.py", "changed\n");
    editor.apply(await saveFile(editor.ctx, "other.py"));

    expect(backend.calls).toEqual([]);
    expect(editor.save).toEqual({ status: "error", path: "other.py", message: NO_HASH_MESSAGE });
    expect(editor.file("other.py").buffer).toBe("changed\n");
    expect(isDirty(editor.file("other.py"))).toBe(true);
    expect(backend.disk.get("other.py")).toBe("other\n");
  });

  it.each(["xyz", "a".repeat(63), "g".repeat(64)])("treats the stored value %j as no hash and sends nothing", async (bad) => {
    editor.type(PATH, "changed\n");
    editor.files = editor.files.map((f) => ({ ...f, baseSha256: bad }));
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(backend.calls).toEqual([]);
    expect(editor.save.status).toBe("error");
  });

  it("also refuses a forced save / overwrite base that is not a hash", async () => {
    editor.type(PATH, "changed\n");
    editor.apply(await saveFile(editor.ctx, PATH, { baseSha256: "", force: true }));
    expect(backend.calls).toEqual([]);
    expect(editor.save.status).toBe("error");
  });

  it("shows the server's message and keeps the text when the server itself answers 428", async () => {
    editor.type(PATH, "my edit\n");
    backend.scriptedSave = { ok: false, status: 428, message: "base_sha256 is required: send the sha256 of the content you loaded. Nothing was written." };
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(editor.save).toMatchObject({ status: "error", path: PATH });
    expect((editor.save as { message: string }).message).toContain("base_sha256 is required");
    expect(editor.file().buffer).toBe("my edit\n");
    expect(isDirty(editor.file())).toBe(true);
    expect(backend.disk.get(PATH)).toBe(ORIGINAL);
  });
});

describe("other save errors never lose the text", () => {
  const failures: Array<[string, ApiResult<FileSaveData>]> = [
    ["404 file deleted", { ok: false, status: 404, message: "File 'app/main.py' does not exist. This endpoint only updates existing files; it never creates files or folders." }],
    ["413 too large", { ok: false, status: 413, message: "Content is 11 bytes; the limit is 10 bytes." }],
    ["400 rejected path", { ok: false, status: 400, message: "Illegal file path." }],
    ["500 server error", { ok: false, status: 500, message: "Failed to write file." }],
    ["backend unreachable", { ok: false, status: 0, message: "The backend could not be reached" }],
  ];

  it.each(failures)("%s: error shown, text kept, still unsaved, hash unchanged", async (_name, response) => {
    editor.type(PATH, "precious unsaved text\n");
    backend.scriptedSave = response;
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(editor.save).toMatchObject({ status: "error", path: PATH });
    expect((editor.save as { message: string }).message).toBe(response.message);
    expect(editor.file().buffer).toBe("precious unsaved text\n");
    expect(isDirty(editor.file())).toBe(true);
    expect(editor.file().baseSha256).toBe(sha(ORIGINAL));
  });

  it("a file deleted after loading gives a 404 error (not a conflict) and nothing is recreated", async () => {
    editor.type(PATH, "my edit\n");
    backend.disk.delete(PATH);
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("error");
    expect(backend.disk.has(PATH)).toBe(false);
    expect(editor.file().buffer).toBe("my edit\n");
  });
});

describe("a save that cannot be verified", () => {
  it("warns (not 'saved') when the read-back fails, but takes the hash the server reported for what it wrote", async () => {
    editor.type(PATH, "v2\n");
    backend.failReadBackWith = { ok: false, status: 500, message: "boom" };
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(editor.save.status).toBe("warning");
    expect((editor.save as { message: string }).message).toContain("Not verified");
    expect(editor.file().baseSha256).toBe(sha("v2\n"));
  });

  it("keeps the user's text, keeps the file unsaved, and does NOT adopt the unexpected disk hash when the read-back differs", async () => {
    editor.type(PATH, "v2\n");
    backend.duringFetch = () => backend.disk.set(PATH, "tampered after the write\n");
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(editor.save.status).toBe("warning");
    expect(editor.file().buffer).toBe("v2\n");
    expect(isDirty(editor.file())).toBe(true);
    // the base is still the hash that was submitted, NOT the hash of the unexpected disk content
    expect(editor.file().baseSha256).toBe(sha(ORIGINAL));
    expect(editor.file().baseSha256).not.toBe(sha("tampered after the write\n"));
  });
});

describe("after a save whose read-back differs from what was submitted (regression: no silent overwrite)", () => {
  const TAMPERED = "tampered after the write\n";

  /** Save "v2" while something else rewrites the file right after the write, so the read-back differs. */
  async function saveWithMismatch() {
    editor.type(PATH, "v2\n");
    backend.duringFetch = () => {
      backend.disk.set(PATH, TAMPERED);
      backend.duringFetch = undefined;
    };
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("warning"); // precondition: the mismatch was detected
    backend.calls.length = 0;
  }

  it("an ordinary Save afterwards does NOT overwrite the unexpected disk version: it ends in the normal conflict flow", async () => {
    await saveWithMismatch();
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(editor.save.status).toBe("conflict");
    expect(backend.disk.get(PATH)).toBe(TAMPERED); // the unexpected version survived
    expect(backend.calls).toEqual([`save:${PATH}:${sha(ORIGINAL)}`]); // sent on the ORIGINAL base, so the server refused
  });

  it("the user's text is still in the editor and the file is still unsaved after that second Save", async () => {
    await saveWithMismatch();
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.file().buffer).toBe("v2\n");
    expect(isDirty(editor.file())).toBe(true);
  });

  it("repeated ordinary Saves keep being refused (they never wear the protection down)", async () => {
    await saveWithMismatch();
    for (let i = 0; i < 3; i++) {
      editor.apply(await saveFile(editor.ctx, PATH));
      expect(editor.save.status).toBe("conflict");
      expect(backend.disk.get(PATH)).toBe(TAMPERED);
    }
  });

  it("the file counts as unsaved even if the user's text equals what was last saved (so it cannot look clean)", async () => {
    await saveWithMismatch();
    editor.type(PATH, ORIGINAL); // text back to the originally loaded content
    expect(editor.file().buffer).toBe(editor.file().saved);
    expect(isDirty(editor.file())).toBe(true);
    expect(editor.files.some(isDirty)).toBe(true);
  });

  it("typing more keeps the protection: the base stays the submitted one", async () => {
    await saveWithMismatch();
    editor.type(PATH, "v2\nand more\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("conflict");
    expect(editor.file().baseSha256).toBe(sha(ORIGINAL));
    expect(backend.disk.get(PATH)).toBe(TAMPERED);
  });

  it("explicit overwrite stays a deliberate action: nothing happens if the user declines", async () => {
    await saveWithMismatch();
    editor.apply(await saveFile(editor.ctx, PATH)); // conflict banner
    backend.calls.length = 0;
    editor.confirms = [false];
    const result = await overwriteWithMine(editor.ctx, PATH);
    editor.apply(result);

    expect(backend.calls).toEqual([]);
    expect(backend.disk.get(PATH)).toBe(TAMPERED);
    expect(editor.save.status).toBe("conflict");
    expect(editor.confirmMessages.at(-1)).toBe(overwriteConfirmText(PATH));
  });

  it("explicit overwrite, once the user confirms, fetches the latest hash and then writes the user's text", async () => {
    await saveWithMismatch();
    editor.apply(await saveFile(editor.ctx, PATH));
    backend.calls.length = 0;
    editor.confirms = [true];
    editor.apply(await overwriteWithMine(editor.ctx, PATH));

    expect(backend.calls[0]).toBe(`fetch:${PATH}`);
    expect(backend.calls[1]).toBe(`save:${PATH}:${sha(TAMPERED)}`);
    expect(backend.disk.get(PATH)).toBe("v2\n");
    expect(editor.save.status).toBe("verified");
    expect(isDirty(editor.file())).toBe(false);
    expect(editor.file().baseSha256).toBe(sha("v2\n"));
  });

  it("reloading from disk (confirmed) resolves it: the file becomes clean and saves work normally again", async () => {
    await saveWithMismatch();
    editor.confirms = [true];
    editor.apply(await reloadFromDisk(editor.ctx, PATH));
    expect(editor.file().buffer).toBe(TAMPERED);
    expect(isDirty(editor.file())).toBe(false);

    editor.type(PATH, TAMPERED + "next\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("verified");
    expect(backend.disk.get(PATH)).toBe(TAMPERED + "next\n");
  });

  it("a read-back whose HASH contradicts the write is handled the same way (content equal, hash different)", async () => {
    editor.type(PATH, "v2\n");
    backend.nextFetchSha256 = sha("something else entirely"); // the read-back reports a hash that is not the written content's
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("warning");
    expect(editor.file().baseSha256).toBe(sha(ORIGINAL)); // submitted base kept, not the odd read-back hash
    expect(isDirty(editor.file())).toBe(true);

    // the disk now holds "v2", which is not the original base, so an ordinary save is refused
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("conflict");
    expect(backend.disk.get(PATH)).toBe("v2\n");
  });

  it("a normal verified save is unaffected: the next ordinary save works with no conflict", async () => {
    editor.type(PATH, "v2\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("verified");
    editor.type(PATH, "v3\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("verified");
    expect(backend.disk.get(PATH)).toBe("v3\n");
  });
});

describe("reload from disk", () => {
  beforeEach(() => {
    editor.type(PATH, "my unsaved edit\n");
    backend.disk.set(PATH, "disk version\n");
  });

  it("asks for confirmation before discarding unsaved edits, naming the file", async () => {
    editor.confirms = [false];
    await reloadFromDisk(editor.ctx, PATH);
    expect(editor.confirmMessages).toEqual([reloadConfirmText(PATH)]);
    expect(editor.confirmMessages[0]).toContain(PATH);
    expect(editor.confirmMessages[0].toLowerCase()).toContain("discard");
  });

  it("changes nothing, and does not even read the disk, when the user declines", async () => {
    editor.confirms = [false];
    const result = await reloadFromDisk(editor.ctx, PATH);
    editor.apply(result);

    expect(backend.calls).toEqual([]);
    expect(editor.file().buffer).toBe("my unsaved edit\n");
    expect(result.save).toBeUndefined(); // an existing conflict banner stays
    expect(isDirty(editor.file())).toBe(true);
  });

  it("replaces the text with the disk content and the hash with the disk hash when the user confirms", async () => {
    editor.confirms = [true];
    editor.apply(await reloadFromDisk(editor.ctx, PATH));

    expect(editor.file().buffer).toBe("disk version\n");
    expect(editor.file().saved).toBe("disk version\n");
    expect(editor.file().baseSha256).toBe(sha("disk version\n"));
    expect(isDirty(editor.file())).toBe(false);
    expect(editor.save).toEqual({ status: "idle" });
  });

  it("does not ask when there is nothing to lose", async () => {
    editor.type(PATH, ORIGINAL); // back to what was loaded
    editor.apply(await reloadFromDisk(editor.ctx, PATH));
    expect(editor.confirmMessages).toEqual([]);
    expect(editor.file().buffer).toBe("disk version\n");
  });

  it("keeps the user's text if the file cannot be read after they confirmed", async () => {
    editor.confirms = [true];
    backend.disk.delete(PATH);
    editor.apply(await reloadFromDisk(editor.ctx, PATH));

    expect(editor.save.status).toBe("error");
    expect((editor.save as { message: string }).message).toContain("Your text is unchanged");
    expect(editor.file().buffer).toBe("my unsaved edit\n");
    expect(isDirty(editor.file())).toBe(true);
  });

  it("after a reload the next save is based on the new hash and succeeds (the conflict is resolved)", async () => {
    editor.confirms = [true];
    editor.apply(await reloadFromDisk(editor.ctx, PATH));
    editor.type(PATH, "disk version\nplus my second attempt\n");
    editor.apply(await saveFile(editor.ctx, PATH));

    expect(backend.calls[backend.calls.length - 2]).toBe(`save:${PATH}:${sha("disk version\n")}`);
    expect(editor.save.status).toBe("verified");
    expect(backend.disk.get(PATH)).toBe("disk version\nplus my second attempt\n");
  });
});

describe("overwrite with my text", () => {
  beforeEach(async () => {
    editor.type(PATH, "my edit\n");
    backend.disk.set(PATH, "someone else's edit\n");
    editor.apply(await saveFile(editor.ctx, PATH)); // the conflict
    backend.calls.length = 0;
  });

  it("asks first, making clear that the disk version will be replaced", async () => {
    editor.confirms = [false];
    await overwriteWithMine(editor.ctx, PATH);
    expect(editor.confirmMessages).toEqual([overwriteConfirmText(PATH)]);
    expect(editor.confirmMessages[0]).toContain(PATH);
    expect(editor.confirmMessages[0].toLowerCase()).toContain("overwrite");
    expect(editor.confirmMessages[0].toLowerCase()).toContain("replaces");
  });

  it("does nothing at all when the user declines: no request, text and conflict untouched", async () => {
    editor.confirms = [false];
    const result = await overwriteWithMine(editor.ctx, PATH);
    editor.apply(result);

    expect(backend.calls).toEqual([]);
    expect(backend.disk.get(PATH)).toBe("someone else's edit\n");
    expect(editor.file().buffer).toBe("my edit\n");
    expect(result.save).toBeUndefined();
    expect(editor.save.status).toBe("conflict");
  });

  it("fetches the LATEST hash first and saves on that, not on the stale one", async () => {
    editor.confirms = [true];
    editor.apply(await overwriteWithMine(editor.ctx, PATH));

    expect(backend.calls[0]).toBe(`fetch:${PATH}`);
    expect(backend.calls[1]).toBe(`save:${PATH}:${sha("someone else's edit\n")}`);
    expect(backend.calls[1]).not.toContain(sha(ORIGINAL));
  });

  it("writes the user's text, reports a verified save, and stores the new hash", async () => {
    editor.confirms = [true];
    editor.apply(await overwriteWithMine(editor.ctx, PATH));

    expect(backend.disk.get(PATH)).toBe("my edit\n");
    expect(editor.save.status).toBe("verified");
    expect(editor.file().baseSha256).toBe(sha("my edit\n"));
    expect(editor.file().saved).toBe("my edit\n");
    expect(isDirty(editor.file())).toBe(false);
  });

  it("uses the text as it is NOW, including anything typed after the conflict appeared", async () => {
    editor.type(PATH, "my edit, extended after the conflict\n");
    editor.confirms = [true];
    editor.apply(await overwriteWithMine(editor.ctx, PATH));
    expect(backend.disk.get(PATH)).toBe("my edit, extended after the conflict\n");
  });

  it("still conflicts, and overwrites nothing, if the file changes AGAIN after its latest hash was read", async () => {
    editor.confirms = [true];
    backend.duringSave = () => backend.disk.set(PATH, "a third writer got in first\n");
    editor.apply(await overwriteWithMine(editor.ctx, PATH));

    expect(editor.save.status).toBe("conflict");
    expect(backend.disk.get(PATH)).toBe("a third writer got in first\n");
    expect(editor.file().buffer).toBe("my edit\n");
    expect(isDirty(editor.file())).toBe(true);
  });

  it("sends no save and keeps the text if the latest hash cannot be read (e.g. the file was deleted)", async () => {
    editor.confirms = [true];
    backend.disk.delete(PATH);
    editor.apply(await overwriteWithMine(editor.ctx, PATH));

    expect(backend.calls.some((c) => c.startsWith("save:"))).toBe(false);
    expect(editor.save.status).toBe("error");
    expect((editor.save as { message: string }).message).toContain("Nothing was overwritten");
    expect(editor.file().buffer).toBe("my edit\n");
    expect(backend.disk.has(PATH)).toBe(false);
  });

  it("works even if the user had reverted their text to what was loaded (an explicit overwrite is still honoured)", async () => {
    editor.type(PATH, ORIGINAL);
    editor.confirms = [true];
    editor.apply(await overwriteWithMine(editor.ctx, PATH));
    expect(backend.disk.get(PATH)).toBe(ORIGINAL);
    expect(editor.save.status).toBe("verified");
  });
});

describe("the whole conflict story, end to end", () => {
  it("edit -> external change -> conflict -> reload (confirmed) -> edit again -> save succeeds", async () => {
    editor.type(PATH, "my first attempt\n");
    backend.disk.set(PATH, "changed elsewhere\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("conflict");

    editor.confirms = [true];
    editor.apply(await reloadFromDisk(editor.ctx, PATH));
    expect(editor.file().buffer).toBe("changed elsewhere\n");

    editor.type(PATH, "changed elsewhere\nmy second attempt\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("verified");
    expect(backend.disk.get(PATH)).toBe("changed elsewhere\nmy second attempt\n");
  });

  it("edit -> external change -> conflict -> overwrite (confirmed) -> later saves keep working", async () => {
    editor.type(PATH, "mine\n");
    backend.disk.set(PATH, "theirs\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("conflict");

    editor.confirms = [true];
    editor.apply(await overwriteWithMine(editor.ctx, PATH));
    expect(backend.disk.get(PATH)).toBe("mine\n");

    editor.type(PATH, "mine, then more\n");
    editor.apply(await saveFile(editor.ctx, PATH));
    expect(editor.save.status).toBe("verified");
    expect(backend.disk.get(PATH)).toBe("mine, then more\n");
  });
});
