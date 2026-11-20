import { describe, expect, it } from "vitest";

import {
  type LabellingRow,
  compoundWithoutBatch,
  parseDose,
  rowsProblem,
  setRoleForRows,
  withoutBatchLine,
} from "./labelling-rows";

let n = 0;
function row(patch: Partial<LabellingRow>): LabellingRow {
  n += 1;
  return {
    key: `k${n}`,
    positionLabel: `Position ${n}`,
    used: true,
    label: "",
    note: "",
    wellType: "sample",
    moleculeId: null,
    moleculeName: null,
    moleculeRef: null,
    batchId: null,
    batchNumber: null,
    dose: "",
    ...patch,
  };
}

describe("labelling rows", () => {
  it("counts used rows with a compound and no batch", () => {
    expect(
      compoundWithoutBatch([
        row({ moleculeId: "m", batchId: null }),
        row({ moleculeId: "m", batchId: "b" }),
        row({ moleculeId: "m", batchId: null, used: false }),
        row({}),
      ]),
    ).toBe(1);
  });

  it("has no line beside the button at 0, and counts the positions otherwise", () => {
    expect(withoutBatchLine(0)).toBeNull();
    expect(withoutBatchLine(1)).toMatch(/^1 position has /);
    expect(withoutBatchLine(3)).toMatch(/^3 positions have /);
  });

  it("names the first used row with a bad concentration, label or note", () => {
    expect(rowsProblem([row({ positionLabel: "Position 1", dose: "12.5" })])).toBeNull();
    expect(rowsProblem([row({ positionLabel: "Position 1", dose: "abc" })])).toMatch(
      /^Position 1: .*concentration/,
    );
    expect(
      rowsProblem([row({}), row({ positionLabel: "Position 2", label: "x".repeat(201) })]),
    ).toMatch(/^Position 2: .*label/);
    expect(rowsProblem([row({ positionLabel: "Position 3", note: "x".repeat(1001) })])).toMatch(
      /^Position 3: .*note/,
    );
    expect(rowsProblem([row({ dose: "-1", used: false })])).toBeNull();
  });

  it("parses a blank dose as null and refuses a negative or non-numeric one", () => {
    expect(parseDose(" ")).toBeNull();
    expect(parseDose("0")).toBe(0);
    expect(parseDose("-1")).toBeUndefined();
    expect(parseDose("abc")).toBeUndefined();
  });

  it("sets one role on the chosen rows and leaves the rest", () => {
    const rows = [row({ key: "a" }), row({ key: "b" }), row({ key: "c" })];
    const out = setRoleForRows(rows, new Set(["a", "c"]), "reference");
    expect(out.map((r) => r.wellType)).toEqual(["reference", "sample", "reference"]);
    expect(rows.every((r) => r.wellType === "sample")).toBe(true);
  });
});
