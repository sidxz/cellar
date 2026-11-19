import type { PreviewItem, PreviewRegistrationItemResponse } from "../types/registration-wizard";

/** What the import will do with one file row, in words a scientist reads. */
export interface PreviewRowView {
  item: PreviewItem;
  fileRow: number;
  /** "New", "New (undisclosed)", "Same as row 11", "Already in ChemCellar", … ; null while waiting. */
  compound: string | null;
  /** "New batch", "Already in ChemCellar CC-…-001", "Same batch as row 4", "No new batch"; null on problem or waiting. */
  batch: string | null;
  problem: string | null;
  /** Values that won't be stored, and why: the file's or vault's own, then the forecast's. */
  warnings: string[];
}

export interface PreviewCounts {
  rows: number;
  newCompounds: number;
  newBatches: number;
  existingBatches: number;
  problems: number;
}

const fileRowOf = (item: PreviewItem) => item.file_row || item.row_index + 2;

/**
 * Turn the parse preview plus the per-row forecast into rows and the five tiles.
 * Rows of one compound are grouped by the forecast's ``compound_key`` (the forecast
 * itself only looks at the database, so it calls every row of a new compound "new").
 * Mirrors the import's rules (spec 2026-11-18 §4): a row with batch IDs is that
 * batch; a row without them gets a batch when its compound is new, or when
 * ``createBatchOnDuplicate`` is on.
 */
export function buildPreviewRows(
  items: PreviewItem[],
  forecast: Map<number, PreviewRegistrationItemResponse> | null,
  createBatchOnDuplicate: boolean,
): { rows: PreviewRowView[]; counts: PreviewCounts } {
  const keyOf = (item: PreviewItem) => {
    const f = forecast?.get(item.row_index);
    return f?.compound_key ?? `row:${item.row_index}`;
  };
  // Only deciding batch IDs say which batch a row is; a stored-only one is stored or
  // skipped, never matched and never a problem.
  const decidingBatchIds = (item: PreviewItem) =>
    (item.batch_ids ?? []).filter((b) => b.decides !== false).map((b) => b.identifier);

  // A batch ID on rows of two different compounds can't be unique in the workspace.
  const keysByBatchId = new Map<string, Set<string>>();
  if (forecast) {
    for (const item of items) {
      if (item.error) continue;
      for (const id of decidingBatchIds(item)) {
        const keys = keysByBatchId.get(id) ?? new Set<string>();
        keys.add(keyOf(item));
        keysByBatchId.set(id, keys);
      }
    }
  }

  const firstRowOfKey = new Map<string, number>();
  const firstRowOfBatchId = new Map<string, number>();
  const counts: PreviewCounts = {
    rows: items.length,
    newCompounds: 0,
    newBatches: 0,
    existingBatches: 0,
    problems: 0,
  };

  const rows = items.map((item): PreviewRowView => {
    const fileRow = fileRowOf(item);
    const warnings = [
      ...new Set([...(item.warnings ?? []), ...(forecast?.get(item.row_index)?.warnings ?? [])]),
    ];
    const view = (compound: string | null, batch: string | null, problem: string | null) => {
      if (problem) counts.problems += 1;
      return { item, fileRow, compound, batch, problem, warnings };
    };

    if (item.error) return view(null, null, item.error);
    const f = forecast?.get(item.row_index);
    if (!f) return view(null, null, null); // waiting, or forecast unavailable
    if (!f.action) return view(null, null, f.error ?? "Structure could not be read");
    if (f.action === "conflict") return view(null, null, f.conflict_reason ?? "Conflict");

    // Compound
    const key = keyOf(item);
    const earlier = firstRowOfKey.get(key);
    let compound: string;
    let compoundIsNew = false;
    if (earlier !== undefined) {
      compound = `Same as row ${earlier}`;
    } else {
      firstRowOfKey.set(key, fileRow);
      if (f.action === "registered") {
        compoundIsNew = true;
        counts.newCompounds += 1;
        compound = item.smiles ? "New" : "New (undisclosed)";
      } else if (f.action === "disclosed") {
        compound = "Adds the structure to an undisclosed compound";
      } else if (f.action === "merge_candidate") {
        compound = "Possible merge";
      } else {
        compound = "Already in ChemCellar";
      }
    }

    // Batch — a possible merge waits for the scientist's decision, so no batch yet.
    if (f.action === "merge_candidate") return view(compound, "No new batch", null);
    const batchIds = decidingBatchIds(item);
    // The server's own check of the file (same rule the import applies).
    if (item.batch_problem) return view(compound, null, item.batch_problem);
    if (batchIds.length > 0) {
      const shared = batchIds.find((id) => (keysByBatchId.get(id)?.size ?? 0) > 1);
      if (shared) {
        const n = keysByBatchId.get(shared)?.size ?? 0;
        return view(
          compound,
          null,
          `${shared} is on ${n} compounds. Batch IDs must be unique in the workspace. Map the column with the full batch name instead.`,
        );
      }
      if (f.batch_action === "problem")
        return view(compound, null, f.batch_problem ?? "Batch problem");
      // An earlier row of this file already names this batch (new or existing):
      // same batch, counted once.
      const sameBatch = batchIds
        .map((id) => firstRowOfBatchId.get(id))
        .find((r) => r !== undefined);
      if (sameBatch !== undefined) return view(compound, `Same batch as row ${sameBatch}`, null);
      for (const id of batchIds) firstRowOfBatchId.set(id, fileRow);
      if (f.batch_action === "existing") {
        counts.existingBatches += 1;
        return view(compound, `Already in ChemCellar ${f.matched_batch_number ?? ""}`.trim(), null);
      }
      counts.newBatches += 1;
      const has = f.existing_batch_count ?? 0;
      return view(
        compound,
        has > 0 ? `New batch · compound already has ${has}` : "New batch",
        null,
      );
    }

    if (compoundIsNew || createBatchOnDuplicate) {
      counts.newBatches += 1;
      return view(compound, "New batch", null);
    }
    return view(compound, "No new batch", null);
  });

  return { rows, counts };
}
