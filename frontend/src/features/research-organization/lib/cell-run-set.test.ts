import { describe, expect, it } from "vitest";
import { focusedGroupKey } from "./cell-run-set";

describe("focusedGroupKey", () => {
  const protocol = { id: "proto", readout_definitions: [{ id: "rd" }, { id: "sp" }] };

  it("reads the split group of a clicked column of this protocol", () => {
    expect(focusedGroupKey("drc:rd:plot@cond:10 µM", protocol)).toBe("cond:10 µM");
    expect(focusedGroupKey("drc:rd:ic:50@run:r1", protocol)).toBe("run:r1");
    expect(focusedGroupKey("rd:proto:sp@cond:1 mM", protocol)).toBe("cond:1 mM");
  });

  it("has no group for other columns, other protocols or the overlay plot", () => {
    expect(focusedGroupKey("molecule", protocol)).toBeNull();
    expect(focusedGroupKey(undefined, protocol)).toBeNull();
    expect(focusedGroupKey("drc:rd:plot", protocol)).toBeNull();
    expect(focusedGroupKey("drc:rd:plot@overlay", protocol)).toBeNull();
    expect(focusedGroupKey("drc:other:plot@cond:10 µM", protocol)).toBeNull();
    expect(focusedGroupKey("rd:other:sp@cond:10 µM", protocol)).toBeNull();
  });
});
