/**
 * The labelling layout file, as pure functions: the template written from the
 * table, and a resolved file applied to the table. The Position text is the key.
 */

import Papa from "papaparse";

import type { PositionLabelMatchesResponse } from "@/shared/lib/api/model";
import { formatCount } from "@/shared/lib/format-number";
import { type LayoutFile, type LayoutFileRow, WELL_TYPE_LABELS, type WellType } from "../types";
import { type LabellingRow, MAX_LABEL, parseDose } from "./labelling-rows";

/** Lets a spreadsheet program read the file as UTF-8. */
const BOM = "﻿";

const LOCKED_NOTICE =
  "Role, Compound, Batch and Concentration in the file were ignored: they can be changed only while the run is draft or in progress.";

/** A cell starting with one of these is run as a formula by a spreadsheet program. */
const FORMULA_START = /^[=+\-@\t\r]/;

/** A cell as written: a leading apostrophe keeps it text. The server drops
 *  that apostrophe when it reads the file back. */
function asText(value: string): string {
  return FORMULA_START.test(value) ? `'${value}` : value;
}

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
      asText(r.positionLabel),
      asText(r.label),
      WELL_TYPE_LABELS[r.wellType],
      asText(r.moleculeRef ?? ""),
      asText(r.batchNumber ?? ""),
      asText(r.dose),
      asText(r.note),
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
        `${p}: positions cannot be removed here. For a draft or in-progress run, reset all run data and import again. Otherwise, import into a new run.`,
      );
      continue;
    }
    toApply.set(p, f);
  }
  // The server tells: only it saw the cells, including ones it could not read.
  if (file.calculated_columns_ignored) notices.push(LOCKED_NOTICE);
  if (file.unrecognised_columns.length > 0) {
    notices.push(`Columns not recognized and ignored: ${file.unrecognised_columns.join(", ")}`);
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
        // The file naming this row's compound and no batch leaves the chosen batch.
        const keepBatch = f.compound.batch_id == null && f.compound.molecule_id === r.moleculeId;
        patch.batchId = keepBatch ? r.batchId : (f.compound.batch_id ?? null);
        patch.batchNumber = keepBatch ? r.batchNumber : (f.compound.batch_number ?? null);
      }
    }
    const keys = Object.keys(patch) as (keyof LabellingRow)[];
    if (!keys.some((k) => patch[k] !== r[k])) return r;
    filled += 1;
    return { ...r, ...patch };
  });
  return { rows: out, filled, problems, notices };
}

/** The label Match from labels asks about for a row, or null: an unused row, one with a
 *  compound, and one whose label is blank or too long to be stored are left alone. */
function labelToMatch(r: LabellingRow): string | null {
  const label = r.label.trim();
  return r.used && !r.moleculeId && label !== "" && label.length <= MAX_LABEL ? label : null;
}

/** The distinct labels of the positions that have a label and no compound, in table order. */
export function labelsToMatch(rows: readonly LabellingRow[]): string[] {
  return [...new Set(rows.map(labelToMatch).filter((label) => label !== null))];
}

export interface LabelMatchApplication<T extends LabellingRow> {
  rows: T[];
  /** Table rows that took a compound. */
  matched: number;
  /** Used table rows that had a compound before the answer was applied. */
  alreadyMatched: number;
  /** Labels that named no registered compound, each once, in table order. */
  unmatched: string[];
}

/** Fill the compound of each position whose label the answer resolved. A row is filled
 *  through {@link applyLayout}, as by a layout file naming that compound and no batch. */
export function applyLabelMatches<T extends LabellingRow>(
  rows: readonly T[],
  answer: PositionLabelMatchesResponse,
): LabelMatchApplication<T> {
  const compounds = new Map(answer.matches.map((m) => [m.label, m.compound]));
  const found: LayoutFileRow[] = [];
  const unmatched = new Set<string>();
  for (const r of rows) {
    const label = labelToMatch(r);
    // A label edited while the answer was on its way was not asked about.
    if (label === null || !compounds.has(label)) continue;
    const compound = compounds.get(label);
    if (!compound) {
      unmatched.add(label);
      continue;
    }
    found.push({
      position: r.positionLabel,
      label: null,
      note: null,
      well_type: null,
      dose: null,
      use: null,
      compound,
      problems: [],
    });
  }
  const applied = applyLayout(
    rows,
    { rows: found, unrecognised_columns: [], calculated_columns_ignored: false },
    { allowUse: false, calculatedLocked: false },
  );
  return {
    rows: applied.rows,
    matched: applied.filled,
    alreadyMatched: rows.filter((r) => r.used && r.moleculeId).length,
    unmatched: [...unmatched],
  };
}

/** What Fill from file says it did; `saveButton` is the button that stores it. */
export function filledMessage(filled: number, fileName: string, saveButton: string): string {
  return `Filled ${formatCount(filled, "position")} from ${fileName}. Nothing is saved until you press ${saveButton}.`;
}

/** Labels that found no compound are listed up to this many; the rest are counted. */
const MAX_UNMATCHED_LISTED = 20;

export interface LabelMatchMessage {
  /** "neutral" is neither success nor a warning. */
  tone: "ok" | "neutral" | "warn";
  text: string;
  /** A muted second line: the labels that found no compound, beside a match. */
  detail: string | null;
}

/** What Match from labels says it did. Nothing new is a warning only when no position has
 *  a compound at all: the wizard matches on its own when the file is read, and what is
 *  left may be controls. Beside a match, the unmatched labels are a muted line, not a
 *  warning: many, such as a control's, name no compound. */
export function labelMatchMessage({
  matched,
  alreadyMatched,
  unmatched,
  saveButton,
}: {
  matched: number;
  alreadyMatched: number;
  unmatched: readonly string[];
  saveButton: string;
}): LabelMatchMessage {
  const more = unmatched.length - MAX_UNMATCHED_LISTED;
  const notFound =
    unmatched.length > 0
      ? `No compound found for: ${unmatched.slice(0, MAX_UNMATCHED_LISTED).join(", ")}${
          more > 0 ? ` and ${more} more` : ""
        }`
      : null;
  if (matched === 0) {
    const lead =
      alreadyMatched === 0
        ? "No label matched a registered compound."
        : alreadyMatched === 1
          ? "1 position is already matched."
          : `${alreadyMatched} positions are already matched.`;
    return {
      tone: alreadyMatched > 0 ? "neutral" : "warn",
      text: notFound ? `${lead} ${notFound}.` : lead,
      detail: null,
    };
  }
  const also =
    alreadyMatched > 0
      ? ` ${alreadyMatched} ${alreadyMatched === 1 ? "was" : "were"} already matched.`
      : "";
  return {
    tone: "ok",
    text: `Matched ${formatCount(matched, "position")} from ${matched === 1 ? "its label" : "their labels"}.${also} Nothing is saved until you press ${saveButton}.`,
    detail: notFound,
  };
}
