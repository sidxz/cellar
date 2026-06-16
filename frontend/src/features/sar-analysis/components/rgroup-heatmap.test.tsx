import { describe, expect, it } from "vitest";
import { cellKey, heatmapReference } from "./rgroup-heatmap";

describe("rgroup-heatmap helpers", () => {
  it("cellKey is stable + collision-free", () => {
    expect(cellKey("F", "Cl")).toBe(cellKey("F", "Cl"));
    expect(cellKey("F", "Cl")).not.toBe(cellKey("Cl", "F"));
  });
  it("heatmapReference = min best_scalar across cells", () => {
    expect(
      heatmapReference([{ best_scalar: 5 }, { best_scalar: 0.1 }, { best_scalar: null }] as never),
    ).toBe(0.1);
  });
});
