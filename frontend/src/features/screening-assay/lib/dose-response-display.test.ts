import { describe, expect, it } from "vitest";
import { generate4PLFromData } from "./dose-response-display";

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
