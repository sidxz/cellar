"use client";

import { useReducer, useRef } from "react";
import type { DerivedSet, DerivedSpec } from "../lib/derived";

/** A derived column set and the job behind it: the compounds it runs over (fixed when it
 * starts, so the job hooks always see the same array), how it stands, and its columns once
 * ready. A set being recomputed keeps its last columns until the new ones arrive. Held by
 * the page, outside the workbench store: never part of undo history. */
export type DerivedEntry = {
  spec: DerivedSpec;
  moleculeIds: string[];
  status: "running" | "ready" | "failed" | "cancelled";
  set?: DerivedSet;
  error?: string;
  startedAt: number;
  attempt: number;
};

export type DerivedAction =
  | { type: "add"; spec: DerivedSpec; moleculeIds: string[] }
  | { type: "resolve"; id: string; set: DerivedSet }
  | { type: "fail"; id: string; message: string }
  | { type: "cancel"; id: string }
  | { type: "retry"; id: string }
  | { type: "recompute"; id: string; moleculeIds: string[] }
  | { type: "remove"; id: string };

const restart = (e: DerivedEntry, moleculeIds = e.moleculeIds): DerivedEntry => ({
  ...e,
  moleculeIds,
  status: "running",
  error: undefined,
  startedAt: Date.now(),
  attempt: e.attempt + 1,
});

function step(e: DerivedEntry, a: Exclude<DerivedAction, { type: "add" | "remove" }>) {
  const running = e.status === "running";
  switch (a.type) {
    case "resolve":
      return running ? { ...e, status: "ready" as const, set: a.set } : e;
    case "fail":
      return running ? { ...e, status: "failed" as const, error: a.message } : e;
    case "cancel":
      return running ? { ...e, status: "cancelled" as const } : e;
    case "retry":
      return running ? e : restart(e);
    case "recompute":
      return running ? e : restart(e, a.moleculeIds);
  }
}

/** Removing an R-groups set takes it out of the series built on it; a series left without
 * members goes too, otherwise it is recomputed. */
function remove(entries: DerivedEntry[], id: string): DerivedEntry[] {
  return entries.flatMap((e) => {
    if (e.spec.id === id) return [];
    if (e.spec.kind !== "series" || !e.spec.members.some((m) => m.rgroupsId === id)) return [e];
    const members = e.spec.members.filter((m) => m.rgroupsId !== id);
    return members.length ? [{ ...restart(e), spec: { ...e.spec, members } }] : [];
  });
}

export function derivedReducer(entries: DerivedEntry[], a: DerivedAction): DerivedEntry[] {
  if (a.type === "remove") return remove(entries, a.id);
  if (a.type === "add") {
    const at = entries.findIndex((e) => e.spec.id === a.spec.id);
    const entry: DerivedEntry = {
      spec: a.spec,
      moleculeIds: a.moleculeIds,
      status: "running",
      startedAt: Date.now(),
      // Counts every start under this id, so a replacement never reuses its runner.
      attempt: (entries[at]?.attempt ?? 0) + 1,
    };
    return at < 0 ? [...entries, entry] : entries.map((e, k) => (k === at ? entry : e));
  }
  const at = entries.findIndex((e) => e.spec.id === a.id);
  const next = at < 0 ? undefined : step(entries[at], a);
  return next === undefined || next === entries[at]
    ? entries
    : entries.map((e, k) => (k === at ? next : e));
}

/** The column sets on show: every entry that has columns (ready, or recomputing). */
export const setsOf = (entries: DerivedEntry[]): DerivedSet[] =>
  entries.flatMap((e) => (e.set ? [e.set] : []));

/** The workbench's derived column sets. */
export function useDerived(initial: DerivedEntry[] = []) {
  const [entries, dispatch] = useReducer(derivedReducer, initial);
  // The same array while the same sets show, so a job starting or failing does not rebuild
  // the dataset and redraw every plot.
  const shown = useRef<DerivedSet[]>([]);
  const sets = setsOf(entries);
  if (sets.length !== shown.current.length || sets.some((s, k) => s !== shown.current[k])) {
    shown.current = sets;
  }
  return { entries, readySets: shown.current, dispatch };
}
