import { describe, expect, it } from "vitest";

import type { RunCurves } from "../types";
import {
  buildPositionEdits,
  calculatedLockedReason,
  labellingEditRefusal,
  reasonRequired,
  rowsFromPositions,
  valuesOf,
} from "./position-edits";

type Position = RunCurves["positions"][number];

const positions: Position[] = [
  {
    well_id: "w1",
    position: "A1",
    row: "A",
    column: 1,
    well_type: "reference",
    batch_id: "b1",
    batch_number: "B-1",
    molecule_id: "m1",
    molecule_name: "ABC-0000001",
    registration_number: "REG-0001",
    dose: 10,
    position_label: "Position 1",
    label: "Protein alone",
    note: "bubble at start",
  },
  {
    well_id: "w2",
    position: "A2",
    row: "A",
    column: 2,
    well_type: "sample",
    batch_id: "b2",
    batch_number: "B-2",
    molecule_id: "m2",
    molecule_name: "ABC-0000002",
    registration_number: "REG-0002",
    dose: 50,
    position_label: "Position 2",
    label: "x",
    note: null,
  },
  {
    well_id: "w3",
    position: "A3",
    row: "A",
    column: 3,
    well_type: "sample",
    batch_id: null,
    molecule_id: null,
    registration_number: null,
    dose: null,
    position_label: "Position 3",
    label: null,
    note: null,
  },
];

describe("position edits", () => {
  it("builds rows from positions in holder order with the well id as key", () => {
    const rows = rowsFromPositions([positions[2], positions[0], positions[1]]);
    expect(rows.map((r) => r.key)).toEqual(["w1", "w2", "w3"]);
    expect(rows[0]).toMatchObject({
      positionLabel: "Position 1",
      used: true,
      label: "Protein alone",
      note: "bubble at start",
      wellType: "reference",
      moleculeId: "m1",
      moleculeName: "ABC-0000001",
      batchId: "b1",
      batchNumber: "B-1",
      moleculeRef: "REG-0001",
      dose: "10",
    });
    expect(rows[2]).toMatchObject({
      label: "",
      note: "",
      moleculeId: null,
      moleculeRef: null,
      batchId: null,
      batchNumber: null,
      dose: "",
    });
  });

  it("returns no edits when nothing changed, treating a blank label and null as the same", () => {
    expect(buildPositionEdits(positions, rowsFromPositions(positions))).toEqual([]);
    const blanks = rowsFromPositions(positions).map((r) =>
      r.key === "w3" ? { ...r, label: "  ", note: " " } : r,
    );
    expect(buildPositionEdits(positions, blanks)).toEqual([]);
  });

  it("compares the concentration as a number", () => {
    const rows = rowsFromPositions(positions).map((r) =>
      r.key === "w2" ? { ...r, dose: "50.0" } : r,
    );
    expect(buildPositionEdits(positions, rows)).toEqual([]);
  });

  it("returns only the changed rows, each with the values the position had", () => {
    const rows = rowsFromPositions(positions).map((r) =>
      r.key === "w2" ? { ...r, label: "y", dose: "25" } : r,
    );
    expect(buildPositionEdits(positions, rows)).toEqual([
      {
        well_id: "w2",
        expected: valuesOf(positions[1]),
        new: { ...valuesOf(positions[1]), label: "y", dose: 25 },
      },
    ]);
  });

  it("sends no batch for a row with a compound and no batch", () => {
    const rows = rowsFromPositions(positions).map((r) =>
      r.key === "w1" ? { ...r, moleculeId: "m9", moleculeName: "ABC-0000009", batchId: null } : r,
    );
    const edits = buildPositionEdits(positions, rows);
    expect(edits).toHaveLength(1);
    expect(edits[0].well_id).toBe("w1");
    expect(edits[0].new.batch_id).toBeNull();
    expect(edits[0].expected.batch_id).toBe("b1");
  });

  it("refuses every edit on a locked run", () => {
    expect(labellingEditRefusal({ is_locked: true })).toBe("The run is locked.");
    expect(labellingEditRefusal({ is_locked: false })).toBeNull();
  });

  it("locks the calculated fields outside draft and in progress, and asks for a reason on completed and approved", () => {
    expect(calculatedLockedReason({ status: "draft" })).toBeNull();
    expect(calculatedLockedReason({ status: "in_progress" })).toBeNull();
    expect(calculatedLockedReason({ status: "rejected" })).toMatch(/draft or in progress/);
    expect(calculatedLockedReason({ status: "completed" })).toBe(
      "Role, compound, batch and concentration can be changed only while the run is draft or in progress.",
    );
    expect([
      reasonRequired({ status: "completed" }),
      reasonRequired({ status: "approved" }),
      reasonRequired({ status: "rejected" }),
      reasonRequired({ status: "draft" }),
    ]).toEqual([true, true, false, false]);
  });
});
