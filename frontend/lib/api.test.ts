import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchFile, fetchTree, saveFileContent } from "@/lib/api";

type FetchCall = { url: string; init?: RequestInit };
let calls: FetchCall[];

function respondWith(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    })
  );
}

beforeEach(() => {
  calls = [];
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const HASH = "a".repeat(64);
const NEW_HASH = "b".repeat(64);

describe("saveFileContent", () => {
  it("PUTs the path, content and base_sha256 as JSON to the project's file endpoint", async () => {
    respondWith(200, { status: "saved", path: "app/main.py", bytes_written: 7, sha256: NEW_HASH });
    const res = await saveFileContent("proj-1", "app/main.py", "x = 1\r\n", HASH);

    expect(res.ok).toBe(true);
    expect(res.data).toEqual({ status: "saved", path: "app/main.py", bytes_written: 7, sha256: NEW_HASH });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://127.0.0.1:8000/api/projects/proj-1/files/content");
    expect(calls[0].init?.method).toBe("PUT");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ path: "app/main.py", content: "x = 1\r\n", base_sha256: HASH });
  });

  it("returns the server's conflict message for a stale hash (HTTP 409)", async () => {
    respondWith(409, { detail: "The file changed on disk since it was loaded, so it was not overwritten. Nothing was written." });
    const res = await saveFileContent("p", "a", "x", HASH);
    expect(res).toMatchObject({ ok: false, status: 409 });
    expect(res.message).toContain("changed on disk");
    expect(res.data).toBeUndefined();
  });

  it("returns the server's message when the hash is missing (HTTP 428)", async () => {
    respondWith(428, { detail: "base_sha256 is required: send the sha256 of the content you loaded. Nothing was written." });
    const res = await saveFileContent("p", "a", "x", "");
    expect(res).toMatchObject({ ok: false, status: 428 });
    expect(res.message).toContain("base_sha256 is required");
  });

  it("returns the server's message when the file was deleted (HTTP 404)", async () => {
    respondWith(404, { detail: "File 'a' does not exist. This endpoint only updates existing files; it never creates files or folders." });
    const res = await saveFileContent("p", "a", "x", HASH);
    expect(res).toMatchObject({ ok: false, status: 404 });
    expect(res.message).toContain("never creates");
  });

  it("encodes the project key in the URL", async () => {
    respondWith(200, { status: "saved", path: "a", bytes_written: 0 });
    await saveFileContent("my project/../x", "a", "", HASH);
    expect(calls[0].url).toContain("/api/projects/my%20project%2F..%2Fx/files/content");
  });

  it("returns the server's own message for a rejected path (HTTP 400)", async () => {
    respondWith(400, { detail: "Illegal file path. Path traversal is strictly prohibited." });
    const res = await saveFileContent("p", "../x", "y", HASH);
    expect(res.ok).toBe(false);
    expect(res.status).toBe(400);
    expect(res.message).toBe("Illegal file path. Path traversal is strictly prohibited.");
    expect(res.data).toBeUndefined();
  });

  it("returns the size-limit message for HTTP 413", async () => {
    respondWith(413, { detail: "Content is 11 bytes; the limit is 10 bytes." });
    const res = await saveFileContent("p", "a", "x".repeat(11), HASH);
    expect(res).toMatchObject({ ok: false, status: 413, message: "Content is 11 bytes; the limit is 10 bytes." });
  });

  it("returns the folder-missing message for HTTP 404", async () => {
    respondWith(404, { detail: "Workspace folder for project 'p' does not exist on disk." });
    const res = await saveFileContent("p", "a", "x", HASH);
    expect(res).toMatchObject({ ok: false, status: 404 });
    expect(res.message).toContain("does not exist on disk");
  });

  it("joins validation messages when the server answers with a list (HTTP 422)", async () => {
    respondWith(422, { detail: [{ msg: "Field required" }, { msg: "Input should be a string" }] });
    const res = await saveFileContent("p", "a", "x", HASH);
    expect(res).toMatchObject({ ok: false, status: 422, message: "Field required; Input should be a string" });
  });

  it("falls back to the HTTP status when the error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>oops</html>", { status: 502 })));
    const res = await saveFileContent("p", "a", "x", HASH);
    expect(res).toMatchObject({ ok: false, status: 502, message: "The backend answered HTTP 502" });
  });

  it("reports status 0 and a clear message when the backend cannot be reached, instead of throwing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const res = await saveFileContent("p", "a", "x", HASH);
    expect(res).toEqual({ ok: false, status: 0, message: "The backend could not be reached" });
  });
});

describe("reading files", () => {
  it("encodes awkward file names in the query string", async () => {
    respondWith(200, { path: "my notes #1 & more.txt", file_name: "x", content: "", line_count: 0, language: "plaintext" });
    await fetchFile("p", "my notes #1 & more.txt");
    expect(calls[0].url).toBe(
      "http://127.0.0.1:8000/api/projects/p/files/content?path=my%20notes%20%231%20%26%20more.txt"
    );
  });

  it("passes through the binary-file rejection (HTTP 415) so the editor can say why it cannot open the file", async () => {
    respondWith(415, { detail: "Binary files are not supported." });
    const res = await fetchFile("p", "logo.png");
    expect(res).toMatchObject({ ok: false, status: 415, message: "Binary files are not supported." });
  });

  it("never substitutes data for a missing file", async () => {
    respondWith(404, { detail: "File 'gone.py' not found." });
    const res = await fetchFile("p", "gone.py");
    expect(res.ok).toBe(false);
    expect(res.data).toBeUndefined();
  });

  it("reports an unreachable backend when listing the tree", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    expect(await fetchTree("p")).toMatchObject({ ok: false, status: 0 });
  });
});
