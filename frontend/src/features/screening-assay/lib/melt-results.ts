/** A temperature window's results as grid rows and ΔTm-against-concentration
 *  series. Pure. */

import type { MeltWindow, MeltingStep, StepCheck } from "../types";
import type { CurvePosition } from "./curve-plot";

// ---- Results table derivations (Traces tab) ----

export type CellStatus =
  | "reference"
  | "several_steps"
  | "no_step"
  | "no_reference"
  | "provisional"
  | "reviewed";

export interface WindowCell {
  tm: number | null;
  deltaTm: number | null;
  status: CellStatus;
  differs: boolean;
  /** The counting step's review; null without one. */
  review: "reviewed" | "provisional" | null;
}

export interface SampleIdentity {
  registrationNumber: string | null;
  moleculeId: string | null;
  batchSuffix: string | null;
  label: string | null;
  smiles: string | null;
}

export interface ResultRow {
  wellId: string;
  position: string;
  wellType: string;
  isSample: boolean;
  batchId: string | null;
  identity: SampleIdentity;
  sampleText: string;
  concentration: number | null;
  cells: Record<string, WindowCell>;
}

export interface WindowSummary {
  window: string;
  referenceLabels: string[];
  referenceTm: number | null;
  referenceCount: number;
  referencesDiffer: boolean;
  referenceUnreviewed: boolean;
  needsReview: number;
  provisional: number;
  /** Samples the run's hit rule calls hits; up/down split them by ΔTm sign. */
  hits: number;
  up: number;
  down: number;
}

export type ResultFilter = "needs_review" | "provisional" | "hits" | "up" | "down" | null;

/** Worst first; references sit outside this ranking. */
export const STATUS_ORDER: readonly CellStatus[] = [
  "several_steps",
  "no_step",
  "no_reference",
  "provisional",
  "reviewed",
];

/** A hit's direction: the sign of its ΔTm in the shown windows. */
function hitSign(cells: readonly WindowCell[], sign: "up" | "down"): boolean {
  return cells.some((c) => c.deltaTm != null && (sign === "up" ? c.deltaTm > 0 : c.deltaTm < 0));
}

/** The step that gives a position its Tm in a window: non-rejected, on the
 *  window's channel, inside the window. */
function countingStep(
  window: MeltWindow,
  wellId: string,
  steps: readonly MeltingStep[],
): MeltingStep | undefined {
  return steps.find(
    (s) =>
      s.well_id === wellId &&
      s.channel_key === window.channel_key &&
      s.status !== "rejected" &&
      s.value >= window.low &&
      s.value <= window.high,
  );
}

/** The batch number without its registration-number prefix (`001`). */
export function batchSuffix(p: CurvePosition): string | null {
  if (!p.batch_number) return null;
  const prefix = `${p.registration_number}-`;
  return p.registration_number && p.batch_number.startsWith(prefix)
    ? p.batch_number.slice(prefix.length)
    : p.batch_number;
}

/** Registration number, else label, else position. */
export const sampleTextOf = (p: CurvePosition): string =>
  p.registration_number || p.label || p.position_label;

function cellStatus(
  isReference: boolean,
  flags: readonly string[],
  counting: MeltingStep | undefined,
): CellStatus {
  if (isReference) return "reference";
  if (flags.includes("several_steps_in_window")) return "several_steps";
  if (flags.includes("no_step_in_window")) return "no_step";
  if (flags.includes("no_reference_value")) return "no_reference";
  return counting?.status === "unreviewed" ? "provisional" : "reviewed";
}

/** One row per position, in `positions` order, whether or not any window
 *  lists it (the grid doubles as the position picker). A window a position is
 *  missing from simply has no entry in `cells`. */
export function resultRows(
  windows: readonly MeltWindow[],
  positions: readonly CurvePosition[],
  steps: readonly MeltingStep[],
  checks: readonly StepCheck[],
): ResultRow[] {
  return positions.flatMap((p) => {
    const cells: Record<string, WindowCell> = {};
    for (const w of windows) {
      const r = w.positions.find((x) => x.well_id === p.well_id);
      if (!r) continue;
      const differs = checks.some(
        (c) => c.channel_key === w.channel_key && c.differs.includes(p.well_id),
      );
      const counting = countingStep(w, p.well_id, steps);
      cells[w.window] = {
        tm: r.tm ?? null,
        deltaTm: r.delta_tm ?? null,
        status: cellStatus(p.well_type === "reference", r.flags, counting),
        differs,
        review: counting ? (counting.status === "unreviewed" ? "provisional" : "reviewed") : null,
      };
    }
    return {
      wellId: p.well_id,
      position: p.position_label,
      wellType: p.well_type,
      isSample: p.well_type === "sample",
      batchId: p.batch_id ?? null,
      identity: {
        registrationNumber: p.registration_number || null,
        moleculeId: p.molecule_id ?? null,
        batchSuffix: batchSuffix(p),
        label: p.label ?? null,
        smiles: p.smiles ?? null,
      },
      sampleText: sampleTextOf(p),
      concentration: p.dose ?? null,
      cells,
    };
  });
}

const cellsOf = (row: ResultRow, names: readonly string[]) =>
  names.flatMap((n) => (row.cells[n] ? [row.cells[n]] : []));

/** Worst status across the given windows; null when the row has no cell in
 *  any of them (nothing to report). */
export function worstStatus(row: ResultRow, windowNames: readonly string[]): CellStatus | null {
  const cells = cellsOf(row, windowNames);
  if (cells.some((c) => c.status === "reference")) return "reference";
  return STATUS_ORDER.find((s) => cells.some((c) => c.status === s)) ?? null;
}

export function maxAbsDelta(row: ResultRow, windowNames: readonly string[]): number | null {
  const ds = cellsOf(row, windowNames).flatMap((c) =>
    c.deltaTm == null ? [] : [Math.abs(c.deltaTm)],
  );
  return ds.length ? Math.max(...ds) : null;
}

/** References pinned; samples by largest |ΔTm| (nulls last); then the rest. */
export function orderRows(
  rows: readonly ResultRow[],
  windowNames: readonly string[],
): { pinned: ResultRow[]; body: ResultRow[] } {
  const pinned = rows.filter((r) => r.wellType === "reference");
  const samples = rows
    .filter((r) => r.isSample)
    .map((r) => ({ r, d: maxAbsDelta(r, windowNames) }))
    .sort((a, b) => (a.d === null ? 1 : 0) - (b.d === null ? 1 : 0) || (b.d ?? 0) - (a.d ?? 0))
    .map((x) => x.r);
  const rest = rows.filter((r) => !r.isSample && r.wellType !== "reference");
  return { pinned, body: [...samples, ...rest] };
}

/** The row to select when the results open: the first sample needing review
 *  (several steps or no step), else the largest |ΔTm|, else the first sample,
 *  else the first position. Grid order, so the pick is the row seen first. */
export function firstToSelect(
  rows: readonly ResultRow[],
  windowNames: readonly string[],
): string | null {
  const { body } = orderRows(rows, windowNames);
  const review = body.find((r) => {
    const s = r.isSample ? worstStatus(r, windowNames) : null;
    return s === "several_steps" || s === "no_step";
  });
  // Samples lead the body, largest |ΔTm| first, then the rest in position order.
  return (review ?? body.find((r) => r.isSample) ?? rows[0])?.wellId ?? null;
}

export function matchesFilter(
  row: ResultRow,
  windowNames: readonly string[],
  filter: ResultFilter,
  hits: ReadonlySet<string>,
): boolean {
  if (filter === null) return true;
  if (!row.isSample) return false;
  const cells = cellsOf(row, windowNames);
  switch (filter) {
    case "needs_review":
      return cells.some((c) => c.status === "several_steps" || c.status === "no_step");
    case "provisional":
      return cells.some((c) => c.status === "provisional");
    case "hits":
      return hits.has(row.wellId);
    case "up":
    case "down":
      return hits.has(row.wellId) && hitSign(cells, filter);
  }
}

export function windowSummary(
  window: MeltWindow,
  rows: readonly ResultRow[],
  positions: readonly CurvePosition[],
  steps: readonly MeltingStep[],
  checks: readonly StepCheck[],
  hits: ReadonlySet<string>,
): WindowSummary {
  const inWindow = new Set(window.positions.map((r) => r.well_id));
  const refs = positions.filter((p) => p.well_type === "reference" && inWindow.has(p.well_id));
  const samples = rows.filter((r) => r.isSample);
  const cells = samples.flatMap((r) => cellsOf(r, [window.window]));
  const n = (f: (c: WindowCell) => boolean) => cells.filter(f).length;
  const hitRows = samples.filter((r) => hits.has(r.wellId));
  const signed = (sign: "up" | "down") =>
    hitRows.filter((r) => hitSign(cellsOf(r, [window.window]), sign)).length;
  return {
    window: window.window,
    referenceLabels: refs.map((p) => p.label ?? p.position_label),
    referenceTm: window.reference_tm ?? null,
    referenceCount: window.reference_count,
    referencesDiffer: checks.some(
      (c) => c.channel_key === window.channel_key && c.references_differ,
    ),
    referenceUnreviewed: refs.some(
      (p) => countingStep(window, p.well_id, steps)?.status === "unreviewed",
    ),
    needsReview: n((c) => c.status === "several_steps" || c.status === "no_step"),
    provisional: n((c) => c.status === "provisional"),
    hits: hitRows.length,
    up: signed("up"),
    down: signed("down"),
  };
}

export interface ShiftRow {
  wellId: string;
  label: string;
  deltaTm: number;
}

/** Samples with a ΔTm, ascending; duplicate sample texts get the position appended. */
export function shiftRows(rows: readonly ResultRow[], windowName: string): ShiftRow[] {
  const have = rows.filter((r) => r.isSample && r.cells[windowName]?.deltaTm != null);
  const counts = new Map<string, number>();
  for (const r of have) counts.set(r.sampleText, (counts.get(r.sampleText) ?? 0) + 1);
  return have
    .map((r) => ({
      wellId: r.wellId,
      label: (counts.get(r.sampleText) ?? 0) > 1 ? `${r.sampleText} · ${r.position}` : r.sampleText,
      deltaTm: r.cells[windowName].deltaTm as number,
    }))
    .sort((a, b) => a.deltaTm - b.deltaTm);
}

export interface SeriesPoint {
  wellId: string;
  dose: number;
  deltaTm: number;
  /** The counting step is unreviewed. */
  provisional: boolean;
}

/** Sample points of one batch; [] unless at least two distinct doses above zero. */
export function batchSeries(
  window: MeltWindow,
  positions: readonly CurvePosition[],
  batchId: string,
  steps: readonly MeltingStep[],
): SeriesPoint[] {
  const byId = new Map(positions.map((p) => [p.well_id, p]));
  const pts = window.positions
    .flatMap((r) => {
      const p = byId.get(r.well_id);
      if (!p || p.well_type !== "sample" || p.batch_id !== batchId) return [];
      if (r.delta_tm == null || p.dose == null || p.dose <= 0) return [];
      const provisional = countingStep(window, r.well_id, steps)?.status === "unreviewed";
      return [{ wellId: r.well_id, dose: p.dose, deltaTm: r.delta_tm, provisional }];
    })
    .sort((a, b) => a.dose - b.dose);
  return new Set(pts.map((x) => x.dose)).size >= 2 ? pts : [];
}

/** Distinct doses above zero at which the run tests a batch's samples. */
export function batchDoseCount(positions: readonly CurvePosition[], batchId: string): number {
  return new Set(
    positions
      .filter((p) => p.well_type === "sample" && p.batch_id === batchId && (p.dose ?? 0) > 0)
      .map((p) => p.dose),
  ).size;
}
