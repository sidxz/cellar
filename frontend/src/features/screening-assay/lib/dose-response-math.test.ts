import { describe, expect, it } from "vitest";
import {
  computeReplicateStats,
  extractPoints,
  generate4PLCurve,
} from "./dose-response-math";

// ─── extractPoints ────────────────────────────────────────────────────────────

describe("extractPoints", () => {
  it("extracts concentration/response from raw_data-style objects", () => {
    const points = [
      { concentration: 0.1, response: 20 },
      { concentration: 1, response: 50 },
      { concentration: 10, response: 80 },
    ];
    const result = extractPoints(points);
    expect(result.x).toEqual([0.1, 1, 10]);
    expect(result.y).toEqual([20, 50, 80]);
    expect(result.reasons).toEqual([null, null, null]);
  });

  it("accepts x/y keys as well as concentration/response keys", () => {
    const points = [
      { x: 0.5, y: 35 },
      { x: 5, y: 65 },
    ];
    const { x, y } = extractPoints(points);
    expect(x).toEqual([0.5, 5]);
    expect(y).toEqual([35, 65]);
  });

  it("captures reason strings when present", () => {
    const points = [
      { concentration: 1, response: 50, reason: "auto_3sigma" },
      { concentration: 10, response: 80 },
    ];
    const { reasons } = extractPoints(points);
    expect(reasons[0]).toBe("auto_3sigma");
    expect(reasons[1]).toBeNull();
  });

  it("skips entries where concentration or response is not a number", () => {
    const points = [
      { concentration: "bad", response: 50 },
      { concentration: 1, response: null },
      { concentration: 0.1, response: 20 },
    ];
    const { x } = extractPoints(points);
    expect(x).toEqual([0.1]);
  });

  it("returns empty arrays for null input", () => {
    const result = extractPoints(null);
    expect(result.x).toEqual([]);
    expect(result.y).toEqual([]);
    expect(result.reasons).toEqual([]);
  });
});

// ─── computeReplicateStats ────────────────────────────────────────────────────

describe("computeReplicateStats", () => {
  it("returns empty arrays for empty input", () => {
    const result = computeReplicateStats([], []);
    expect(result.meanX).toEqual([]);
    expect(result.meanY).toEqual([]);
    expect(result.sdY).toEqual([]);
    expect(result.replicateX).toEqual([]);
    expect(result.replicateY).toEqual([]);
  });

  it("returns single points unchanged with zero SD for singletons", () => {
    const { meanX, meanY, sdY, replicateX } = computeReplicateStats([1, 10], [50, 80]);
    expect(meanX).toEqual([1, 10]);
    expect(meanY).toEqual([50, 80]);
    expect(sdY).toEqual([0, 0]);
    // No replicates for singleton groups
    expect(replicateX).toEqual([]);
  });

  it("groups replicates at the same concentration and computes mean + SD", () => {
    // Two replicates at 1 µM: 48 and 52 → mean 50, SD = sqrt(((48-50)^2+(52-50)^2)/(2-1)) = 2.828...
    const x = [1, 1];
    const y = [48, 52];
    const { meanX, meanY, sdY, replicateX, replicateY } = computeReplicateStats(x, y);
    expect(meanX).toHaveLength(1);
    expect(meanX[0]).toBe(1);
    expect(meanY[0]).toBeCloseTo(50, 8);
    expect(sdY[0]).toBeCloseTo(Math.sqrt(8), 6);
    // Both individual replicates are surfaced
    expect(replicateX).toEqual([1, 1]);
    expect(replicateY).toEqual([48, 52]);
  });

  it("handles a mix of singleton and replicate concentrations", () => {
    const x = [0.1, 1, 1, 10];
    const y = [10, 48, 52, 90];
    const { meanX, meanY } = computeReplicateStats(x, y);
    // Three distinct groups: 0.1, 1, 10
    expect(meanX).toHaveLength(3);
    // Group at 1: mean of [48,52] = 50
    const idx = meanX.indexOf(1);
    expect(meanY[idx]).toBeCloseTo(50, 8);
  });
});

// ─── generate4PLCurve ─────────────────────────────────────────────────────────

describe("generate4PLCurve", () => {
  // Only the fields consumed by generate4PLPoints / isDegenerateFit are needed;
  // cast to the full type so the rest of the suite doesn't need all required fields.
  const CURVE = {
    id: "test",
    top: 100,
    bottom: 0,
    fitted_value: 1,
    hill_slope: 1,
    curve_class: "full",
  } as Parameters<typeof generate4PLCurve>[0];

  it("returns non-empty parallel x/y arrays", () => {
    const { x, y } = generate4PLCurve(CURVE, 0.001, 1000);
    expect(x.length).toBeGreaterThan(0);
    expect(x.length).toBe(y.length);
  });

  it("x values span the requested range in log space", () => {
    const xMin = 0.001;
    const xMax = 1000;
    const { x } = generate4PLCurve(CURVE, xMin, xMax);
    expect(x[0]).toBeCloseTo(xMin, 8);
    expect(x[x.length - 1]).toBeCloseTo(xMax, 5);
  });

  it("produces a rising curve for hill_slope > 0", () => {
    const { y } = generate4PLCurve(CURVE, 0.001, 1000);
    expect(y[0]).toBeLessThan(y[y.length - 1]);
  });

  it("y midpoint is near 50 at the EC50 concentration", () => {
    // At x = fitted_value = 1, the 4PL evaluates to exactly (top + bottom) / 2 = 50
    const { x, y } = generate4PLCurve(CURVE, 0.001, 1000);
    const midIdx = x.findIndex((v) => Math.abs(v - 1) < 0.01);
    expect(y[midIdx]).toBeCloseTo(50, 0);
  });
});
