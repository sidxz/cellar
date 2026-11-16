import { describe, expect, it } from "vitest";
import type { Dataset } from "../types";
import {
  categoryColumns,
  column,
  isSampleRow,
  numberAt,
  numericColumns,
  resolveUserColumns,
  uniqueCompounds,
  valueColumns,
} from "./dataset";

const RAW = "rd:r1:raw";

function ds(): Dataset {
  const col = (key: string, kind: Dataset["columns"][number]["kind"], hidden = false) => ({
    key,
    label: key,
    kind,
    unit: null,
    group: null,
    provenance: {},
    hidden,
  });
  return {
    revision: "x",
    level: "wells",
    row_count: 5,
    row_ids: ["a", "b", "c", "d", "e"],
    columns: [
      col("compound", "category"),
      col("molecule_id", "text", true),
      col("well_type", "category"),
      col("operator", "user"),
      col("well_order", "number"),
      col(RAW, "number"),
      col(`${RAW}:q`, "category"),
      col(`${RAW}:outlier`, "category"),
    ],
    values: {
      compound: ["CEL-1", "CEL-1", "DMSO", "CEL-2", null],
      molecule_id: ["m1", "m1", null, "m2", "m3"],
      well_type: ["sample", "sample", "negative_control", "sample", null],
      operator: ["u1", "u1", "u2", "u1", "u1"],
      well_order: [1, 2, 3, 4, null],
      [RAW]: [0.5, Number.NaN, null, 2, 3],
      [`${RAW}:q`]: [null, null, null, ">", null],
      [`${RAW}:outlier`]: [null, "outlier", null, null, null],
    },
  };
}

describe("dataset helpers", () => {
  it("numberAt returns null for NaN and null", () => {
    const d = ds();
    expect(numberAt(d, RAW, 0)).toBe(0.5);
    expect(numberAt(d, RAW, 1)).toBeNull();
    expect(numberAt(d, RAW, 2)).toBeNull();
    expect(numberAt(d, "missing", 0)).toBeNull();
  });

  it("valueColumns excludes qualifier and outlier siblings", () => {
    expect(valueColumns(ds()).map((c) => c.key)).toEqual([RAW]);
  });

  it("numeric and category columns skip hidden ones and include user columns as categories", () => {
    const d = ds();
    expect(numericColumns(d).map((c) => c.key)).toEqual(["well_order", RAW]);
    expect(categoryColumns(d).map((c) => c.key)).toEqual([
      "compound",
      "well_type",
      "operator",
      `${RAW}:q`,
      `${RAW}:outlier`,
    ]);
    expect(column(d, "molecule_id")?.hidden).toBe(true);
  });

  it("isSampleRow: sample wells and well-less rows with a compound", () => {
    const d = ds();
    expect([0, 1, 2, 3, 4].map((i) => isSampleRow(d, i))).toEqual([true, true, false, true, true]);
  });

  it("uniqueCompounds drops controls and null molecules and dedupes", () => {
    const d = ds();
    expect(uniqueCompounds(d, [0, 1, 2, 3])).toEqual(["m1", "m2"]);
    d.values.molecule_id[4] = null;
    expect(uniqueCompounds(d, [4])).toEqual([]);
  });

  it("resolveUserColumns replaces user ids with names and never leaves an id behind", () => {
    const names: Record<string, string> = { u1: "A. Chen", u2: "R. Iyer" };
    const d = resolveUserColumns(ds(), (id) => names[id] ?? "Unknown member");
    expect(d.values.operator).toEqual(["A. Chen", "A. Chen", "R. Iyer", "A. Chen", "A. Chen"]);
    expect(column(d, "operator")?.kind).toBe("category");
  });
});
