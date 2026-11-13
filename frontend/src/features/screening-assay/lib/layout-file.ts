/**
 * The labelling layout file, as pure functions: the template written from the
 * table, and a resolved file applied to the table. The Position text is the key.
 */

import Papa from "papaparse";

import { type LayoutFile, type LayoutFileRow, WELL_TYPE_LABELS, type WellType } from "../types";
import { type LabellingRow, parseDose } from "./labelling-rows";

/** Lets a spreadsheet program read the file as UTF-8. */
const BOM = "﻿";

const LOCKED_NOTICE =
  "Role, Compound, Batch and Concentration in the file were ignored: they can be changed only while the run is draft or in progress.";

export function layoutTemplateCsv(
  rows: readonly LabellingRow[],
  opts: { doseUnit: string; withUse: boolean },
): string {
  const fields = [
    "Position",
    "Label",
    "Role",
    "Compound",
    "Batch",
    `Concentration (${opts.doseUnit})`,
    "Note",
  ];
  if (opts.withUse) fields.push("Use");
  const data = rows.map((r) => {
    const line = [
      r.positionLabel,
      r.label,
      WELL_TYPE_LABELS[r.wellType],
      r.moleculeRef ?? "",
      r.batchNumber ?? "",
      r.dose,
      r.note,
    ];
    if (opts.withUse) line.push(r.used ? "Yes" : "No");
    return line;
  });
  return BOM + Papa.unparse({ fields, data });
}

export interface LayoutApplication<T extends LabellingRow> {
  rows: T[];
  /** Table rows that changed. */
  filled: number;
  /** One line each, naming the position by its Position text. */
  problems: string[];
  notices: string[];
}

export function applyLayout<T extends LabellingRow>(
  rows: readonly T[],
  file: LayoutFile,
  opts: { allowUse: boolean; calculatedLocked: boolean },
): LayoutApplication<T> {
  const problems: string[] = [];
  const notices: string[] = [];
  const known = new Set(rows.map((r) => r.positionLabel.trim()));
  const times = new Map<string, number>();
  for (const f of file.rows) {
    const p = f.position.trim();
    times.set(p, (times.get(p) ?? 0) + 1);
  }

  const toApply = new Map<string, LayoutFileRow>();
  const reported = new Set<string>();
  let lockedIgnored = false;
  for (const f of file.rows) {
    const p = f.position.trim();
    if (!p) {
      problems.push("A row with no Position was skipped");
      continue;
    }
    if ((times.get(p) ?? 0) > 1) {
      if (!reported.has(p)) problems.push(`${p}: appears more than once in the file; skipped`);
      reported.add(p);
      continue;
    }
    if (!known.has(p)) {
      problems.push(`${p}: not a position in this table; skipped`);
      continue;
    }
    for (const problem of f.problems) problems.push(`${p}: ${problem}`);
    if (!opts.allowUse && f.use === false) {
      problems.push(
        `${p}: positions cannot be removed here; reset the run and import again to leave one out`,
      );
      continue;
    }
    if (opts.calculatedLocked && (f.well_type != null || f.compound != null || f.dose != null)) {
      lockedIgnored = true;
    }
    toApply.set(p, f);
  }
  if (lockedIgnored) notices.push(LOCKED_NOTICE);
  if (file.unrecognised_columns.length > 0) {
    notices.push(`Columns not recognised and ignored: ${file.unrecognised_columns.join(", ")}`);
  }

  let filled = 0;
  const out = rows.map((r) => {
    const f = toApply.get(r.positionLabel.trim());
    if (!f) return r;
    const patch: Partial<LabellingRow> = {};
    if (f.label != null) patch.label = f.label;
    if (f.note != null) patch.note = f.note;
    if (opts.allowUse && f.use != null) patch.used = f.use;
    if (!opts.calculatedLocked) {
      if (f.well_type != null) patch.wellType = f.well_type as WellType;
      // Same number, same text: "10.0" stays as typed when the file says 10.
      if (f.dose != null && parseDose(r.dose) !== f.dose) patch.dose = String(f.dose);
      if (f.compound) {
        patch.moleculeId = f.compound.molecule_id;
        patch.moleculeName = f.compound.molecule_name;
        patch.moleculeRef = f.compound.registration_number;
        patch.batchId = f.compound.batch_id ?? null;
        patch.batchNumber = f.compound.batch_number ?? null;
      }
    }
    const keys = Object.keys(patch) as (keyof LabellingRow)[];
    if (!keys.some((k) => patch[k] !== r[k])) return r;
    filled += 1;
    return { ...r, ...patch };
  });
  return { rows: out, filled, problems, notices };
}
