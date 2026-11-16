import { describe, expect, it } from "vitest";
import type { Dataset } from "../types";
import {
  type Filter,
  type SubstructureFilter,
  binCounts,
  computePassMask,
  filterCondition,
  filterSummary,
  fixedBins,
  isFilterActive,
  substructureSummary,
} from "./filters";

function ds(): Dataset {
  const col = (key: string, kind: "number" | "category") => ({
    key,
    label: key,
    kind,
    unit: null,
    group: null,
    provenance: {},
    hidden: false,
  });
  return {
    revision: "x",
    level: "wells",
    row_count: 6,
    row_ids: ["r0", "r1", "r2", "r3", "r4", "r5"],
    columns: [col("inh", "number"), col("type", "category")],
    values: {
      inh: [-10, 0, 30, 30.0001, 100, null],
      type: ["sample", "sample", "sample", "negative_control", "positive_control", null],
    },
  };
}

const range = (min: number | null, max: number | null, includeMissing = false): Filter => ({
  id: "f-range",
  kind: "range",
  key: "inh",
  min,
  max,
  includeMissing,
});

const mask = (m: Uint8Array) => [...m];

describe("computePassMask", () => {
  it("range keeps both bounds", () => {
    expect(mask(computePassMask(ds(), [range(0, 30)]))).toEqual([0, 1, 1, 0, 0, 0]);
  });

  it("open bounds and missing values", () => {
    expect(mask(computePassMask(ds(), [range(30, null)]))).toEqual([0, 0, 1, 1, 1, 0]);
    expect(mask(computePassMask(ds(), [range(30, null, true)]))).toEqual([0, 0, 1, 1, 1, 1]);
  });

  it("category filter, with and without missing", () => {
    const f: Filter = {
      id: "f-cat",
      kind: "category",
      key: "type",
      values: ["sample"],
      includeMissing: false,
    };
    expect(mask(computePassMask(ds(), [f]))).toEqual([1, 1, 1, 0, 0, 0]);
    expect(mask(computePassMask(ds(), [{ ...f, includeMissing: true }]))).toEqual([
      1, 1, 1, 0, 0, 1,
    ]);
  });

  it("two filters AND together", () => {
    const f: Filter = {
      id: "f-cat",
      kind: "category",
      key: "type",
      values: ["sample"],
      includeMissing: false,
    };
    expect(mask(computePassMask(ds(), [range(0, null), f]))).toEqual([0, 1, 1, 0, 0, 0]);
  });

  it("exceptId ignores that one filter", () => {
    const f: Filter = {
      id: "f-cat",
      kind: "category",
      key: "type",
      values: ["sample"],
      includeMissing: false,
    };
    expect(mask(computePassMask(ds(), [range(0, null), f], "f-cat"))).toEqual([0, 1, 1, 1, 1, 0]);
  });

  it("rows filter keeps exactly the listed rows", () => {
    const f: Filter = { id: "f-rows", kind: "rows", rowIds: ["r1", "r4"] };
    expect(mask(computePassMask(ds(), [f]))).toEqual([0, 1, 0, 0, 1, 0]);
  });

  it("no filters → everything passes", () => {
    expect(mask(computePassMask(ds(), []))).toEqual([1, 1, 1, 1, 1, 1]);
  });
});

describe("substructure filter", () => {
  /** Three wells of m1, a control without a compound, one well of m2. */
  const wells = (): Dataset => ({
    ...ds(),
    row_count: 5,
    row_ids: ["w1", "w2", "w3", "c1", "w4"],
    values: {
      inh: [10, 50, 90, 50, 50],
      type: ["sample", "sample", "sample", "negative_control", "sample"],
      molecule_id: ["m1", "m1", "m1", null, "m2"],
    },
  });
  const sub = (moleculeIds: string[], query = "c1ccccc1"): SubstructureFilter => ({
    id: "sub-1",
    kind: "substructure",
    query,
    queryKind: "smiles",
    moleculeIds,
  });

  it("keeps the rows of matched compounds; rows without a compound never pass", () => {
    expect(mask(computePassMask(wells(), [sub(["m1"])]))).toEqual([1, 1, 1, 0, 0]);
    expect(mask(computePassMask(wells(), [sub([])]))).toEqual([0, 0, 0, 0, 0]);
  });

  it("ANDs with other filters, and exceptId ignores it", () => {
    expect(mask(computePassMask(wells(), [sub(["m1"]), range(30, null)]))).toEqual([0, 1, 1, 0, 0]);
    expect(mask(computePassMask(wells(), [sub(["m1"]), range(30, null)], "sub-1"))).toEqual([
      0, 1, 1, 1, 1,
    ]);
  });

  it("reads as the query it contains, cut at 24 characters", () => {
    expect(substructureSummary(sub(["m1"]))).toBe("Contains c1ccccc1");
    expect(substructureSummary(sub([], "C".repeat(24)))).toBe(`Contains ${"C".repeat(24)}`);
    expect(substructureSummary(sub([], "C".repeat(25)))).toBe(`Contains ${"C".repeat(23)}…`);
    expect(filterSummary(wells(), sub(["m1"]))).toBe("Contains c1ccccc1");
  });

  it("counts the dataset compounds it keeps", () => {
    expect(filterCondition(wells(), sub(["m1", "m9"]))).toBe("1 of 2 compounds");
  });

  it("filters nothing until it is matched against this data", () => {
    const { moleculeIds: _, ...unmatched } = sub(["m1"]);
    expect(mask(computePassMask(wells(), [unmatched]))).toEqual([1, 1, 1, 1, 1]);
    expect(isFilterActive(wells(), unmatched)).toBe(false);
    expect(filterCondition(wells(), unmatched)).toBe("not matched");
  });
});

describe("fixedBins / binCounts", () => {
  it("edges come from the full column and do not move when filtering", () => {
    const d = ds();
    const { edges } = fixedBins(d, "inh", 11);
    expect(edges).toHaveLength(12);
    expect(edges[0]).toBe(-10);
    expect(edges[11]).toBe(100);
    const all = binCounts(d, "inh", edges, computePassMask(d, []));
    const filtered = binCounts(d, "inh", edges, computePassMask(d, [range(0, 30)]));
    expect(all.reduce((a, b) => a + b, 0)).toBe(5);
    expect(filtered.reduce((a, b) => a + b, 0)).toBe(2);
    expect(fixedBins(d, "inh", 11).edges).toEqual(edges);
  });

  it("the maximum lands in the last bin", () => {
    const d = ds();
    const { edges } = fixedBins(d, "inh", 11);
    const counts = binCounts(d, "inh", edges, computePassMask(d, []));
    expect(counts[10]).toBe(1);
  });

  it("a constant column still gets a usable bin", () => {
    const d = ds();
    d.values.inh = [5, 5, 5, null, null, null];
    const { edges } = fixedBins(d, "inh", 4);
    expect(binCounts(d, "inh", edges, computePassMask(d, [])).reduce((a, b) => a + b, 0)).toBe(3);
  });
});
