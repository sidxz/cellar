import { describe, expect, it } from "vitest";
import {
  pointInPolygon,
  idsInsidePolygon,
  selectedIdsFromPlotlyEvent,
  hasSelectionGeometry,
} from "./lasso-math";

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

describe("selectedIdsFromPlotlyEvent", () => {
  const points = [
    { moleculeId: "a", x: 0, y: 0 },
    { moleculeId: "b", x: 10, y: 10 },
  ];

  it("resolves ids from a lasso polygon (lassoPoints, data space)", () => {
    const ev = { lassoPoints: { x: [-1, 1, 1, -1], y: [-1, -1, 1, 1] } };
    expect(selectedIdsFromPlotlyEvent(ev, points)).toEqual(["a"]);
  });

  it("resolves ids from a box selection (range corners)", () => {
    const ev = { range: { x: [-1, 1], y: [-1, 1] } };
    expect(selectedIdsFromPlotlyEvent(ev, points)).toEqual(["a"]);
  });

  it("falls back to pointNumber indexing on the base trace", () => {
    const ev = { points: [{ curveNumber: 0, pointNumber: 1 }] };
    expect(selectedIdsFromPlotlyEvent(ev, points)).toEqual(["b"]);
  });

  it("ignores non-base-trace points in the fallback path", () => {
    const ev = { points: [{ curveNumber: 1, pointNumber: 0 }] };
    expect(selectedIdsFromPlotlyEvent(ev, points)).toEqual([]);
  });

  it("returns [] for null / empty event", () => {
    expect(selectedIdsFromPlotlyEvent(null, points)).toEqual([]);
    expect(selectedIdsFromPlotlyEvent({}, points)).toEqual([]);
  });
});

describe("hasSelectionGeometry", () => {
  it("is true for a lasso event (lassoPoints present)", () => {
    expect(
      hasSelectionGeometry({ lassoPoints: { x: [0, 1, 2], y: [0, 1, 2] } }),
    ).toBe(true);
  });

  it("is true for a box event (range present)", () => {
    expect(hasSelectionGeometry({ range: { x: [0, 1], y: [0, 1] } })).toBe(true);
  });

  it("is FALSE for the geometry-less redraw artifact (empty points, no lassoPoints/range)", () => {
    // This is the exact shape Plotly re-emits after a Plotly.react redraw.
    expect(hasSelectionGeometry({ points: [] } as any)).toBe(false);
  });

  it("is false for null / undefined / empty", () => {
    expect(hasSelectionGeometry(null)).toBe(false);
    expect(hasSelectionGeometry(undefined)).toBe(false);
    expect(hasSelectionGeometry({})).toBe(false);
  });
});
