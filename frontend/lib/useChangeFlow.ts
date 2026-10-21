"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  analyzeChange,
  applyChange,
  proposeChange,
  revertChange,
  type ChangeProposal,
  type ImpactReport,
} from "@/lib/api";

export type ChangeStage = "describe" | "impact" | "review" | "done";

/**
 * The whole guided-change flow (describe -> impact and plan -> review the edits -> applied), kept in ONE place so the
 * Agent panel, the Impact tab and the Modification Preview tab show the same thing and switching tabs loses nothing.
 * Nothing is written to a project file except by `runApply`, which sends only the files the user ticked.
 */
export function useChangeFlow(projectId: string | null, onFilesChanged?: (paths: string[]) => void) {
  const [stage, setStage] = useState<ChangeStage>("describe");
  const [request, setRequest] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [impact, setImpact] = useState<ImpactReport | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [proposal, setProposal] = useState<ChangeProposal | null>(null);
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [applied, setApplied] = useState<string[]>([]);
  const [reverted, setReverted] = useState(false);

  // A reply that arrives after the project changed or the flow was reset is ignored.
  const generation = useRef(0);
  const changedRef = useRef(onFilesChanged);
  changedRef.current = onFilesChanged;

  const reset = useCallback(() => {
    generation.current += 1;
    setStage("describe");
    setRequest("");
    setNotes("");
    setBusy(null);
    setError(null);
    setImpact(null);
    setChosen(new Set());
    setProposal(null);
    setApproved(new Set());
    setApplied([]);
    setReverted(false);
  }, []);

  useEffect(() => {
    reset();
  }, [projectId, reset]);

  const toggleIn = (set: Set<string>, setter: (s: Set<string>) => void, path: string) => {
    const next = new Set(set);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setter(next);
  };

  /** Find the files, the impact and a plan for `request`. Writes nothing. */
  const runAnalyze = async (): Promise<boolean> => {
    if (!projectId || !request.trim() || busy) return false;
    const mine = ++generation.current;
    setBusy("Finding the files involved and planning the change...");
    setError(null);
    const r = await analyzeChange(projectId, request.trim());
    if (mine !== generation.current) return false;
    setBusy(null);
    if (!r.ok || !r.data) {
      setError(r.message ?? "The analysis failed.");
      return false;
    }
    setImpact(r.data);
    setChosen(new Set(r.data.plan.map((st) => st.path)));
    setProposal(null);
    setStage("impact");
    return true;
  };

  /** Prepare exact edits for the approved plan steps. Writes nothing. */
  const runPropose = async (): Promise<boolean> => {
    if (!projectId || chosen.size === 0 || busy) return false;
    const mine = ++generation.current;
    setBusy("Writing the exact edits (one file at a time)...");
    setError(null);
    const steps = (impact?.plan ?? []).filter((st) => chosen.has(st.path));
    const r = await proposeChange(projectId, request.trim(), notes.trim(), steps);
    if (mine !== generation.current) return false;
    setBusy(null);
    if (!r.ok || !r.data) {
      setError(r.message ?? "No edits could be prepared.");
      return false;
    }
    setProposal(r.data);
    setApproved(new Set(r.data.files.map((f) => f.path)));
    setStage("review");
    return true;
  };

  /** Write ONLY the approved files of the proposal. */
  const runApply = async (): Promise<boolean> => {
    if (!projectId || !proposal || approved.size === 0 || busy) return false;
    const mine = ++generation.current;
    setBusy("Applying the approved files...");
    setError(null);
    const r = await applyChange(projectId, proposal.proposal_id, Array.from(approved));
    if (mine !== generation.current) return false;
    setBusy(null);
    if (!r.ok || !r.data) {
      setError(r.message ?? "Nothing was written.");
      return false;
    }
    setApplied(r.data.applied);
    setReverted(false);
    changedRef.current?.(r.data.applied);
    setStage("done");
    return true;
  };

  const runRevert = async (): Promise<boolean> => {
    if (!projectId || !proposal || busy) return false;
    const mine = ++generation.current;
    setBusy("Restoring the original files...");
    setError(null);
    const r = await revertChange(projectId, proposal.proposal_id);
    if (mine !== generation.current) return false;
    setBusy(null);
    if (!r.ok || !r.data) {
      setError(r.message ?? "Nothing was reverted.");
      return false;
    }
    setReverted(true);
    changedRef.current?.(r.data.reverted);
    return true;
  };

  return {
    projectId,
    stage, setStage,
    request, setRequest,
    notes, setNotes,
    busy, error,
    impact, chosen, proposal, approved, applied, reverted,
    toggleChosen: (path: string) => toggleIn(chosen, setChosen, path),
    toggleApproved: (path: string) => toggleIn(approved, setApproved, path),
    reset, runAnalyze, runPropose, runApply, runRevert,
  };
}

export type ChangeFlow = ReturnType<typeof useChangeFlow>;
