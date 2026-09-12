import { describe, expect, it } from "vitest";
import { extractPoints } from "./dose-response-math";

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
