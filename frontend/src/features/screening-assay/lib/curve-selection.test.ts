import { describe, expect, it } from "vitest";

import { EMPTY_SELECTION, applyClick, assignColourSlots, selectAll } from "./curve-selection";

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
