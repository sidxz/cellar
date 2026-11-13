/** A temperature window's results as grid rows and ΔTm-against-concentration
 *  series. Pure. */

import type { MeltWindow, MeltingStep, StepCheck, WellType } from "../types";
import { WELL_TYPE_LABELS } from "../types";
import type { CurvePosition } from "./curve-plot";

export interface WindowRow {
  wellId: string;
  position: string;
  role: string;
  batch: string;
  concentration: number | null;
  tm: number | null;
  deltaTm: number | null;
  flags: string;
}

const FLAG_TEXT: Record<string, string> = {
  no_step_in_window: "No step in window",
  several_steps_in_window: "Several steps in window",
  no_reference_value: "No reference value",
};
const DIFFERS_TEXT = "Step count differs from the reference";

export function windowRows(
  window: MeltWindow,
  positions: CurvePosition[],
  checks: StepCheck[],
): WindowRow[] {
  const byId = new Map(positions.map((p) => [p.well_id, p]));
  const differs = new Set(
    checks.filter((c) => c.channel_key === window.channel_key).flatMap((c) => c.differs),
  );
  return window.positions.flatMap((r) => {
    const p = byId.get(r.well_id);
    if (!p) return [];
    const flags = r.flags.map((f) => FLAG_TEXT[f] ?? f);
    if (differs.has(r.well_id)) flags.push(DIFFERS_TEXT);
    return {
      wellId: r.well_id,
      position: p.label ?? p.position_label,
      role: WELL_TYPE_LABELS[p.well_type as WellType] ?? p.well_type,
      batch: p.batch_number ?? "",
      concentration: p.dose ?? null,
      tm: r.tm ?? null,
      deltaTm: r.delta_tm ?? null,
      flags: flags.join(", "),
    };
  });
}

export interface ConcentrationSeries {
  batchLabel: string;
  points: { dose: number; deltaTm: number }[];
}

/** One series per batch with at least two distinct doses above zero. */
export function concentrationSeries(
  window: MeltWindow,
  positions: CurvePosition[],
): ConcentrationSeries[] {
  const byId = new Map(positions.map((p) => [p.well_id, p]));
  const batches = new Map<string, { dose: number; deltaTm: number }[]>();
  for (const r of window.positions) {
    const p = byId.get(r.well_id);
    if (!p || r.delta_tm == null || p.dose == null || p.dose <= 0) continue;
    if (p.batch_number == null) continue;
    const key = p.batch_number;
    batches.set(key, [...(batches.get(key) ?? []), { dose: p.dose, deltaTm: r.delta_tm }]);
  }
  return [...batches]
    .filter(([, pts]) => new Set(pts.map((x) => x.dose)).size >= 2)
    .map(([batchLabel, pts]) => ({ batchLabel, points: pts.sort((a, b) => a.dose - b.dose) }));
}

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
  referenceLabels: string[];
  referenceTm: number | null;
  referenceCount: number;
  referencesDiffer: boolean;
  referenceUnreviewed: boolean;
  needsReview: number;
  provisional: number;
  up: number;
  down: number;
}

export type ResultFilter = "needs_review" | "provisional" | "up" | "down" | null;

/** Worst first; references sit outside this ranking. */
export const STATUS_ORDER: readonly CellStatus[] = [
  "several_steps",
  "no_step",
  "no_reference",
  "provisional",
  "reviewed",
];

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

function batchSuffix(p: CurvePosition): string | null {
  if (!p.batch_number) return null;
  const prefix = `${p.registration_number}-`;
  return p.registration_number && p.batch_number.startsWith(prefix)
    ? p.batch_number.slice(prefix.length)
    : p.batch_number;
}

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
      cells[w.window] = {
        tm: r.tm ?? null,
        deltaTm: r.delta_tm ?? null,
        status: cellStatus(p.well_type === "reference", r.flags, countingStep(w, p.well_id, steps)),
        differs,
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
      sampleText: p.registration_number || p.label || p.position_label,
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

export function matchesFilter(
  row: ResultRow,
  windowNames: readonly string[],
  filter: ResultFilter,
  threshold: number,
): boolean {
  if (filter === null) return true;
  if (!row.isSample) return false;
  const cells = cellsOf(row, windowNames);
  switch (filter) {
    case "needs_review":
      return cells.some((c) => c.status === "several_steps" || c.status === "no_step");
    case "provisional":
      return cells.some((c) => c.status === "provisional");
    case "up":
      return cells.some((c) => c.deltaTm != null && c.deltaTm >= threshold);
    case "down":
      return cells.some((c) => c.deltaTm != null && c.deltaTm <= -threshold);
  }
}

export function windowSummary(
  window: MeltWindow,
  rows: readonly ResultRow[],
  positions: readonly CurvePosition[],
  steps: readonly MeltingStep[],
  checks: readonly StepCheck[],
  threshold: number,
): WindowSummary {
  const inWindow = new Set(window.positions.map((r) => r.well_id));
  const refs = positions.filter((p) => p.well_type === "reference" && inWindow.has(p.well_id));
  const cells = rows.filter((r) => r.isSample).flatMap((r) => cellsOf(r, [window.window]));
  const n = (f: (c: WindowCell) => boolean) => cells.filter(f).length;
  return {
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
    up: n((c) => c.deltaTm != null && c.deltaTm >= threshold),
    down: n((c) => c.deltaTm != null && c.deltaTm <= -threshold),
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
}

/** Sample points of one batch; [] unless at least two distinct doses above zero. */
export function batchSeries(
  window: MeltWindow,
  positions: readonly CurvePosition[],
  batchId: string,
): SeriesPoint[] {
  const byId = new Map(positions.map((p) => [p.well_id, p]));
  const pts = window.positions
    .flatMap((r) => {
      const p = byId.get(r.well_id);
      if (!p || p.well_type !== "sample" || p.batch_id !== batchId) return [];
      if (r.delta_tm == null || p.dose == null || p.dose <= 0) return [];
      return [{ wellId: r.well_id, dose: p.dose, deltaTm: r.delta_tm }];
    })
    .sort((a, b) => a.dose - b.dose);
  return new Set(pts.map((x) => x.dose)).size >= 2 ? pts : [];
}
