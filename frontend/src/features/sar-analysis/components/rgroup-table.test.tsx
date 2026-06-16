import { describe, expect, it } from "vitest";
import {
  buildActivityColumns,
  canSaveAll,
  pickReference,
  potencyShade,
  saveAllLabel,
} from "./rgroup-table";

const SPEC = {
  protocolId: "p",
  column: "drc:rd",
  interceptKey: null,
  source: "dr_curve",
  label: "IC50",
} as const;

describe("rgroup-table pure helpers (kept)", () => {
  it("pickReference = min non-null (most potent)", () => {
    expect(pickReference([5, null, 0.2, 1])).toBe(0.2);
    expect(pickReference([null, null])).toBeNull();
  });

  it("potencyShade greens the reference, reds far-off", () => {
    expect(potencyShade(0.2, 0.2)).toContain("green");
    expect(potencyShade(50, 0.2)).toContain("red");
    expect(potencyShade(null, 0.2)).toBe("");
  });

  it("buildActivityColumns reads row.activity + shades dr_curve by the server reference", () => {
    const cols = buildActivityColumns(SPEC, 0.2);
    const valueCol = cols.find((c) => c.colId === "activity:value");
    expect(valueCol?.headerName).toBe("IC50");
    // value getter pulls the per-row scalar (ColDef.valueGetter is `string | func`;
    // narrow with typeof so the call is type-safe, matching the repo convention).
    const getter = valueCol?.valueGetter;
    expect(typeof getter).toBe("function");
    const got =
      typeof getter === "function" ? getter({ data: { activity: 1.0 } } as never) : undefined;
    expect(got).toBe(1.0);
    // cellClass present for dr_curve (shading), absent for readout_data
    expect(valueCol?.cellClass).toBeDefined();
    const ro = buildActivityColumns({ ...SPEC, source: "readout_data" }, 0.2).find(
      (c) => c.colId === "activity:value",
    );
    expect(ro?.cellClass).toBeUndefined();
  });
});

describe("save-all toolbar action helpers", () => {
  it("labels matched vs filtered by filter state", () => {
    expect(saveAllLabel(1234, false)).toBe("Save all 1234 matched");
    expect(saveAllLabel(320, true)).toBe("Save 320 filtered");
    expect(saveAllLabel(null, false)).toBe("Save all 0 matched");
  });
  it("canSaveAll gates null/zero", () => {
    expect(canSaveAll(5)).toBe(true);
    expect(canSaveAll(0)).toBe(false);
    expect(canSaveAll(null)).toBe(false);
  });
});
