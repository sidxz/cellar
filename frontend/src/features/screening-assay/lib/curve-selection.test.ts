import { describe, expect, it } from "vitest";

import type { CurveGroup } from "./curve-plot";
import {
  CURVES_PER_REQUEST,
  EMPTY_SELECTION,
  MAX_CURVE_RUNS,
  applyClick,
  assignColourSlots,
  chunk,
  drawnPositionIds,
  matchesFilter,
  selectAll,
  toggleRun,
} from "./curve-selection";

const ids = ["w1", "w2", "w3", "w4", "w5"];
const NONE = { shift: false, toggle: false };

describe("applyClick", () => {
  it("a plain click selects only that position", () => {
    expect([...applyClick(selectAll(ids), ids, "w3", NONE).selected]).toEqual(["w3"]);
  });

  it("shift selects the inclusive range from the anchor in holder order", () => {
    const s = applyClick(applyClick(EMPTY_SELECTION, ids, "w4", NONE), ids, "w2", {
      shift: true,
      toggle: false,
    });
    expect([...s.selected].sort()).toEqual(["w2", "w3", "w4"]);
  });

  it("toggle adds and removes without clearing the rest", () => {
    const toggle = { shift: false, toggle: true };
    const one = applyClick(EMPTY_SELECTION, ids, "w1", NONE);
    const two = applyClick(one, ids, "w3", toggle);
    expect([...two.selected].sort()).toEqual(["w1", "w3"]);
    const back = applyClick(two, ids, "w1", toggle);
    expect([...back.selected]).toEqual(["w3"]);
  });

  it("shift with no anchor behaves as a plain click", () => {
    const s = applyClick(EMPTY_SELECTION, ids, "w2", { shift: true, toggle: false });
    expect([...s.selected]).toEqual(["w2"]);
    expect(s.anchor).toBe("w2");
  });
});

describe("assignColourSlots", () => {
  it("keeps a survivor's slot when another position is deselected", () => {
    const first = assignColourSlots(new Map(), ["w1", "w2", "w3"]);
    const next = assignColourSlots(first, ["w1", "w3"]);
    expect(next.get("w3")).toBe(2);
    expect(next.get("w1")).toBe(0);
    expect(next.has("w2")).toBe(false);
  });

  it("gives a newly selected position the lowest free slot", () => {
    const prev = new Map([
      ["w1", 0],
      ["w3", 2],
    ]);
    const next = assignColourSlots(prev, ["w1", "w3", "w5"]);
    expect(next.get("w5")).toBe(1);
  });

  it("returns an empty map when more than 8 are selected", () => {
    const nine = Array.from({ length: 9 }, (_, i) => `p${i}`);
    expect(assignColourSlots(new Map(), nine).size).toBe(0);
  });

  it("assigns slots in holder order on going back to 8 or fewer", () => {
    const nine = Array.from({ length: 9 }, (_, i) => `p${i}`);
    const cleared = assignColourSlots(new Map(), nine);
    const next = assignColourSlots(cleared, ["p2", "p5", "p7"]);
    expect([...next.entries()]).toEqual([
      ["p2", 0],
      ["p5", 1],
      ["p7", 2],
    ]);
  });
});

function group(prefix: string): CurveGroup {
  return {
    key: `run-${prefix}`,
    run: null,
    holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" },
    positions: [1, 2, 3].map((column) => ({
      well_id: `${prefix}${column}`,
      position: `A${column}`,
      row: "A",
      column,
      well_type: column === 1 ? "reference" : "sample",
      registration_number: null,
      position_label: `Position ${column}`,
      label: column === 2 ? "Second Label" : null,
      molecule_name: column === 3 ? "ABC-0000003" : null,
      batch_number: column === 3 ? "BATCH-07" : null,
      note: column === 1 ? "Bubble at start" : null,
    })),
  };
}

const groups = [group("a"), group("b")];

describe("drawnPositionIds", () => {
  it("adds the reference positions only of runs that have a selected position", () => {
    expect(drawnPositionIds(groups, new Set(["a2"]), true)).toEqual(["a2", "a1"]);
    expect(drawnPositionIds(groups, new Set(["a2"]), false)).toEqual(["a2"]);
    expect(drawnPositionIds(groups, new Set(["a1", "b3"]), true)).toEqual(["a1", "b3", "b1"]);
  });
});

describe("matchesFilter", () => {
  it("filters by label, compound, batch or note, ignoring case", () => {
    const [p1, p2, p3] = groups[0].positions;
    expect(matchesFilter(p2, "second label")).toBe(true);
    expect(matchesFilter(p3, "abc-0000003")).toBe(true);
    expect(matchesFilter(p3, "batch-0")).toBe(true);
    expect(matchesFilter(p1, "BUBBLE")).toBe(true);
    expect(matchesFilter(p1, "second")).toBe(false);
    expect(matchesFilter(p1, "Position 1")).toBe(false);
    expect(matchesFilter(p1, "  ")).toBe(true);
  });
});

describe("chunk", () => {
  it("splits a list into pieces of at most the size, in order", () => {
    expect(CURVES_PER_REQUEST).toBe(100);
    const ids = Array.from({ length: 250 }, (_, i) => i);
    expect(chunk(ids, 100).map((c) => c.length)).toEqual([100, 100, 50]);
    expect(chunk(ids, 100)[2][0]).toBe(200);
    expect(chunk([], 100)).toEqual([]);
  });
});

describe("toggleRun", () => {
  const eight = ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"];

  it("adds a run up to 8 and removes one that is chosen", () => {
    expect(MAX_CURVE_RUNS).toBe(8);
    expect(toggleRun(["r1"], "r2")).toEqual(["r1", "r2"]);
    expect(toggleRun(eight, "r9")).toEqual(eight);
    expect(toggleRun(["r1", "r2"], "r1")).toEqual(["r2"]);
    expect(toggleRun(eight, "r8")).toEqual(eight.slice(0, 7));
  });
});
