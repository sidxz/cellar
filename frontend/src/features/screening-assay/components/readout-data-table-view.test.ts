import { describe, expect, it } from "vitest";
import type { PivotRow } from "../lib/readout-data-pivot";
import type { PlateMapResponse } from "../types";
import { readoutTableRows } from "./readout-data-table-view";

const row = (wellId: string | null): PivotRow => ({
  key: wellId ?? "summary",
  label: "CC-1",
  registrationNumber: "CC-1",
  moleculeName: "Compound one",
  aliases: ["Compound one"],
  batchNumber: "CC-1-001",
  smiles: null,
  moleculeId: "molecule-1",
  batchId: "batch-1",
  wellId,
  values: new Map(),
  curves: new Map(),
});

const plateMap = {
  dose_unit: "uM",
  plates: [
    {
      plate_number: 2,
      registered_plate_barcode: "PLATE-002",
      wells: [
        { well_id: "well-2", row: "A", column: 10, position: "A10", dose: 0.1 },
        { well_id: "well-1", row: "A", column: 2, position: "A02", dose: 0 },
      ],
    },
  ],
} as PlateMapResponse;

describe("readout table well context", () => {
  it("joins each well's own dose and plate, preserves zero, and orders wells numerically", () => {
    const rows = readoutTableRows([row("well-2"), row("well-1")], plateMap);
    expect(
      rows.map(({ wellId, position, dose, doseUnit, plateLabel }) => ({
        wellId,
        position,
        dose,
        doseUnit,
        plateLabel,
      })),
    ).toEqual([
      { wellId: "well-1", position: "A02", dose: 0, doseUnit: "uM", plateLabel: "PLATE-002" },
      { wellId: "well-2", position: "A10", dose: 0.1, doseUnit: "uM", plateLabel: "PLATE-002" },
    ]);
  });

  it("keeps summaries and unmatched wells without borrowing another well's concentration", () => {
    const rows = readoutTableRows([row(null), row("missing")], plateMap);
    for (const result of rows) {
      expect(result.dose).toBeNull();
      expect(result.position).toBeNull();
      expect(result.plateLabel).toBeNull();
    }
    expect(readoutTableRows([row("well-1")])[0].dose).toBeNull();
  });
});
