/**
 * The labelling table's neutral row model and its pure rules, shared by the
 * instrument import wizard and Edit labelling.
 */

import type { WellType } from "../types";

const MAX_LABEL = 200;
const MAX_NOTE = 1000;

export interface LabellingRow {
  /** The wizard: positionKey(row, column); Edit labelling: the well id. */
  key: string;
  positionLabel: string;
  used: boolean;
  label: string;
  note: string;
  wellType: WellType;
  moleculeId: string | null;
  moleculeName: string | null;
  batchId: string | null;
  /** Shown in place of the batch picker when the batch is read-only. */
  batchNumber?: string | null;
  /** Text while editing; parsed with {@link parseDose}. */
  dose: string;
}

/** A blank dose is null; anything else must be a non-negative number. */
export function parseDose(text: string): number | null | undefined {
  const t = text.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : undefined;
}

/** Why the rows cannot be stored yet, naming the first used row that holds an
 *  invalid value, or null when they can. */
export function rowsProblem(rows: readonly LabellingRow[]): string | null {
  for (const p of rows) {
    if (!p.used) continue;
    if (parseDose(p.dose) === undefined) {
      return `${p.positionLabel}: the concentration must be a number, 0 or more.`;
    }
    if (p.label.length > MAX_LABEL) {
      return `${p.positionLabel}: the label is longer than ${MAX_LABEL} characters.`;
    }
    if (p.note.length > MAX_NOTE) {
      return `${p.positionLabel}: the note is longer than ${MAX_NOTE} characters.`;
    }
  }
  return null;
}

export function setRoleForRows<T extends LabellingRow>(
  rows: readonly T[],
  keys: ReadonlySet<string>,
  wellType: WellType,
): T[] {
  return rows.map((r) => (keys.has(r.key) ? { ...r, wellType } : r));
}

/** Used rows with a compound chosen and no batch: stored without a compound. */
export function compoundWithoutBatch(rows: readonly LabellingRow[]): number {
  return rows.filter((r) => r.used && r.moleculeId && !r.batchId).length;
}

export function withoutBatchLine(count: number): string | null {
  if (count === 0) return null;
  return count === 1
    ? "1 position has a compound but no batch; it will be stored without a compound"
    : `${count} positions have a compound but no batch; they will be stored without a compound`;
}
