import { describe, expect, it } from "vitest";
import { pointInPolygon, idsInsidePolygon } from "./lasso-math";

const SQUARE = [
  { x: 0, y: 0 },
  { x: 0, y: 10 },
  { x: 10, y: 10 },
  { x: 10, y: 0 },
];

describe("pointInPolygon", () => {
  it("returns true for clearly inside", () => {
    expect(pointInPolygon({ x: 5, y: 5 }, SQUARE)).toBe(true);
  });

  it("returns false for clearly outside", () => {
    expect(pointInPolygon({ x: 50, y: 50 }, SQUARE)).toBe(false);
  });

  it("handles concave polygon", () => {
    const C = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 5, y: 5 },
      { x: 0, y: 10 },
    ];
    expect(pointInPolygon({ x: 5, y: 8 }, C)).toBe(false);
    expect(pointInPolygon({ x: 2, y: 2 }, C)).toBe(true);
  });
});

describe("idsInsidePolygon", () => {
  it("filters points by polygon membership", () => {
    const points = [
      { moleculeId: "a", x: 5, y: 5 },
      { moleculeId: "b", x: 100, y: 100 },
      { moleculeId: "c", x: 2, y: 8 },
    ];
    const ids = idsInsidePolygon(points, SQUARE);
    expect(new Set(ids)).toEqual(new Set(["a", "c"]));
  });
});
