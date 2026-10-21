import { describe, expect, it } from "vitest";
import {
  normalizeStatus,
  statusLabel,
  statusBadgeClasses,
  normalizeCitationStatus,
  isCitationClickable,
  citationsHeading,
  citationDisplay,
  type AnswerStatus,
  type CitationStatus,
} from "./chatGrounding";

// -------------------------------------------------------------------------------------
// normalizeStatus
// -------------------------------------------------------------------------------------

describe("normalizeStatus", () => {
  it("maps null to legacy", () => expect(normalizeStatus(null)).toBe("legacy"));
  it("maps undefined to legacy", () => expect(normalizeStatus(undefined)).toBe("legacy"));
  it("maps empty string to legacy", () => expect(normalizeStatus("")).toBe("legacy"));
  it("maps an unknown string to legacy", () => expect(normalizeStatus("surprise")).toBe("legacy"));

  const known: AnswerStatus[] = [
    "loading",
    "error",
    "unavailable",
    "not_in_context",
    "answered_unverified",
    "answered_verified",
    "legacy",
  ];
  for (const s of known) {
    it(`preserves "${s}"`, () => expect(normalizeStatus(s)).toBe(s));
  }
});

// -------------------------------------------------------------------------------------
// statusLabel
// -------------------------------------------------------------------------------------

describe("statusLabel", () => {
  it("labels loading as blue", () => {
    const l = statusLabel("loading");
    expect(l.tone).toBe("blue");
    expect(l.text.toLowerCase()).toContain("loading");
  });

  it("labels error as red", () => {
    const l = statusLabel("error");
    expect(l.tone).toBe("red");
    expect(l.text.toLowerCase()).toContain("error");
  });

  it("labels unavailable as red", () => {
    const l = statusLabel("unavailable");
    expect(l.tone).toBe("red");
    expect(l.text.toLowerCase()).toContain("unavailable");
  });

  it("labels not_in_context as amber", () => {
    const l = statusLabel("not_in_context");
    expect(l.tone).toBe("amber");
  });

  it("labels answered_unverified as amber with a not-fully-verified note", () => {
    const l = statusLabel("answered_unverified");
    expect(l.tone).toBe("amber");
    expect(l.text.toLowerCase()).toContain("not fully verified");
  });

  it("labels answered_verified as green", () => {
    const l = statusLabel("answered_verified");
    expect(l.tone).toBe("green");
    expect(l.text.toLowerCase()).toContain("verified");
  });

  it("labels legacy as gray with 'not grounded'", () => {
    const l = statusLabel("legacy");
    expect(l.tone).toBe("gray");
    expect(l.text.toLowerCase()).toContain("legacy");
    expect(l.text.toLowerCase()).toContain("not grounded");
  });

  it("never infers verified from the presence of citations (this is a pure status map)", () => {
    // answered_unverified must NOT be relabeled as verified even though
    // the UI might display citations. The backend alone decides verification status.
    const l = statusLabel("answered_unverified");
    expect(l.tone).not.toBe("green");
  });
});

// -------------------------------------------------------------------------------------
// statusBadgeClasses
// -------------------------------------------------------------------------------------

describe("statusBadgeClasses", () => {
  it("returns a non-empty string for every tone", () => {
    for (const tone of ["green", "amber", "red", "blue", "gray"] as const) {
      expect(statusBadgeClasses(tone).length).toBeGreaterThan(0);
    }
  });
  it("green uses emerald classes", () => expect(statusBadgeClasses("green")).toContain("emerald"));
  it("red uses rose classes", () => expect(statusBadgeClasses("red")).toContain("rose"));
  it("amber uses amber classes", () => expect(statusBadgeClasses("amber")).toContain("amber"));
});

// -------------------------------------------------------------------------------------
// normalizeCitationStatus
// -------------------------------------------------------------------------------------

describe("normalizeCitationStatus", () => {
  it("maps verified on a verified answer", () =>
    expect(normalizeCitationStatus("verified", "answered_verified")).toBe("verified"));

  it("maps stale on an unverified answer", () =>
    expect(normalizeCitationStatus("stale", "answered_unverified")).toBe("stale"));

  it("maps invalid explicitly", () =>
    expect(normalizeCitationStatus("invalid", "answered_unverified")).toBe("invalid"));

  it("treats null status on a legacy answer as legacy_unverified", () =>
    expect(normalizeCitationStatus(null, "legacy")).toBe("legacy_unverified"));

  it("treats undefined status on a legacy answer as legacy_unverified", () =>
    expect(normalizeCitationStatus(undefined, "legacy")).toBe("legacy_unverified"));

  it("overrides to legacy_unverified when the answer itself is legacy, regardless of citation status", () => {
    expect(normalizeCitationStatus("verified", "legacy")).toBe("legacy_unverified");
    expect(normalizeCitationStatus("stale", "legacy")).toBe("legacy_unverified");
  });

  it("unknown citation status on a non-legacy answer falls back to legacy_unverified", () =>
    expect(normalizeCitationStatus("mystery", "answered_verified")).toBe("legacy_unverified"));
});

// -------------------------------------------------------------------------------------
// isCitationClickable
// -------------------------------------------------------------------------------------

describe("isCitationClickable", () => {
  const clickable: CitationStatus[] = ["verified", "stale", "legacy_unverified"];
  const notClickable: CitationStatus[] = ["invalid"];

  for (const s of clickable) {
    it(`${s} is clickable`, () => expect(isCitationClickable(s)).toBe(true));
  }
  for (const s of notClickable) {
    it(`${s} is NOT clickable`, () => expect(isCitationClickable(s)).toBe(false));
  }
});

// -------------------------------------------------------------------------------------
// citationsHeading
// -------------------------------------------------------------------------------------

describe("citationsHeading", () => {
  it("says VERIFIED CITATIONS for answered_verified", () =>
    expect(citationsHeading("answered_verified")).toContain("VERIFIED"));

  it("says not all verified for answered_unverified", () =>
    expect(citationsHeading("answered_unverified").toLowerCase()).toContain("not all verified"));

  it("says legacy unverified for legacy", () =>
    expect(citationsHeading("legacy").toLowerCase()).toContain("legacy"));

  it("says FILES MENTIONED for loading/error/unavailable", () => {
    expect(citationsHeading("loading")).toBe("FILES MENTIONED");
    expect(citationsHeading("error")).toBe("FILES MENTIONED");
    expect(citationsHeading("unavailable")).toBe("FILES MENTIONED");
  });
});

// -------------------------------------------------------------------------------------
// citationDisplay
// -------------------------------------------------------------------------------------

describe("citationDisplay", () => {
  it("verified citation: green, clickable, shows checkmark", () => {
    const d = citationDisplay("verified", "answered_verified");
    expect(d.status).toBe("verified");
    expect(d.clickable).toBe(true);
    expect(d.classes).toContain("emerald");
    expect(d.label).toContain("verified");
  });

  it("stale citation: amber, clickable, shows warning", () => {
    const d = citationDisplay("stale", "answered_unverified");
    expect(d.status).toBe("stale");
    expect(d.clickable).toBe(true);
    expect(d.classes).toContain("amber");
    expect(d.label).toContain("stale");
  });

  it("invalid citation: not clickable, struck through, line-through class", () => {
    const d = citationDisplay("invalid", "answered_unverified");
    expect(d.status).toBe("invalid");
    expect(d.clickable).toBe(false);
    expect(d.classes).toContain("line-through");
    expect(d.classes).toContain("cursor-not-allowed");
  });

  it("legacy citation: clickable, gray, shows unverified", () => {
    const d = citationDisplay(null, "legacy");
    expect(d.status).toBe("legacy_unverified");
    expect(d.clickable).toBe(true);
    expect(d.label).toContain("unverified");
  });

  it("missing citation status on a non-legacy answer: treated as unverified", () => {
    const d = citationDisplay(undefined, "answered_verified");
    expect(d.status).toBe("legacy_unverified");
    expect(d.clickable).toBe(true);
  });

  it("does NOT infer answered_verified from verified citation status alone (backend decides)", () => {
    // Even if a citation says "verified", the answer status is what we respect
    const d = citationDisplay("verified", "answered_unverified");
    expect(d.status).toBe("verified"); // citation is verified
    // but status label is still answered_unverified (tested elsewhere)
  });
});

// -------------------------------------------------------------------------------------
// Malformed / missing grounding metadata
// -------------------------------------------------------------------------------------

describe("malformed or missing grounding metadata", () => {
  it("null status → legacy, null citation → legacy_unverified", () => {
    expect(normalizeStatus(null)).toBe("legacy");
    expect(normalizeCitationStatus(null, "legacy")).toBe("legacy_unverified");
  });

  it("empty object-like status falls back to legacy", () => {
    expect(normalizeStatus("" as unknown as string)).toBe("legacy");
  });

  it("unknown answer status treats all citations as legacy_unverified", () => {
    const s = normalizeStatus("completely_unknown");
    expect(s).toBe("legacy");
    const cd = citationDisplay("verified", s);
    expect(cd.status).toBe("legacy_unverified");
  });
});
