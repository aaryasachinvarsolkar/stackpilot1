// Guards against false claims creeping back into the UI. This reads the component source as text, so it
// is a regression tripwire, not a rendering test: it fails if a phrase that claimed something which does
// not exist (an executed plan, a sandbox run, a git push, indexing, "grounded" analysis) reappears.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (rel: string) => readFileSync(new URL(`../${rel}`, import.meta.url), "utf-8");

const PANEL = read("chat/AICopilotPanel.tsx");
const DIALOG = read("components/CreateProjectDialog.tsx");
const PAGE = read("app/page.tsx");
const WORKSPACE = read("components/WorkspaceView.tsx");
const GRAPH = read("components/RealProjectGraph.tsx");
const UI_FILES: Record<string, string> = {
  "chat/AICopilotPanel.tsx": PANEL,
  "components/CreateProjectDialog.tsx": DIALOG,
  "app/page.tsx": PAGE,
  "components/WorkspaceView.tsx": WORKSPACE,
  "components/RealProjectGraph.tsx": GRAPH,
};

// Each of these was shown to users although the feature behind it does not exist.
const FALSE_CLAIMS = [
  "Approve Plan",
  "Plan approved",
  "REQUIRES APPROVAL",
  "Execute plan",
  "executed in sandbox",
  "git push origin",
  "Allow Action",
  "AST+RAG",
  "Codebase Grounded",
  "GROUNDED",
  "ANALYSIS READY",
  "Security Advisory",
  "indexed and ready",
  "indexed and verified",
  "Processing & Indexing",
  "Upload & Inspect",
  "Import & Inspect",
  "Modules Indexed",
  "Agent generating",
  "Fallback intelligent reasoning",
];

describe("no claims about features that do not exist", () => {
  for (const [file, source] of Object.entries(UI_FILES)) {
    it(`${file} contains none of the known false claims`, () => {
      const found = FALSE_CLAIMS.filter((phrase) => source.includes(phrase));
      expect(found).toEqual([]);
    });
  }

  it("the copilot never renders a step as done (no checkmark, no struck-through steps)", () => {
    expect(PANEL).not.toContain("✓");
    expect(PANEL).not.toContain("line-through");
    expect(PANEL).not.toMatch(/status\s*===\s*["']completed["']/);
  });

  it("no scripted data in the copilot marks a step as completed or running", () => {
    expect(PANEL).not.toMatch(/status:\s*["'](completed|running)["']/);
  });

  it("the copilot has no button that pretends to approve, execute, push or stop anything", () => {
    expect(PANEL).not.toMatch(/handleApprovePlan|setPlanApproved|setApprovalStatus/);
    expect(PANEL).not.toMatch(/<Square|Stop<\/|> Stop/);
  });
});

describe("unfinished features say so", () => {
  it("the copilot lists what is not available yet", () => {
    expect(PANEL.toLowerCase()).toContain("not available yet");
    for (const feature of ["sandbox", "git commit and push"]) {
      expect(PANEL.toLowerCase()).toContain(feature);
    }
  });

  it("guided changes write nothing before the user approves, and say so at each step", () => {
    const ASSISTANT = read("chat/ChangeAssistant.tsx");
    const IMPACT = read("components/RealImpactView.tsx");
    const PREVIEW = read("components/RealPreviewView.tsx");
    const FLOW = read("lib/useChangeFlow.ts");
    expect(PANEL).toContain("ChangeAssistant");
    expect(ASSISTANT).toContain("Nothing is changed in this step");
    expect(ASSISTANT).toContain("Still nothing is written");
    expect(IMPACT).toContain("Nothing is changed in this step");
    expect(IMPACT).toContain("Still nothing is written");
    expect(PREVIEW).toContain("this is only a preview");
    // the only call that writes files is in the shared flow, and it sends just the files the user ticked
    expect(FLOW.match(/applyChange\(/g)).toHaveLength(1);
    expect(FLOW).toMatch(/applyChange\(projectId, proposal\.proposal_id, Array\.from\(approved\)\)/);
    // ...and it is only reachable from an explicit Apply button
    for (const view of [ASSISTANT, PREVIEW]) expect(view).toMatch(/onClick=\{\(\) => void runApply\(\)\}/);
    for (const view of [IMPACT]) expect(view).not.toContain("runApply");
  });

  it("the review tab says it is not available yet instead of showing findings", () => {
    expect(PANEL).toContain("review-not-available");
    expect(PANEL).not.toMatch(/Architecture & Maintainability|Clean modular structure/);
  });

  it("the copilot says project files are not indexed", () => {
    expect(PANEL).toContain("not indexed yet");
  });

  it("the sample project's replies are labelled as scripted", () => {
    expect(PANEL).toContain("SCRIPTED SAMPLE");
    expect(PANEL).toContain("scripted");
  });

  it("a failed chat request is shown as a failure, never replaced by an invented reply", () => {
    expect(PANEL).toContain("The request failed");
    expect(PANEL).not.toMatch(/fallback-\$\{/);
  });

  it("the dependency graph for real projects is labelled as a heuristic", () => {
    expect(GRAPH).toContain("HEURISTIC");
  });
});
