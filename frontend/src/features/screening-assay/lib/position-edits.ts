/**
 * Pure state for Edit labelling: the run's positions as labelling rows, and
 * the edits a save sends, each with the values the user started from.
 */

import type { PositionEdit, PositionValues, Run, RunCurves, WellType } from "../types";
import { holderOrder } from "./curve-selection";
import { type LabellingRow, parseDose } from "./labelling-rows";

type Position = RunCurves["positions"][number];

export function rowsFromPositions(positions: readonly Position[]): LabellingRow[] {
  return holderOrder(positions).map((p) => ({
    key: p.well_id,
    positionLabel: p.position_label,
    used: true,
    label: p.label ?? "",
    note: p.note ?? "",
    wellType: p.well_type as WellType,
    moleculeId: p.molecule_id ?? null,
    moleculeName: p.molecule_name ?? null,
    batchId: p.batch_id ?? null,
    batchNumber: p.batch_number ?? null,
    dose: p.dose == null ? "" : String(p.dose),
  }));
}

export function valuesOf(p: Position): PositionValues {
  return {
    label: p.label ?? "",
    note: p.note ?? "",
    well_type: p.well_type as WellType,
    batch_id: p.batch_id ?? null,
    dose: p.dose ?? null,
  };
}

// Blank and null are the same label or note.
const text = (s: string | null | undefined) => (s ?? "").trim();

function differs(a: PositionValues, b: PositionValues): boolean {
  return (
    text(a.label) !== text(b.label) ||
    text(a.note) !== text(b.note) ||
    a.well_type !== b.well_type ||
    (a.batch_id ?? null) !== (b.batch_id ?? null) ||
    (a.dose ?? null) !== (b.dose ?? null)
  );
}

/** One edit per row that differs from its position. A row with a compound and
 *  no batch sends no batch: it is stored without a compound. */
export function buildPositionEdits(
  positions: readonly Position[],
  rows: readonly LabellingRow[],
): PositionEdit[] {
  const byId = new Map(positions.map((p) => [p.well_id, p]));
  const edits: PositionEdit[] = [];
  for (const r of rows) {
    const p = byId.get(r.key);
    if (!p) continue;
    const expected = valuesOf(p);
    const next: PositionValues = {
      label: r.label,
      note: r.note,
      well_type: r.wellType,
      batch_id: r.batchId,
      dose: parseDose(r.dose) ?? null,
    };
    if (differs(expected, next)) edits.push({ well_id: r.key, expected, new: next });
  }
  return edits;
}

/** Why the run's labelling cannot be edited, or null when it can. */
export function labellingEditRefusal(run: Pick<Run, "is_locked">): string | null {
  return run.is_locked ? "The run is locked." : null;
}

/** Why role, compound, batch and concentration are read-only, or null when they are not. */
export function calculatedLockedReason(run: Pick<Run, "status">): string | null {
  return run.status === "draft" || run.status === "in_progress"
    ? null
    : "Role, compound, batch and concentration can be changed only while the run is draft or in progress.";
}

/** A label or note edit on a completed or approved run needs a reason. */
export function reasonRequired(run: Pick<Run, "status">): boolean {
  return run.status === "completed" || run.status === "approved";
}
