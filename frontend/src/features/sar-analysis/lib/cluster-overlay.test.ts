import { describe, expect, it } from "vitest";
import { buildOverlayTraces } from "./cluster-overlay";

const points = [
  { moleculeId: "a", x: 0, y: 0 },
  { moleculeId: "b", x: 1, y: 1 },
  { moleculeId: "c", x: 2, y: 2 },
];

describe("buildOverlayTraces", () => {
  it("returns no traces when both sets are empty", () => {
    expect(buildOverlayTraces(points, new Set(), new Set(), "scatter")).toEqual([]);
  });

  it("emits a basket trace at the basket members' coordinates", () => {
    const traces = buildOverlayTraces(points, new Set(["a", "c"]), new Set(), "scatter");
    expect(traces).toHaveLength(1);
    expect(traces[0].x).toEqual([0, 2]);
    expect(traces[0].y).toEqual([0, 2]);
  });

  it("emits a region-candidate trace when regionPickIds set", () => {
    const traces = buildOverlayTraces(points, new Set(), new Set(["b"]), "scatter");
    expect(traces).toHaveLength(1);
    expect(traces[0].x).toEqual([1]);
  });

  it("emits both traces (basket first, then candidates)", () => {
    const traces = buildOverlayTraces(points, new Set(["a"]), new Set(["b"]), "scattergl");
    expect(traces).toHaveLength(2);
    expect(traces[0].type as string).toBe("scattergl");
    expect(traces[1].type as string).toBe("scattergl");
  });
});
