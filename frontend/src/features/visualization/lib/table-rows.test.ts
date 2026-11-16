import { describe, expect, it } from "vitest";
import type { Dataset } from "../types";
import { MAX_PINNED, orderTableRows, pinnedBlock } from "./table-rows";

const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 6,
  row_ids: ["w0", "w1", "w2", "w3", "w4", "w5"],
  columns: [],
  values: {},
};
const mask = Uint8Array.from([1, 1, 0, 1, 0, 1]);
const selection = new Set(["w1", "w2", "w5"]);

describe("orderTableRows", () => {
  it("pins the selected passing rows and leaves failing rows out", () => {
    expect(orderTableRows(ds, mask, selection, false)).toEqual({ pinned: [1, 5], rest: [0, 3] });
  });

  it("appends the failing rows when showing all", () => {
    expect(orderTableRows(ds, mask, selection, true)).toEqual({
      pinned: [1, 5],
      rest: [0, 3, 2, 4],
    });
  });

  it("pins nothing without a selection", () => {
    expect(orderTableRows(ds, mask, new Set(), false)).toEqual({ pinned: [], rest: [0, 1, 3, 5] });
  });
});

describe("pinnedBlock", () => {
  const many = Array.from({ length: 3000 }, (_, i) => i);

  it("shows at most MAX_PINNED selected rows and counts the rest", () => {
    expect(pinnedBlock([4, 7], false)).toEqual({ shown: [4, 7], more: 0 });
    const block = pinnedBlock(many, false);
    expect(block.shown).toEqual(many.slice(0, MAX_PINNED));
    expect(block.more).toBe(3000 - MAX_PINNED);
  });

  it("shows nothing while collapsed", () => {
    expect(pinnedBlock(many, true)).toEqual({ shown: [], more: 0 });
  });
});
