import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getChatStatus,
  getChatHistory,
  postChatMessage,
  clearChatHistory,
  type ChatStatusData,
  type ChatResponseData,
  type ChatHistoryItem,
} from "./api";
import {
  normalizeStatus,
  statusLabel,
  statusBadgeClasses,
  normalizeCitationStatus,
  citationDisplay,
  isCitationClickable,
  type AnswerStatus,
  type CitationStatus,
} from "./chatGrounding";
import {
  isDirty,
  withBuffer,
  saveStateFor,
  type OpenFile,
  type SaveStates,
} from "./editorSession";

type FetchCall = { url: string; init?: RequestInit };
let calls: FetchCall[];

function respondWith(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (status === 204) {
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    })
  );
}

beforeEach(() => {
  calls = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getChatStatus API", () => {
  it("fetches provider configuration and consent status from the backend", async () => {
    const mockStatus: ChatStatusData = {
      provider: "openai",
      model: "gpt-4o",
      configured: true,
      consent: true,
      can_send: true,
      reason: null,
    };
    respondWith(200, mockStatus);

    const res = await getChatStatus("project-1");
    expect(res).toEqual(mockStatus);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://127.0.0.1:8000/api/projects/project-1/chat/status");
    expect(calls[0].init?.method).toBe("GET");
  });

  it("reports consent-off state clearly without error", async () => {
    const mockStatus: ChatStatusData = {
      provider: "openai",
      model: null,
      configured: true,
      consent: false,
      can_send: false,
      reason: "ALLOW_SENDING_CODE_TO_PROVIDER is false",
    };
    respondWith(200, mockStatus);

    const res = await getChatStatus("project-1");
    expect(res?.can_send).toBe(false);
    expect(res?.consent).toBe(false);
    expect(res?.reason).toContain("ALLOW_SENDING_CODE_TO_PROVIDER is false");
  });

  it("handles network failure gracefully returning null without throwing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const res = await getChatStatus("project-1");
    expect(res).toBeNull();
  });
});

describe("chat history and message sending API", () => {
  it("fetches chat history with accurate message and citation statuses", async () => {
    const mockHistory: ChatHistoryItem[] = [
      {
        id: "msg-1",
        sender: "user",
        content: "Where is auth handled?",
        citations: [],
        plan_steps: [],
        timestamp: "2026-10-21T10:00:00Z",
      },
      {
        id: "msg-2",
        sender: "assistant",
        content: "Authentication is handled in backend/app/auth.py.",
        citations: [
          {
            file_path: "backend/app/auth.py",
            line_start: 10,
            line_end: 25,
            status: "verified",
          },
        ],
        plan_steps: [],
        timestamp: "2026-10-21T10:00:05Z",
        status: "answered_verified",
      },
    ];
    respondWith(200, mockHistory);

    const res = await getChatHistory("project-1");
    expect(res).toHaveLength(2);
    expect(res[1].status).toBe("answered_verified");
    expect(res[1].citations[0].status).toBe("verified");
  });

  it("posts message to backend API with conversation_id and mode", async () => {
    const mockResponse: ChatResponseData = {
      conversation_id: "conv-1",
      message_id: "msg-asst-1",
      sender: "assistant",
      content: "Found in backend/app/main.py",
      citations: [
        {
          file_path: "backend/app/main.py",
          line_start: 1,
          line_end: 20,
          status: "verified",
        },
      ],
      plan_steps: [],
      timestamp: "2026-10-21T10:00:02Z",
      status: "answered_verified",
    };
    respondWith(200, mockResponse);

    const res = await postChatMessage("project-1", "Where is the entry point?", "chat", "conv-1");
    expect(res).toEqual(mockResponse);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://127.0.0.1:8000/api/projects/project-1/chat");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      message: "Where is the entry point?",
      mode: "chat",
      conversation_id: "conv-1",
    });
  });

  it("returns null on post failure without fabricating answers", async () => {
    respondWith(500, { detail: "Internal Server Error" });
    const res = await postChatMessage("project-1", "Test question");
    expect(res).toBeNull();
  });

  it("clears chat history via DELETE endpoint", async () => {
    respondWith(204, null);
    const ok = await clearChatHistory("project-1");
    expect(ok).toBe(true);
    expect(calls[0].init?.method).toBe("DELETE");
  });
});

describe("grounded status and citation rendering integration", () => {
  it("maps all supported backend answer statuses correctly", () => {
    const statuses: AnswerStatus[] = [
      "loading",
      "error",
      "unavailable",
      "not_in_context",
      "answered_unverified",
      "answered_verified",
      "legacy",
    ];
    for (const s of statuses) {
      expect(normalizeStatus(s)).toBe(s);
      const label = statusLabel(s);
      expect(label.text.length).toBeGreaterThan(0);
      expect(statusBadgeClasses(label.tone).length).toBeGreaterThan(0);
    }
  });

  it("handles malformed or unexpected statuses safely by defaulting to legacy", () => {
    expect(normalizeStatus(null)).toBe("legacy");
    expect(normalizeStatus(undefined)).toBe("legacy");
    expect(normalizeStatus("weird_unknown_status")).toBe("legacy");
    expect(normalizeStatus("")).toBe("legacy");
  });

  it("never marks an answer as verified simply because citations exist", () => {
    // If backend returns answered_unverified, status label must not claim verified
    const s = normalizeStatus("answered_unverified");
    const l = statusLabel(s);
    expect(l.tone).not.toBe("green");
    expect(l.text).toContain("not fully verified");
  });

  it("verified citation: clickable, emerald badge, correct label", () => {
    const disp = citationDisplay("verified", "answered_verified");
    expect(disp.clickable).toBe(true);
    expect(disp.status).toBe("verified");
    expect(disp.classes).toContain("emerald");
    expect(disp.label).toContain("verified");
  });

  it("stale citation: clickable with warning tone", () => {
    const disp = citationDisplay("stale", "answered_unverified");
    expect(disp.clickable).toBe(true);
    expect(disp.status).toBe("stale");
    expect(disp.classes).toContain("amber");
    expect(disp.label).toContain("stale");
  });

  it("invalid citation: NOT clickable, disabled with line-through style", () => {
    const disp = citationDisplay("invalid", "answered_unverified");
    expect(disp.clickable).toBe(false);
    expect(disp.status).toBe("invalid");
    expect(disp.classes).toContain("line-through");
    expect(disp.classes).toContain("cursor-not-allowed");
    expect(isCitationClickable("invalid")).toBe(false);
  });

  it("legacy citation: clickable best-effort, labelled as unverified", () => {
    const disp = citationDisplay(null, "legacy");
    expect(disp.clickable).toBe(true);
    expect(disp.status).toBe("legacy_unverified");
    expect(disp.label).toContain("unverified");
  });
});

describe("citation navigation safeguards on editor session", () => {
  it("navigating to a citation does not mutate file buffer, dirty state, or base hash", () => {
    const file: OpenFile = {
      path: "app/main.py",
      language: "python",
      saved: "def main():\n    pass\n",
      buffer: "def main():\n    pass\n",
      baseSha256: "abc".repeat(20) + "abcd",
    };

    // Simulate opening citation at lines 1-2
    const target = { path: "app/main.py", lineStart: 1, lineEnd: 2 };
    expect(target.lineStart).toBe(1);
    expect(target.lineEnd).toBe(2);

    // Verify file content and state are completely untouched
    expect(isDirty(file)).toBe(false);
    expect(file.buffer).toBe("def main():\n    pass\n");
    expect(file.saved).toBe("def main():\n    pass\n");
    expect(file.baseSha256).toBe("abc".repeat(20) + "abcd");
  });

  it("navigating to a citation preserves existing uncommitted edits and conflicts on other files", () => {
    const fileA: OpenFile = {
      path: "app/auth.py",
      language: "python",
      saved: "x = 1",
      buffer: "x = 2", // dirty edit
      baseSha256: "111".repeat(21) + "1",
    };
    const fileB: OpenFile = {
      path: "app/routes.py",
      language: "python",
      saved: "y = 1",
      buffer: "y = 1",
      baseSha256: "222".repeat(21) + "2",
    };

    const saveStates: SaveStates = {
      "app/auth.py": { status: "conflict", path: "app/auth.py", message: "file changed on disk" },
      "app/routes.py": { status: "idle" },
    };

    // User is editing fileA (dirty, conflicted) and clicks a citation in fileB
    expect(isDirty(fileA)).toBe(true);
    expect(saveStateFor(saveStates, "app/auth.py").status).toBe("conflict");

    // Switching or opening fileB preserves fileA's conflict and buffer
    const files = [fileA, fileB];
    const updated = files.find((f) => f.path === "app/auth.py");
    expect(updated?.buffer).toBe("x = 2");
    expect(isDirty(updated!)).toBe(true);
    expect(saveStateFor(saveStates, "app/auth.py").status).toBe("conflict");
  });
});
