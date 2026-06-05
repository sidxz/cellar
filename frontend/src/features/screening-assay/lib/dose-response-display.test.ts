import { describe, expect, it } from "vitest";
import { evaluate4PL, generate4PLFromData, generate4PLPoints } from "./dose-response-display";

/**
 * Pin the 4PL Hill convention to GraphPad Prism (matches backend
 * ``infrastructure/lmfit/curve_fitter.py``):
 *
 *     y = bottom + (top - bottom) / (1 + 10^((logEC50 - log(c)) * hill))
 *
 * - hill > 0 ⇒ RISING curve (response increases with dose)
 * - hill < 0 ⇒ FALLING curve
 *
 * A second copy of this evaluator used to live in
 * ``research-organization/lib/curve-math.ts`` with the Hill sign inverted —
 * making search-results curves render flipped relative to the protocol view.
 * That copy is gone; this test guards against re-introducing the same bug
 * if someone re-implements the math closer to a consumer.
 */
describe("evaluate4PL — Prism convention", () => {
  const RISING = { top: 100, bottom: 0, fitted_value: 1, hill_slope: 1 };
  const FALLING = { top: 100, bottom: 0, fitted_value: 1, hill_slope: -1 };

  it("hill > 0 produces a rising curve", () => {
    const yLow = evaluate4PL(Math.log10(0.01), RISING);
    const yMid = evaluate4PL(Math.log10(1), RISING);
    const yHigh = evaluate4PL(Math.log10(100), RISING);
    expect(yLow).toBeLessThan(yMid);
    expect(yMid).toBeLessThan(yHigh);
  });

  it("hill < 0 produces a falling curve", () => {
    const yLow = evaluate4PL(Math.log10(0.01), FALLING);
    const yMid = evaluate4PL(Math.log10(1), FALLING);
    const yHigh = evaluate4PL(Math.log10(100), FALLING);
    expect(yLow).toBeGreaterThan(yMid);
    expect(yMid).toBeGreaterThan(yHigh);
  });

  it("y crosses (top + bottom) / 2 at the EC50 for hill ≠ 0", () => {
    expect(evaluate4PL(Math.log10(1), RISING)).toBeCloseTo(50, 6);
    expect(evaluate4PL(Math.log10(1), FALLING)).toBeCloseTo(50, 6);
  });

  it("approaches the asymptotes far from the EC50", () => {
    expect(evaluate4PL(Math.log10(1e-9), RISING)).toBeCloseTo(0, 6);
    expect(evaluate4PL(Math.log10(1e9), RISING)).toBeCloseTo(100, 6);
  });
});

describe("generate4PLPoints", () => {
  const PARAMS = { top: 100, bottom: 0, fitted_value: 1, hill_slope: 1 };

  it("emits n samples spanning [xMin, xMax] in log space", () => {
    const { x, y, logX } = generate4PLPoints(PARAMS, 0.001, 1000, 11);
    expect(x).toHaveLength(11);
    expect(y).toHaveLength(11);
    expect(logX).toHaveLength(11);
    expect(x[0]).toBeCloseTo(0.001, 8);
    expect(x[x.length - 1]).toBeCloseTo(1000, 6);
  });

  it("y values increase monotonically for a rising curve", () => {
    const { y } = generate4PLPoints(PARAMS, 0.001, 1000, 50);
    for (let i = 1; i < y.length; i++) {
      expect(y[i]).toBeGreaterThanOrEqual(y[i - 1]);
    }
  });

  it("agrees with evaluate4PL pointwise", () => {
    const { x, y } = generate4PLPoints(PARAMS, 0.01, 100, 25);
    for (let i = 0; i < x.length; i++) {
      expect(y[i]).toBeCloseTo(evaluate4PL(Math.log10(x[i]), PARAMS), 9);
    }
  });
});

describe("generate4PLFromData — compact-renderer wrapper", () => {
  const PARAMS = { top: 100, bottom: 0, fitted_value: 1, hill_slope: 1 };
  const RAW = [
    { x: 0.01, y: 5 },
    { x: 0.1, y: 18 },
    { x: 1, y: 50 },
    { x: 10, y: 82 },
    { x: 100, y: 95 },
  ];

  it("renders a rising curve when hill > 0 (search results match protocol view)", () => {
    const { x, y } = generate4PLFromData(PARAMS, RAW, { numPoints: 30, rangeExtension: 0.3 });
    expect(x.length).toBeGreaterThan(0);
    expect(y[0]).toBeLessThan(y[y.length - 1]);
  });

  it("returns empty arrays for a degenerate fit (fitted_value = 0)", () => {
    const degenerate = { ...PARAMS, fitted_value: 0 };
    const result = generate4PLFromData(degenerate, RAW);
    expect(result.x).toEqual([]);
    expect(result.y).toEqual([]);
  });

  it("returns empty arrays when fewer than 2 positive raw x-values", () => {
    expect(generate4PLFromData(PARAMS, [{ x: 1, y: 10 }]).x).toEqual([]);
    expect(generate4PLFromData(PARAMS, []).x).toEqual([]);
    expect(
      generate4PLFromData(PARAMS, [
        { x: -1, y: 10 },
        { x: 0, y: 5 },
      ]).x,
    ).toEqual([]);
  });
});
