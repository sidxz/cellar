import { describe, expect, it } from "vitest";
import type { Dataset } from "../types";
import { isOutlierRow, outlierTargets } from "./outliers";

// r1: wells a (flagged on one readout), b, a well-less row; r2 (locked): well c.
const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 4,
  row_ids: ["r1:a", "r1:b", "r1:m:mol:batch", "r2:c"],
  columns: [],
  values: {
    "rd:x:raw": [1, 2, 3, 4],
    "rd:x:raw:outlier": [null, null, null, null],
    "rd:y:raw:outlier": ["outlier", null, null, null],
  },
};

describe("outliers", () => {
  it("a row is an outlier when any of its values is flagged", () => {
    expect([0, 1, 2, 3].map((i) => isOutlierRow(ds, i))).toEqual([true, false, false, false]);
  });

  it("splits the wells of editable runs by their flag, per run; well-less rows and other runs stay out", () => {
    const t = outlierTargets(ds, [0, 1, 2, 3], new Set(["r1"]));
    expect([...t.flag]).toEqual([["r1", ["b"]]]);
    expect([...t.unflag]).toEqual([["r1", ["a"]]]);
  });
});
