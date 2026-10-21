// Monaco's expected-cancellation signature, and a handler that marks ONLY that signature as handled.
//
// Why this exists: when the editor switches models (tab switch) within ~50 ms of a cursor move, Monaco's occurrence
// highlighter disposes a pending `Delayer(50)`, whose `cancel()` rejects an internal promise with a CancellationError
// that nothing listens to (monaco-editor 0.52.2: wordHighlighter.js:165/184/622-625, async.js:216-222). Monaco itself
// treats such errors as ignorable (errors.js isCancellationError / onUnexpectedError), but this particular rejection
// never passes through that filter, so the browser reports it as an uncaught promise rejection. It is harmless: the
// disposal completes, the editor keeps working, and highlighting is unaffected.
//
// The handler is deliberately narrow. It marks a rejection as handled (event.preventDefault()) only when ALL of these hold:
//   * the reason is an Error instance,
//   * its name AND its message are both exactly "Canceled",
//   * the frame that created it (the TOP stack frame) is in the Monaco bundle served from this page's own origin.
// Anything else (other errors, strings, a "Canceled" from other code, the same name with another message, a Monaco
// frame only deeper in the stack, another origin, synchronous exceptions) is left alone and stays visible. The handler
// never stops propagation, so other listeners still receive every event.

/**
 * Where Monaco is served from (public/monaco/vs, copied by scripts/copy-monaco.mjs). Shared by the loader
 * configuration and the handler below, so the two cannot drift apart.
 */
export const MONACO_ASSET_PATH = "/monaco/vs";

const CANCELED = "Canceled";

/** The top stack frame (where the error was created), or null. Handles V8 ("    at fn (url)") and Gecko/WebKit ("fn@url"). */
export function topStackFrame(error: Error): string | null {
  const stack = error.stack;
  if (typeof stack !== "string") return null;
  const lines = stack.split("\n").map((line) => line.trim());
  // V8 prints a "name: message" header first; it is neither an "at ..." frame nor a "fn@url" frame, so it is skipped.
  const frame = lines.find((line) => /^at\s/.test(line) || line.includes("@"));
  return frame ?? null;
}

/** True if the frame's script URL starts with `<origin>/monaco/vs/` (the URL must begin the frame text or follow "(", "@" or a space). */
function isMonacoFrame(frame: string, origin: string): boolean {
  const prefix = `${origin}${MONACO_ASSET_PATH}/`;
  const at = frame.indexOf(prefix);
  return at === 0 || (at > 0 && " (@".includes(frame.charAt(at - 1)));
}

/**
 * Is this rejection reason exactly Monaco's expected cancellation? `origin` is the page's own origin
 * (window.location.origin). Any doubt means false, i.e. the error stays visible.
 */
export function isMonacoCancellation(reason: unknown, origin: string): boolean {
  if (!origin) return false;
  try {
    if (!(reason instanceof Error)) return false;
    if (reason.name !== CANCELED || reason.message !== CANCELED) return false;
    const top = topStackFrame(reason);
    return top !== null && isMonacoFrame(top, origin);
  } catch {
    return false; // a hostile or broken reason object must never make the handler throw or hide anything
  }
}

/** The `unhandledrejection` listener: marks Monaco's cancellation as handled and touches nothing else. */
export function handleUnhandledRejection(event: Event, origin: string): void {
  const reason = (event as Event & { reason?: unknown }).reason;
  if (isMonacoCancellation(reason, origin)) event.preventDefault(); // no stopPropagation: other listeners still run
}

type Target = Pick<EventTarget, "addEventListener" | "removeEventListener">;
const installed = new WeakMap<object, { count: number; listener: EventListener }>();

/**
 * Register the handler on `target` (the window) and return a function that releases it. Reference-counted per target,
 * so repeated mounts (remounts, React strict-mode double effects) never create duplicate listeners, and the listener
 * is removed when the last user releases it. The returned release function is idempotent.
 */
export function installMonacoCancellationHandler(target: Target, origin: string): () => void {
  let entry = installed.get(target);
  if (!entry) {
    const listener: EventListener = (event) => handleUnhandledRejection(event, origin);
    entry = { count: 0, listener };
    installed.set(target, entry);
    target.addEventListener("unhandledrejection", listener);
  }
  entry.count += 1;

  let released = false;
  return () => {
    if (released) return;
    released = true;
    const current = installed.get(target);
    if (!current) return;
    current.count -= 1;
    if (current.count <= 0) {
      target.removeEventListener("unhandledrejection", current.listener);
      installed.delete(target);
    }
  };
}
