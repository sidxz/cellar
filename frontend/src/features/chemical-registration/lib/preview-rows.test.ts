import { describe, expect, it } from "vitest";

import type { PreviewItem, PreviewRegistrationItemResponse } from "../types/registration-wizard";
import { buildPreviewRows } from "./preview-rows";

/** A parsed file row; `row_index` is 0-based, `file_row` is what the scientist sees. */
const item = (row_index: number, patch: Partial<PreviewItem> = {}): PreviewItem => ({
  row_index,
  file_row: row_index + 2,
  name: `Cmpd-${row_index}`,
  smiles: "CCO",
  external_ids: [],
  batch_ids: [],
  ...patch,
});

const batch = (...ids: string[]) => ids.map((identifier) => ({ identifier, source: "Lot" }));

/** Forecast keyed by row_index, as StepPreview builds it. */
const forecastOf = (
  entries: [number, Partial<PreviewRegistrationItemResponse>][],
): Map<number, PreviewRegistrationItemResponse> =>
  new Map(entries.map(([row, f]) => [row, { index: row, action: "registered", ...f }]));

describe("buildPreviewRows", () => {
  it("reads the second row of one new compound as 'Same as row <first>' and counts the compound once", () => {
    const { rows, counts } = buildPreviewRows(
      [item(0), item(1)],
      forecastOf([
        [0, { compound_key: "KEY-A" }],
        [1, { compound_key: "KEY-A" }],
      ]),
      false,
    );
    expect(rows[0].compound).toBe("New");
    expect(rows[1].compound).toBe("Same as row 2");
    expect(counts.newCompounds).toBe(1);
  });

  it("shows a row whose batch ID is already in ChemCellar with its batch number", () => {
    const { rows, counts } = buildPreviewRows(
      [item(0, { batch_ids: batch("SACC-1-001") })],
      forecastOf([
        [
          0,
          {
            action: "deduplicated",
            compound_key: "KEY-A",
            batch_action: "existing",
            matched_batch_number: "CC-013112-001",
          },
        ],
      ]),
      false,
    );
    expect(rows[0].compound).toBe("Already in ChemCellar");
    expect(rows[0].batch).toBe("Already in ChemCellar CC-013112-001");
    expect(rows[0].problem).toBeNull();
    expect(counts).toMatchObject({ existingBatches: 1, newBatches: 0, problems: 0 });
  });

  it("shows the forecast's batch problem and counts it, still counting the compound", () => {
    const reason = "MSD-1 already belongs to CC-061200-001 (another compound)";
    const { rows, counts } = buildPreviewRows(
      [item(0, { batch_ids: batch("MSD-1") })],
      forecastOf([[0, { compound_key: "KEY-A", batch_action: "problem", batch_problem: reason }]]),
      false,
    );
    expect(rows[0].problem).toBe(reason);
    expect(rows[0].batch).toBeNull();
    expect(rows[0].compound).toBe("New");
    expect(counts).toMatchObject({ problems: 1, newCompounds: 1, newBatches: 0 });
  });

  it("flags a batch ID on rows of two different compounds on every such row", () => {
    const { rows, counts } = buildPreviewRows(
      [item(0, { batch_ids: batch("001") }), item(1, { batch_ids: batch("001") })],
      forecastOf([
        [0, { compound_key: "KEY-A" }],
        [1, { compound_key: "KEY-B" }],
      ]),
      false,
    );
    const sentence =
      "001 is on 2 compounds. Batch IDs must be unique in the workspace. Map the column with the full batch name instead.";
    expect(rows.map((r) => r.problem)).toEqual([sentence, sentence]);
    expect(counts).toMatchObject({ problems: 2, newBatches: 0, newCompounds: 2 });
  });

  it("reads the same batch ID twice for one compound as one batch", () => {
    const { rows, counts } = buildPreviewRows(
      [
        item(0, { batch_ids: batch("SACC-1-001") }),
        item(1, { batch_ids: batch("SACC-1-001", "MSD-1") }),
      ],
      forecastOf([
        [0, { compound_key: "KEY-A", batch_action: "new" }],
        [1, { compound_key: "KEY-A", batch_action: "new" }],
      ]),
      false,
    );
    expect(rows[0].batch).toBe("New batch");
    expect(rows[1].batch).toBe("Same batch as row 2");
    expect(counts.newBatches).toBe(1);
  });

  it("gives each batch ID of one compound its own new batch", () => {
    const { rows, counts } = buildPreviewRows(
      [item(0, { batch_ids: batch("SACC-1-001") }), item(1, { batch_ids: batch("SACC-1-002") })],
      forecastOf([
        [0, { compound_key: "KEY-A", batch_action: "new" }],
        [1, { compound_key: "KEY-A", batch_action: "new" }],
      ]),
      false,
    );
    expect(rows.map((r) => r.batch)).toEqual(["New batch", "New batch"]);
    expect(counts).toMatchObject({ newCompounds: 1, newBatches: 2 });
  });

  it("makes no batch for an existing compound without batch IDs unless asked to", () => {
    const items = [item(0)];
    const forecast = forecastOf([[0, { action: "deduplicated", compound_key: "KEY-A" }]]);

    const off = buildPreviewRows(items, forecast, false);
    expect(off.rows[0].batch).toBe("No new batch");
    expect(off.counts.newBatches).toBe(0);

    const on = buildPreviewRows(items, forecast, true);
    expect(on.rows[0].batch).toBe("New batch");
    expect(on.counts.newBatches).toBe(1);
  });

  it("counts parse-error rows as problems and shows their error", () => {
    const { rows, counts } = buildPreviewRows(
      [item(0), item(1, { name: null, smiles: null, error: "Row 3: no name and no structure" })],
      forecastOf([[0, { compound_key: "KEY-A" }]]),
      false,
    );
    expect(rows[1].problem).toBe("Row 3: no name and no structure");
    expect(rows[1].compound).toBeNull();
    expect(counts).toMatchObject({ rows: 2, problems: 1, newCompounds: 1 });
  });

  it("reads a new compound without a structure as 'New (undisclosed)'", () => {
    const { rows, counts } = buildPreviewRows(
      [item(0, { smiles: null })],
      forecastOf([[0, { compound_key: "ids:JSF-1187" }]]),
      false,
    );
    expect(rows[0].compound).toBe("New (undisclosed)");
    expect(counts.newCompounds).toBe(1);
  });

  it("uses the file row number, falling back to row_index + 2", () => {
    const { rows } = buildPreviewRows(
      [item(0, { file_row: 7 }), item(1, { file_row: undefined })],
      null,
      false,
    );
    expect(rows.map((r) => r.fileRow)).toEqual([7, 3]);
  });

  it("leaves outcomes empty while the forecast is pending but still counts parse errors", () => {
    const { rows, counts } = buildPreviewRows(
      [item(0), item(1, { error: "bad row" })],
      null,
      false,
    );
    expect(rows[0]).toMatchObject({ compound: null, batch: null, problem: null });
    expect(counts).toMatchObject({ rows: 2, problems: 1, newCompounds: 0, newBatches: 0 });
  });
});
