/**
 * Pure functions for displaying grounded answer status and citation states in the UI.
 *
 * Status values come from the backend (see app/api/chat.py ChatResponse.status):
 *   answered_verified | answered_unverified | not_in_context | unavailable | legacy | loading | error
 *
 * Citation-level status (see Citation.status):
 *   verified | stale  (invalid citations are filtered out by the backend and not listed)
 *
 * Legacy messages (pre-grounding) have status "legacy" or a missing/null status. They are labelled
 * "Legacy, not grounded" and their citations are explicitly marked as unverified.
 */

// -------------------------------------------------------------------------------------
// Answer-level status
// -------------------------------------------------------------------------------------

/** All recognized answer statuses. */
export type AnswerStatus =
  | "loading"
  | "error"
  | "unavailable"
  | "not_in_context"
  | "answered_unverified"
  | "answered_verified"
  | "legacy";

/** Normalise a status value from the backend (or null/undefined for legacy messages). */
export function normalizeStatus(raw: string | null | undefined): AnswerStatus {
  if (!raw) return "legacy";
  const known: AnswerStatus[] = [
    "loading",
    "error",
    "unavailable",
    "not_in_context",
    "answered_unverified",
    "answered_verified",
    "legacy",
  ];
  return known.includes(raw as AnswerStatus) ? (raw as AnswerStatus) : "legacy";
}

export interface StatusLabel {
  text: string;
  tone: "gray" | "green" | "amber" | "red" | "blue";
}

/** Human-readable label and colour tone for an answer status. */
export function statusLabel(status: AnswerStatus): StatusLabel {
  switch (status) {
    case "loading":
      return { text: "Loading…", tone: "blue" };
    case "error":
      return { text: "Error: answer could not be generated", tone: "red" };
    case "unavailable":
      return { text: "Unavailable: no provider configured or consent not given", tone: "red" };
    case "not_in_context":
      return { text: "Not in project context", tone: "amber" };
    case "answered_unverified":
      return { text: "Answered (citations not fully verified)", tone: "amber" };
    case "answered_verified":
      return { text: "Answered (all citations verified)", tone: "green" };
    case "legacy":
      return { text: "Legacy, not grounded", tone: "gray" };
  }
}

/** CSS class tokens for a status badge (Tailwind). */
export function statusBadgeClasses(tone: StatusLabel["tone"]): string {
  switch (tone) {
    case "green":
      return "bg-emerald-500/15 border-emerald-400/40 text-emerald-300";
    case "amber":
      return "bg-amber-500/15 border-amber-400/40 text-amber-200";
    case "red":
      return "bg-rose-500/15 border-rose-400/40 text-rose-200";
    case "blue":
      return "bg-blue-500/15 border-blue-400/40 text-blue-200";
    case "gray":
    default:
      return "bg-slate-700/40 border-slate-600/50 text-slate-400";
  }
}

// -------------------------------------------------------------------------------------
// Citation-level status
// -------------------------------------------------------------------------------------

export type CitationStatus = "verified" | "stale" | "invalid" | "legacy_unverified";

/**
 * Normalise a per-citation status value.
 *
 * When the answer itself is legacy (pre-grounding), ALL its citations are treated as unverified.
 * Invalid citations are filtered out by the backend, so they should not normally appear in the
 * payload; if they do, they are treated as non-clickable.
 */
export function normalizeCitationStatus(
  raw: string | null | undefined,
  answerStatus: AnswerStatus,
): CitationStatus {
  if (answerStatus === "legacy") return "legacy_unverified";
  if (raw === "verified") return "verified";
  if (raw === "stale") return "stale";
  if (raw === "invalid") return "invalid";
  return "legacy_unverified"; // missing status on a non-legacy answer: treat as unverified
}

/** Whether a citation should be clickable (opens file + line range). */
export function isCitationClickable(status: CitationStatus): boolean {
  // Verified and stale: can still open. Legacy unverified: can attempt to open (best effort).
  // Invalid: struck through, not clickable.
  return status !== "invalid";
}

/** A section header for the citations list, based on the answer status. */
export function citationsHeading(answerStatus: AnswerStatus): string {
  switch (answerStatus) {
    case "answered_verified":
      return "VERIFIED CITATIONS";
    case "answered_unverified":
      return "CITATIONS (not all verified)";
    case "legacy":
      return "CITATIONS (legacy, unverified)";
    default:
      return "FILES MENTIONED";
  }
}

export interface CitationDisplay {
  status: CitationStatus;
  clickable: boolean;
  /** Tailwind classes for the citation button/badge. */
  classes: string;
  /** Extra label shown next to the citation. */
  label: string;
}

export function citationDisplay(
  citationStatus: string | null | undefined,
  answerStatus: AnswerStatus,
): CitationDisplay {
  const s = normalizeCitationStatus(citationStatus, answerStatus);
  const clickable = isCitationClickable(s);
  switch (s) {
    case "verified":
      return {
        status: s,
        clickable,
        classes:
          "bg-emerald-900/30 hover:bg-emerald-600/20 border-emerald-700/50 text-emerald-300 hover:text-white cursor-pointer",
        label: "✓ verified",
      };
    case "stale":
      return {
        status: s,
        clickable,
        classes:
          "bg-amber-900/30 hover:bg-amber-600/20 border-amber-700/50 text-amber-300 hover:text-white cursor-pointer",
        label: "⚠ stale",
      };
    case "invalid":
      return {
        status: s,
        clickable: false,
        classes:
          "bg-slate-900/40 border-slate-700/50 text-slate-500 line-through cursor-not-allowed opacity-60",
        label: "invalid",
      };
    case "legacy_unverified":
      return {
        status: s,
        clickable,
        classes:
          "bg-slate-800/70 hover:bg-slate-700/60 border-slate-600/50 text-slate-400 hover:text-slate-200 cursor-pointer",
        label: "unverified",
      };
  }
}
