import { describe, expect, it, vi } from "vitest";
import {
  MONACO_ASSET_PATH,
  handleUnhandledRejection,
  installMonacoCancellationHandler,
  isMonacoCancellation,
  topStackFrame,
} from "@/lib/monacoCancellation";

const ORIGIN = "http://127.0.0.1:3000";
const MONACO_JS = `${ORIGIN}${MONACO_ASSET_PATH}/editor/editor.main.js`;

/** Build an error with an exact name, message and stack text (the stack is what the browser would have captured). */
function errorWith(name: string, message: string, stack: string | undefined, ctor: new (m: string) => Error = Error): Error {
  const e = new ctor(message);
  e.name = name;
  Object.defineProperty(e, "stack", { value: stack, configurable: true });
  return e;
}

// The first 10 frames of the real rejection, captured from the running app in a real browser (Edge, monaco-editor 0.52.2).
const REAL_V8_STACK = [
  "Canceled: Canceled",
  `    at i.cancel (${MONACO_JS}:122:13889)`,
  `    at i.dispose (${MONACO_JS}:122:14018)`,
  `    at t (${MONACO_JS}:11:22161)`,
  `    at g.clear (${MONACO_JS}:11:22775)`,
  `    at g.dispose (${MONACO_JS}:11:22685)`,
  `    at P.dispose (${MONACO_JS}:722:24461)`,
  `    at c.value (${MONACO_JS}:722:24961)`,
  `    at u._deliver (${MONACO_JS}:71:910)`,
  `    at u._deliverQueue (${MONACO_JS}:71:1001)`,
  `    at u.fire (${MONACO_JS}:71:1336)`,
].join("\n");

/** Monaco's own class shape (errors.js): super("Canceled"); this.name = this.message. */
class CancellationError extends Error {
  constructor(_message = "Canceled") {
    super("Canceled");
    this.name = this.message;
  }
}

function rejection(reason: unknown, cancelable = true): Event {
  const event = new Event("unhandledrejection", { cancelable });
  Object.defineProperty(event, "reason", { value: reason });
  return event;
}

describe("what IS treated as Monaco's expected cancellation", () => {
  it("the exact signature captured from the real browser (Chromium stack, same origin)", () => {
    expect(isMonacoCancellation(errorWith("Canceled", "Canceled", REAL_V8_STACK), ORIGIN)).toBe(true);
  });

  it("an instance of Monaco's own CancellationError shape", () => {
    expect(isMonacoCancellation(errorWith("Canceled", "Canceled", REAL_V8_STACK, CancellationError), ORIGIN)).toBe(true);
  });

  it("Gecko/WebKit-style frames ('fn@url', no 'name: message' header)", () => {
    const stack = [`cancel@${MONACO_JS}:122:13889`, `dispose@${MONACO_JS}:122:14018`].join("\n");
    expect(isMonacoCancellation(errorWith("Canceled", "Canceled", stack), ORIGIN)).toBe(true);
  });

  it("is not thrown off by a V8 header that differs from the current name (header skipped, frame decides)", () => {
    const stack = `Error: Canceled\n    at i.cancel (${MONACO_JS}:1:1)`;
    expect(isMonacoCancellation(errorWith("Canceled", "Canceled", stack), ORIGIN)).toBe(true);
  });
});

describe("what is NOT suppressed (every case must stay visible)", () => {
  const monacoTop = `Canceled: Canceled\n    at i.cancel (${MONACO_JS}:1:1)`;
  const cases: Array<[string, unknown]> = [
    // name / message alone
    ["name Canceled but another message", errorWith("Canceled", "real failure", monacoTop)],
    ["message Canceled but name is Error", errorWith("Error", "Canceled", monacoTop)],
    ["message Canceled but name TypeError", errorWith("TypeError", "Canceled", monacoTop)],
    ["name 'canceled' (wrong case)", errorWith("canceled", "Canceled", monacoTop)],
    ["name AbortError / message 'Canceled'", errorWith("AbortError", "Canceled", monacoTop)],
    ["name and message with trailing space", errorWith("Canceled ", "Canceled ", monacoTop)],
    // stack alone
    ["Monaco top frame but unrelated error (boom)", errorWith("Error", "boom", monacoTop)],
    ["Monaco top frame, name Error, message Canceled", errorWith("Error", "Canceled", monacoTop)],
    // right name+message, wrong origin of the frame
    ["Canceled/Canceled created by app code", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at doWork (${ORIGIN}/_next/static/chunks/app.js:1:1)`)],
    ["Canceled/Canceled with Monaco only deeper in the stack", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at appCode (${ORIGIN}/_next/static/chunks/app.js:1:1)\n    at i.cancel (${MONACO_JS}:1:1)`)],
    ["Canceled/Canceled, top frame on another origin", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at i.cancel (https://evil.example${MONACO_ASSET_PATH}/editor/editor.main.js:1:1)`)],
    ["Canceled/Canceled, same origin but a different path (/monaco/other/)", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at i.cancel (${ORIGIN}/monaco/other/editor.main.js:1:1)`)],
    ["Canceled/Canceled, lookalike path (/monaco/vsx/)", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at i.cancel (${ORIGIN}/monaco/vsx/editor.main.js:1:1)`)],
    ["Canceled/Canceled, lookalike path (/x/monaco/vs/ under the origin)", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at i.cancel (${ORIGIN}/x/monaco/vs/editor.main.js:1:1)`)],
    ["Canceled/Canceled, Monaco URL only inside another host's query string", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at i.cancel (https://evil.example/?u=${MONACO_JS}:1:1)`)],
    ["Canceled/Canceled, origin embedded after other text", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at i.cancel (evil${MONACO_JS}:1:1)`)],
    // stack missing or unusable
    ["Canceled/Canceled with no stack", errorWith("Canceled", "Canceled", undefined)],
    ["Canceled/Canceled with an empty stack", errorWith("Canceled", "Canceled", "")],
    ["Canceled/Canceled with only the header line", errorWith("Canceled", "Canceled", "Canceled: Canceled")],
    ["Canceled/Canceled with a non-string stack", errorWith("Canceled", "Canceled", 42 as unknown as string)],
    // not an Error at all
    ["plain object with matching fields", { name: "Canceled", message: "Canceled", stack: monacoTop }],
    ["the string 'Canceled'", "Canceled"],
    ["the string 'Canceled: Canceled'", "Canceled: Canceled"],
    ["a stack-like string", monacoTop],
    ["null", null],
    ["undefined", undefined],
    ["a number", 42],
    ["a boolean", true],
    ["an array", ["Canceled"]],
    ["a plain Error('boom')", new Error("boom")],
    ["a TypeError", new TypeError("x is not a function")],
  ];

  it.each(cases)("%s", (_name, reason) => {
    expect(isMonacoCancellation(reason, ORIGIN)).toBe(false);
  });

  it("an empty or missing origin never matches (fails visible)", () => {
    const e = errorWith("Canceled", "Canceled", REAL_V8_STACK);
    expect(isMonacoCancellation(e, "")).toBe(false);
    expect(isMonacoCancellation(e, undefined as unknown as string)).toBe(false);
  });

  it("an error whose stack getter throws does not make the check throw, and is not suppressed", () => {
    const hostile = new Error("Canceled");
    hostile.name = "Canceled";
    Object.defineProperty(hostile, "stack", { get() { throw new Error("hostile getter"); } });
    expect(() => isMonacoCancellation(hostile, ORIGIN)).not.toThrow();
    expect(isMonacoCancellation(hostile, ORIGIN)).toBe(false);
  });

  it("a proxy that throws on any access does not make the check throw, and is not suppressed", () => {
    const proxy = new Proxy(new Error("Canceled"), { get() { throw new Error("no access"); } });
    expect(() => isMonacoCancellation(proxy, ORIGIN)).not.toThrow();
    expect(isMonacoCancellation(proxy, ORIGIN)).toBe(false);
  });
});

describe("topStackFrame", () => {
  it("returns the first frame and skips the V8 header", () => {
    expect(topStackFrame(errorWith("Canceled", "Canceled", REAL_V8_STACK))).toBe(`at i.cancel (${MONACO_JS}:122:13889)`);
  });
  it("returns the first Gecko-style frame", () => {
    expect(topStackFrame(errorWith("E", "m", `fn@${MONACO_JS}:1:1\nother@x:2:2`))).toBe(`fn@${MONACO_JS}:1:1`);
  });
  it("returns null without a usable stack", () => {
    expect(topStackFrame(errorWith("E", "m", undefined))).toBeNull();
    expect(topStackFrame(errorWith("E", "m", "E: m"))).toBeNull();
  });
});

describe("the event handler", () => {
  it("marks the genuine cancellation as handled (default prevented)", () => {
    const event = rejection(errorWith("Canceled", "Canceled", REAL_V8_STACK));
    handleUnhandledRejection(event, ORIGIN);
    expect(event.defaultPrevented).toBe(true);
  });

  it.each([
    ["an unrelated Error", new Error("boom")],
    ["a string reason", "just a string"],
    ["Canceled/Canceled from non-Monaco code", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at x (${ORIGIN}/app.js:1:1)`)],
    ["name only", errorWith("Canceled", "other", REAL_V8_STACK)],
    ["stack only", errorWith("TypeError", "Canceled", REAL_V8_STACK)],
    ["another origin", errorWith("Canceled", "Canceled", `Canceled: Canceled\n    at i.cancel (https://evil.example/monaco/vs/editor/editor.main.js:1:1)`)],
    ["undefined", undefined],
  ])("leaves %s visible (default NOT prevented)", (_name, reason) => {
    const event = rejection(reason);
    handleUnhandledRejection(event, ORIGIN);
    expect(event.defaultPrevented).toBe(false);
  });

  it("does not throw on a non-cancelable event (it simply cannot prevent it)", () => {
    const event = rejection(errorWith("Canceled", "Canceled", REAL_V8_STACK), false);
    expect(() => handleUnhandledRejection(event, ORIGIN)).not.toThrow();
    expect(event.defaultPrevented).toBe(false);
  });

  it("does not throw on an event with no 'reason' at all", () => {
    expect(() => handleUnhandledRejection(new Event("unhandledrejection", { cancelable: true }), ORIGIN)).not.toThrow();
  });

  it("never alters the reason it inspects", () => {
    const reason = errorWith("Canceled", "Canceled", REAL_V8_STACK);
    handleUnhandledRejection(rejection(reason), ORIGIN);
    expect([reason.name, reason.message, reason.stack]).toEqual(["Canceled", "Canceled", REAL_V8_STACK]);
  });
});

describe("it does not interfere with other listeners", () => {
  it("listeners registered before AND after it still receive the genuine event", () => {
    const target = new EventTarget();
    const early = vi.fn(), late = vi.fn();
    target.addEventListener("unhandledrejection", early);
    const release = installMonacoCancellationHandler(target, ORIGIN);
    target.addEventListener("unhandledrejection", late);

    const event = rejection(errorWith("Canceled", "Canceled", REAL_V8_STACK));
    target.dispatchEvent(event);

    expect(early).toHaveBeenCalledTimes(1);
    expect(late).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
    release();
  });

  it("other listeners receive non-matching events untouched, and those stay visible", () => {
    const target = new EventTarget();
    const other = vi.fn();
    const release = installMonacoCancellationHandler(target, ORIGIN);
    target.addEventListener("unhandledrejection", other);
    const event = rejection(new Error("boom"));
    target.dispatchEvent(event);
    expect(other).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(false);
    release();
  });

  it("is registered only for 'unhandledrejection' (no error / rejectionhandled / other listeners)", () => {
    const add = vi.fn(), remove = vi.fn();
    const release = installMonacoCancellationHandler({ addEventListener: add, removeEventListener: remove }, ORIGIN);
    expect(add).toHaveBeenCalledTimes(1);
    expect(add.mock.calls[0][0]).toBe("unhandledrejection");
    release();
    expect(remove.mock.calls.map((c) => c[0])).toEqual(["unhandledrejection"]);
  });

  it("a synchronous 'error' event is never touched", () => {
    const target = new EventTarget();
    const release = installMonacoCancellationHandler(target, ORIGIN);
    const event = new Event("error", { cancelable: true });
    Object.defineProperty(event, "reason", { value: errorWith("Canceled", "Canceled", REAL_V8_STACK) });
    target.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    release();
  });
});

describe("lifecycle: mount, unmount, remount", () => {
  const fakeTarget = () => ({ addEventListener: vi.fn(), removeEventListener: vi.fn() });

  it("adds exactly one listener however many times it is installed", () => {
    const t = fakeTarget();
    installMonacoCancellationHandler(t, ORIGIN);
    installMonacoCancellationHandler(t, ORIGIN);
    installMonacoCancellationHandler(t, ORIGIN);
    expect(t.addEventListener).toHaveBeenCalledTimes(1);
  });

  it("removes the listener only when the LAST user releases it, using the same function it added", () => {
    const t = fakeTarget();
    const a = installMonacoCancellationHandler(t, ORIGIN);
    const b = installMonacoCancellationHandler(t, ORIGIN);
    a();
    expect(t.removeEventListener).not.toHaveBeenCalled();
    b();
    expect(t.removeEventListener).toHaveBeenCalledTimes(1);
    expect(t.removeEventListener.mock.calls[0][1]).toBe(t.addEventListener.mock.calls[0][1]);
  });

  it("release is idempotent: calling it twice cannot release someone else's registration", () => {
    const t = fakeTarget();
    const a = installMonacoCancellationHandler(t, ORIGIN);
    const b = installMonacoCancellationHandler(t, ORIGIN);
    a(); a(); a();
    expect(t.removeEventListener).not.toHaveBeenCalled();   // b still holds it
    b();
    expect(t.removeEventListener).toHaveBeenCalledTimes(1);
  });

  it("a full unmount followed by a remount registers one fresh listener", () => {
    const t = fakeTarget();
    installMonacoCancellationHandler(t, ORIGIN)();
    installMonacoCancellationHandler(t, ORIGIN);
    expect(t.addEventListener).toHaveBeenCalledTimes(2);
    expect(t.removeEventListener).toHaveBeenCalledTimes(1);
  });

  it("React strict-mode style (mount, cleanup, mount) ends with exactly one active listener that still works", () => {
    const target = new EventTarget();
    const first = installMonacoCancellationHandler(target, ORIGIN);
    first();
    const second = installMonacoCancellationHandler(target, ORIGIN);
    const event = rejection(errorWith("Canceled", "Canceled", REAL_V8_STACK));
    target.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    second();
  });

  it("after the last release the handler is gone: the same cancellation is no longer suppressed", () => {
    const target = new EventTarget();
    installMonacoCancellationHandler(target, ORIGIN)();
    const event = rejection(errorWith("Canceled", "Canceled", REAL_V8_STACK));
    target.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("different targets are independent", () => {
    const a = fakeTarget(), b = fakeTarget();
    const releaseA = installMonacoCancellationHandler(a, ORIGIN);
    installMonacoCancellationHandler(b, ORIGIN);
    releaseA();
    expect(a.removeEventListener).toHaveBeenCalledTimes(1);
    expect(b.removeEventListener).not.toHaveBeenCalled();
  });
});
