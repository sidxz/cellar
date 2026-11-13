/** Position selection in the curve viewer. Pure; ids are well ids. */

import type { CurveGroup, CurvePosition } from "./curve-plot";

export interface SelectionState {
  selected: ReadonlySet<string>;
  anchor: string | null;
}

export const EMPTY_SELECTION: SelectionState = { selected: new Set(), anchor: null };

/** Click one: only it. Shift: the inclusive range from the anchor in holder
 *  order (the anchor stays). Toggle (ctrl or cmd): add or remove it. */
export function applyClick(
  state: SelectionState,
  orderedIds: readonly string[],
  id: string,
  mods: { shift: boolean; toggle: boolean },
): SelectionState {
  if (mods.shift && state.anchor !== null) {
    const a = orderedIds.indexOf(state.anchor);
    const b = orderedIds.indexOf(id);
    if (a >= 0 && b >= 0) {
      const range = orderedIds.slice(Math.min(a, b), Math.max(a, b) + 1);
      return { selected: new Set(range), anchor: state.anchor };
    }
  }
  if (mods.toggle) {
    const next = new Set(state.selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return { selected: next, anchor: id };
  }
  return { selected: new Set([id]), anchor: id };
}

export function selectAll(orderedIds: readonly string[]): SelectionState {
  return { selected: new Set(orderedIds), anchor: null };
}

/** Positions in holder order: row (A before B before AA), then column. */
export function holderOrder<T extends { row: string; column: number }>(
  positions: readonly T[],
): T[] {
  return [...positions].sort(
    (a, b) => a.row.length - b.row.length || a.row.localeCompare(b.row) || a.column - b.column,
  );
}

/** Number of distinct colours; more selected positions than this and the
 *  distinct colour mode is off. */
export const COLOUR_SLOT_COUNT = 8;

/** A colour slot per selected position. A position keeps its slot while it
 *  stays selected; a newly selected one takes the lowest free slot, in holder
 *  order. More than COLOUR_SLOT_COUNT selected gives an empty map. */
export function assignColourSlots(
  previous: ReadonlyMap<string, number>,
  selectedInHolderOrder: readonly string[],
): Map<string, number> {
  const next = new Map<string, number>();
  if (selectedInHolderOrder.length > COLOUR_SLOT_COUNT) return next;
  for (const id of selectedInHolderOrder) {
    const slot = previous.get(id);
    if (slot !== undefined) next.set(id, slot);
  }
  const used = new Set(next.values());
  let free = 0;
  for (const id of selectedInHolderOrder) {
    if (next.has(id)) continue;
    while (used.has(free)) free++;
    next.set(id, free);
    used.add(free);
  }
  return next;
}

/** At most this many positions are drawn at once. */
export const MAX_DRAWN = 400;

/** The selected positions in group then holder order, then, with the switch
 *  on, every reference position of a group that has a selected position. */
export function drawnPositionIds(
  groups: readonly CurveGroup[],
  selected: ReadonlySet<string>,
  showReferences: boolean,
): string[] {
  const ids = groups
    .flatMap((g) => g.positions.map((p) => p.well_id))
    .filter((id) => selected.has(id));
  if (!showReferences) return ids;
  const seen = new Set(ids);
  for (const g of groups) {
    if (!g.positions.some((p) => selected.has(p.well_id))) continue;
    for (const p of g.positions) {
      if (p.well_type === "reference" && !seen.has(p.well_id)) {
        seen.add(p.well_id);
        ids.push(p.well_id);
      }
    }
  }
  return ids;
}

/** Case-insensitive: the text is in the label, compound name, batch number or
 *  note. Blank text matches everything. */
export function matchesFilter(p: CurvePosition, text: string): boolean {
  const t = text.trim().toLowerCase();
  if (!t) return true;
  return [p.label, p.molecule_name, p.batch_number, p.note].some((v) =>
    v?.toLowerCase().includes(t),
  );
}

/** At most this many positions per curve request. */
export const CURVES_PER_REQUEST = 100;

export function chunk<T>(items: readonly T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** At most this many runs at once on the protocol's Curves tab (also the
 *  number of colours, so colour by run always works). */
export const MAX_CURVE_RUNS = 8;

/** Removes a chosen run, or adds it while fewer than MAX_CURVE_RUNS are chosen. */
export function toggleRun(chosen: readonly string[], runId: string): string[] {
  if (chosen.includes(runId)) return chosen.filter((id) => id !== runId);
  return chosen.length < MAX_CURVE_RUNS ? [...chosen, runId] : [...chosen];
}

/** What "Compare curves" on the protocol's Runs tab will open: the selected
 *  runs that have curves, why it cannot (none, or more than MAX_CURVE_RUNS),
 *  and a note when some selected runs have no curves and are left out. */
export function compareCurvesChoice(
  selectedRunIds: readonly string[],
  runIdsWithCurves: ReadonlySet<string>,
): { runIds: string[]; disabledReason: string | null; note: string | null } {
  const runIds = selectedRunIds.filter((id) => runIdsWithCurves.has(id));
  const disabledReason =
    runIds.length === 0
      ? "Select runs that have traces"
      : runIds.length > MAX_CURVE_RUNS
        ? "At most 8 runs at once"
        : null;
  const note =
    runIds.length > 0 && runIds.length < selectedRunIds.length
      ? `${runIds.length} of the ${selectedRunIds.length} selected runs ${runIds.length === 1 ? "has" : "have"} traces`
      : null;
  return { runIds, disabledReason, note };
}
