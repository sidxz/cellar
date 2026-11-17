import { buildDoseResponsePlot } from "@structflo/components/dose-response";
import { describe, expect, it } from "vitest";
import { editablePoints, generate4PLFromData, placeExclusions } from "./dose-response-display";

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

describe("one point order for a curve's entries", () => {
  // The auto-fit left the 0.1 µM point out (its well is flagged) and suggests the 1 µM point:
  // captured set 0.01, 0.1 (flag), 1 (suggestion), 10, 100, 1000.
  const raw = [0.01, 1, 10, 100, 1000].map((c, i) => ({ concentration: c, response: i * 20 }));
  const flag = {
    idx: 1,
    source: "well_flag",
    excluded: true,
    reason: "outlier_well",
    concentration: 0.1,
    response: -40,
  };
  const suggestion = (idx: number) => ({
    idx,
    source: "auto_3sigma",
    excluded: false,
    reason: "auto_3sigma",
    concentration: 1,
    response: 20,
  });
  const curve = (idx: number) => ({
    id: "c1",
    fitted_value: 1,
    top: 100,
    bottom: 0,
    hill_slope: 1,
    raw_data: raw,
    excluded_points: [flag, suggestion(idx)],
  });

  it.each([
    ["its captured position", 2],
    ["the raw_data index an earlier fit stored", 1],
  ])("puts a suggestion stored at %s on its own point, once", (_, idx) => {
    const { captured, exclusions } = editablePoints(curve(idx));

    expect(captured.map((p) => p.concentration)).toEqual([0.01, 0.1, 1, 10, 100, 1000]);
    expect(exclusions.map((e) => [e.source, e.idx])).toEqual([
      ["well_flag", 1],
      ["auto_3sigma", 2],
    ]);
  });

  it("gives the chart's suggestion halo the index the edit session and the backend use", () => {
    const { traces, traceIndexToCurve } = buildDoseResponsePlot([placeExclusions(curve(2))], {
      showCI: false,
      showMarker: false,
      showPlateaus: false,
      interactive: true,
      editMode: true,
      editCurveId: "c1",
    });
    const halo = traceIndexToCurve.findIndex((t) => t?.type === "suggestion");

    expect(traces[halo].x).toEqual([1]);
    expect(traceIndexToCurve[halo].capturedIdxOrder).toEqual([2]);
  });
});
