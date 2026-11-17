import { describe, expect, it } from "vitest";
import type { Dataset } from "../types";
import { actionSet } from "./action-set";

function ds(n: number): Dataset {
  return {
    revision: "x",
    level: "wells",
    row_count: n,
    row_ids: Array.from({ length: n }, (_, i) => `r${i}`),
    columns: [],
    values: {},
  };
}

describe("actionSet", () => {
  it("selection: acts on selected rows that pass, and counts the hidden ones", () => {
    const d = ds(20);
    const selection = new Set(Array.from({ length: 12 }, (_, i) => `r${i}`));
    const mask = new Uint8Array(20).fill(1);
    mask[0] = 0;
    mask[1] = 0;
    mask[2] = 0;
    const set = actionSet(d, selection, mask);
    expect(set.mode).toBe("selected");
    expect(set.rows).toHaveLength(9);
    expect(set.hiddenSelected).toBe(3);
    expect(set.rows[0]).toBe(3);
  });

  it("no selection: acts on every passing row", () => {
    const d = ds(5);
    const mask = Uint8Array.from([1, 0, 1, 1, 0]);
    expect(actionSet(d, new Set(), mask)).toEqual({
      mode: "filtered",
      rows: [0, 2, 3],
      hiddenSelected: 0,
    });
  });

  it("selected ids that are not in the dataset are ignored", () => {
    const d = ds(3);
    const set = actionSet(d, new Set(["r1", "gone"]), new Uint8Array(3).fill(1));
    expect(set).toEqual({ mode: "selected", rows: [1], hiddenSelected: 0 });
  });
});
