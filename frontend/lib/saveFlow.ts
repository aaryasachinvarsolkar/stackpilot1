// The editor's save, reload and overwrite flows, written against injected dependencies (the file API, the
// current open files, a confirm function) so they run and are tested without React, a browser or a network.
//
// Rules every flow follows:
//  * A save is always based on the hash of the content the editor loaded (base_sha256). Without a valid
//    hash nothing is sent at all.
//  * The user's text is only ever replaced by an explicit, confirmed reload. Every failure leaves it in
//    place and the file marked unsaved.
//  * A save is only called verified when the byte count, the content and the hash all match a fresh read.
//  * If a save does not verify, the SUBMITTED base hash is kept (the unexpected disk hash is never adopted),
//    so the next ordinary save is refused with 409 instead of silently overwriting what is on disk.
import type { ApiResult, FileContentData, FileSaveData } from "@/lib/api";
import {
  isDirty,
  isSha256,
  judgeSave,
  withUnverified,
  withReloaded,
  withSaved,
  type OpenFile,
  type SaveState,
} from "@/lib/editorSession";

export interface FileApi {
  fetchFile(projectId: string, path: string): Promise<ApiResult<FileContentData>>;
  saveFileContent(projectId: string, path: string, content: string, baseSha256: string): Promise<ApiResult<FileSaveData>>;
}

export interface FlowContext {
  api: FileApi;
  projectId: string;
  /** The open files right now (read after every await, so edits made meanwhile are never lost). */
  getFiles: () => OpenFile[];
  /** Ask the user to confirm; returns false if they decline. */
  confirm: (message: string) => boolean;
}

export interface FlowResult {
  /** Apply to the latest open files (never to a stale snapshot), so edits made during the request survive. */
  update: (files: OpenFile[]) => OpenFile[];
  /** The new save state; undefined leaves the current one (e.g. a cancelled confirmation changes nothing). */
  save?: SaveState;
}

const unchanged: FlowResult["update"] = (files) => files;

export const NO_HASH_MESSAGE =
  "This file cannot be saved: the backend did not report a content hash for it, so a save could not be " +
  "checked against changes on disk. Is the backend up to date? Your text is kept. Nothing was sent.";

export const reloadConfirmText = (path: string) =>
  `Discard your unsaved changes to ${path} and reload it from disk?`;

export const overwriteConfirmText = (path: string) =>
  `Overwrite ${path} on disk with the text in your editor?\n\n` +
  "This replaces whatever changed on the disk since you opened the file, and cannot be undone from here.";

const reason = (r: { message?: string }) => r.message ?? "unknown error";

/**
 * Save the file's current text. Pass `baseSha256` to base the save on a hash other than the one loaded
 * (used by "overwrite", after the latest hash was fetched) and `force` to save even if the text equals
 * what was last saved.
 */
export async function saveFile(
  ctx: FlowContext,
  path: string,
  options: { baseSha256?: string; force?: boolean } = {}
): Promise<FlowResult> {
  const entry = ctx.getFiles().find((f) => f.path === path);
  if (!entry || (!options.force && !isDirty(entry))) return { update: unchanged };

  const base = options.baseSha256 ?? entry.baseSha256;
  if (!isSha256(base)) return { update: unchanged, save: { status: "error", path, message: NO_HASH_MESSAGE } };

  const sent = entry.buffer;
  const written = await ctx.api.saveFileContent(ctx.projectId, path, sent, base);
  if (!written.ok || !written.data) {
    // 409 = the file changed on disk; anything else (428, 404, 400, 413, unreachable...) is a plain error.
    // Either way nothing was written, the user's text is untouched, and the file stays unsaved.
    return {
      update: unchanged,
      save: { status: written.status === 409 ? "conflict" : "error", path, message: reason(written) },
    };
  }

  const readBack = await ctx.api.fetchFile(ctx.projectId, path);
  if (!readBack.ok || !readBack.data) {
    return {
      update: (files) => withSaved(files, path, sent, written.data!.sha256),
      save: {
        status: "warning",
        path,
        message: `Backend accepted ${written.data.bytes_written} bytes, but reading the file back failed (${reason(readBack)}). Not verified.`,
      },
    };
  }

  const verdict = judgeSave(
    sent,
    { bytes: written.data.bytes_written, sha256: written.data.sha256 },
    { content: readBack.data.content, sha256: readBack.data.sha256 }
  );
  if (verdict.kind === "verified") {
    return {
      update: (files) => withSaved(files, path, sent, verdict.sha256),
      save: { status: "verified", path, bytes: verdict.bytes },
    };
  }

  // The disk differs from what was submitted. Do NOT adopt the unexpected disk hash as the new base: the file
  // stays marked unsaved, the user's text and the submitted base hash are kept, and so the next ordinary Save
  // is refused with 409 (the normal conflict flow) instead of silently overwriting what is on disk now.
  const detail =
    verdict.kind === "length-mismatch"
      ? `Sent ${verdict.sentBytes} bytes but the backend reports ${verdict.reportedBytes}. The file on disk may not match.`
      : verdict.kind === "hash-mismatch"
      ? "The hash reported for the write does not match the file read back. Check the file before relying on this save."
      : "The file on disk differs from what was sent. Check it before relying on this save.";
  const message = `${detail} Your text is kept and still marked unsaved; saving again will ask what to do.`;
  return {
    update: (files) => withUnverified(files, path),
    save: { status: "warning", path, message },
  };
}

/**
 * Throw away the editor's text for this file and load what is on disk. Confirms first if there are unsaved
 * edits; declining changes nothing. If the file cannot be read, the text is kept.
 */
export async function reloadFromDisk(ctx: FlowContext, path: string): Promise<FlowResult> {
  const entry = ctx.getFiles().find((f) => f.path === path);
  if (!entry) return { update: unchanged };
  if (isDirty(entry) && !ctx.confirm(reloadConfirmText(path))) return { update: unchanged };

  const latest = await ctx.api.fetchFile(ctx.projectId, path);
  if (!latest.ok || !latest.data) {
    return {
      update: unchanged,
      save: { status: "error", path, message: `Could not reload ${path}: ${reason(latest)}. Your text is unchanged.` },
    };
  }
  const disk = latest.data;
  if (!isSha256(disk.sha256)) return { update: unchanged, save: { status: "error", path, message: NO_HASH_MESSAGE } };
  return { update: (files) => withReloaded(files, path, disk.content, disk.sha256), save: { status: "idle" } };
}

/**
 * Explicitly overwrite the file on disk with the editor's text. Confirms first; then fetches the file's
 * CURRENT hash and saves based on that, so the overwrite replaces exactly the version the user was told
 * about. If the file changes again in between, the server answers 409 again and nothing is overwritten.
 */
export async function overwriteWithMine(ctx: FlowContext, path: string): Promise<FlowResult> {
  const entry = ctx.getFiles().find((f) => f.path === path);
  if (!entry) return { update: unchanged };
  if (!ctx.confirm(overwriteConfirmText(path))) return { update: unchanged };

  const latest = await ctx.api.fetchFile(ctx.projectId, path);
  if (!latest.ok || !latest.data) {
    return {
      update: unchanged,
      save: {
        status: "error",
        path,
        message: `Could not read the file's current hash: ${reason(latest)}. Nothing was overwritten. Your text is unchanged.`,
      },
    };
  }
  if (!isSha256(latest.data.sha256)) return { update: unchanged, save: { status: "error", path, message: NO_HASH_MESSAGE } };
  return saveFile(ctx, path, { baseSha256: latest.data.sha256, force: true });
}
