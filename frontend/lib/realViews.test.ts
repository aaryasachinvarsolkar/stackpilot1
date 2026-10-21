import { describe, expect, it, vi } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { ChangeFlow } from "@/lib/useChangeFlow";
import type { ChangeProposal, ImpactReport } from "@/lib/api";
import { RealImpactView } from "@/components/RealImpactView";
import { RealPreviewView } from "@/components/RealPreviewView";

// The two tabs for REAL projects, rendered with a stub flow in each state. This checks they do not crash and that what
// the backend returned is what the user sees (and that nothing claims a file was written before it was).

const IMPACT: ImpactReport = {
  status: "analyzed",
  summary: "A toggle needs a button, a handler and dark colours.",
  risk: "medium",
  risk_reasons: ["Global CSS variables may affect other components"],
  affected_files: [
    { path: "frontend/app.js", category: "direct", why: "holds the handlers", editable: true, not_editable_reason: null },
    { path: "frontend/style.css", category: "indirect", why: "colours", editable: false, not_editable_reason: "Contains values that look like secrets; edits to it are not allowed." },
  ],
  plan: [
    { id: 1, action: "modify", path: "frontend/app.js", what: "add toggleDarkMode()" },
    { id: 2, action: "create", path: "frontend/theme.js", what: "store the choice" },
  ],
  skipped_steps: [{ path: ".env", reason: "never created" }],
  questions: ["Remember the choice between visits?"],
  excerpts_used: 4,
};

const PROPOSAL: ChangeProposal = {
  proposal_id: "p1",
  status: "proposed",
  summary: "Adds a dark mode toggle",
  files: [
    { path: "frontend/app.js", is_new: false, explanation: "adds the handler", diff: "--- a/frontend/app.js\n+++ b/frontend/app.js\n@@ -1,2 +1,3 @@\n a\n+function toggleDarkMode() {}\n b", added: 1, removed: 0 },
    { path: "frontend/theme.js", is_new: true, explanation: "new file", diff: "--- /dev/null\n+++ b/frontend/theme.js\n@@ -0,0 +1 @@\n+export {}", added: 1, removed: 0 },
  ],
  rejected: [{ path: "frontend/style.css", reason: "Edit 1 does not match the file's text." }],
};

function flow(over: Partial<ChangeFlow> = {}): ChangeFlow {
  const noop = vi.fn();
  const none = vi.fn(async () => false);
  return {
    projectId: "p", stage: "describe", setStage: noop, request: "", setRequest: noop, notes: "", setNotes: noop,
    busy: null, error: null, impact: null, chosen: new Set<string>(), proposal: null, approved: new Set<string>(),
    applied: [], reverted: false, toggleChosen: noop, toggleApproved: noop, reset: noop,
    runAnalyze: none, runPropose: none, runApply: none, runRevert: none, ...over,
  } as unknown as ChangeFlow;
}

const impactHtml = (f: ChangeFlow, canSend = true) =>
  renderToStaticMarkup(React.createElement(RealImpactView, { flow: f, canSend, onOpenFile: vi.fn(), onShowGraph: vi.fn(), onShowPreview: vi.fn() }));
const previewHtml = (f: ChangeFlow) =>
  renderToStaticMarkup(React.createElement(RealPreviewView, { flow: f, onOpenFile: vi.fn(), onGoToImpact: vi.fn() }));

describe("Impact Analysis tab for a real project", () => {
  it("starts with a request box and an honest empty state, not the sample scenario", () => {
    const html = impactHtml(flow());
    expect(html).toContain('data-testid="real-impact"');
    expect(html).toContain('data-testid="impact-request"');
    expect(html).toContain('data-testid="impact-empty"');
    expect(html).not.toMatch(/orders-platform|Sample scenario/i);
  });

  it("explains why it cannot run when no model is connected, and disables the button", () => {
    const html = impactHtml(flow({ request: "x" }), false);
    expect(html).toContain('data-testid="impact-blocked"');
    expect(html).toMatch(/<button[^>]*disabled[^>]*data-testid="impact-analyze"|data-testid="impact-analyze"[^>]*disabled/);
  });

  it("shows the risk, the plan with new-file marks, the affected files and the dropped steps from the backend", () => {
    const html = impactHtml(flow({ stage: "impact", request: "add dark mode", impact: IMPACT, chosen: new Set(["frontend/app.js", "frontend/theme.js"]) }));
    expect(html).toContain("medium risk");
    expect((html.match(/data-testid="plan-step"/g) ?? []).length).toBe(2);
    expect(html).toContain("new file");
    expect(html).toContain("frontend/theme.js");
    expect(html).toContain("holds the handlers");
    expect(html).toContain("Contains values that look like secrets");
    expect(html).toContain("1 suggested step(s) were dropped");
    expect(html).toContain("Remember the choice between visits?");
    expect(html).toContain("Approve plan and preview the modification (2)");
    expect(html).toContain("Still nothing is written");
  });

  it("disables the approve button when no step is ticked", () => {
    const html = impactHtml(flow({ stage: "impact", request: "x", impact: IMPACT, chosen: new Set<string>() }));
    expect(html).toMatch(/disabled=""[^>]*data-testid="impact-prepare"|data-testid="impact-prepare"[^>]*disabled=""/);
  });

  it("shows a failure from the backend instead of an empty report", () => {
    const html = impactHtml(flow({ error: "The groq model could not answer: groq answered HTTP 429. Rate limit reached; try again in about 59s." }));
    expect(html).toContain('data-testid="impact-error"');
    expect(html).toContain("Rate limit reached");
  });

  it("offers a way to the already prepared edits", () => {
    const html = impactHtml(flow({ stage: "review", request: "x", impact: IMPACT, proposal: PROPOSAL, chosen: new Set(["frontend/app.js"]) }));
    expect(html).toContain('data-testid="impact-go-preview"');
  });
});

describe("Modification Preview tab for a real project", () => {
  it("says nothing is prepared and points back to Impact Analysis", () => {
    const html = previewHtml(flow());
    expect(html).toContain('data-testid="preview-needs-plan"');
    expect(html).toContain('data-testid="preview-go-impact"');
    expect(html).not.toContain('data-testid="real-preview"');
  });

  it("lists every prepared file with its counts, shows the first diff and says it is only a preview", () => {
    const html = previewHtml(flow({ stage: "review", proposal: PROPOSAL, approved: new Set(["frontend/app.js", "frontend/theme.js"]) }));
    expect(html).toContain('data-testid="real-preview"');
    expect((html.match(/data-testid="preview-file"/g) ?? []).length).toBe(2);
    expect(html).toContain("+function toggleDarkMode() {}");
    expect(html).toContain("this is only a preview");
    expect(html).toContain("Apply 2 approved files");
    expect(html).toContain('data-testid="preview-rejected"');
    expect(html).toContain("does not match the file&#x27;s text");
  });

  it("cannot apply with nothing ticked", () => {
    const html = previewHtml(flow({ stage: "review", proposal: PROPOSAL, approved: new Set<string>() }));
    expect(html).toMatch(/disabled=""[^>]*data-testid="preview-apply"|data-testid="preview-apply"[^>]*disabled=""/);
  });

  it("after applying, offers undo and the written files, and no longer offers apply", () => {
    const html = previewHtml(flow({ stage: "done", proposal: PROPOSAL, applied: ["frontend/app.js"] }));
    expect(html).toContain("Applied to disk.");
    expect(html).toContain('data-testid="preview-revert"');
    expect(html).not.toContain('data-testid="preview-apply"');
  });

  it("after undo, says the original files are back", () => {
    const html = previewHtml(flow({ stage: "done", proposal: PROPOSAL, applied: ["frontend/app.js"], reverted: true }));
    expect(html).toContain("the original files are back");
    expect(html).not.toContain('data-testid="preview-revert"');
  });

  it("renders diff text as plain text, never as HTML", () => {
    const evil: ChangeProposal = { ...PROPOSAL, files: [{ ...PROPOSAL.files[0], diff: "+<img src=x onerror=alert(1)>" }] };
    const html = previewHtml(flow({ stage: "review", proposal: evil, approved: new Set(["frontend/app.js"]) }));
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});
