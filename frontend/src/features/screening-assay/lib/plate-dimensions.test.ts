import { describe, expect, it } from "vitest";
import { holderDimensions } from "./plate-dimensions";

describe("holderDimensions", () => {
  it("uses the holder's own size when both are set", () => {
    expect(holderDimensions({ format: "", holder_rows: 2, holder_columns: 3 })).toEqual([2, 3]);
  });
  it("falls back to the plate format", () => {
    expect(holderDimensions({ format: "384", holder_rows: null, holder_columns: null })).toEqual([
      16, 24,
    ]);
  });
});
