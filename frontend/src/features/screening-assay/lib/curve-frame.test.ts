import { describe, expect, it } from "vitest";
import { curveFrame, curveLayer, percentYRange } from "./curve-frame";

const halfDecade = Math.sqrt(10);

describe("curveFrame", () => {
  it("spans every curve's tested doses, half a decade either side", () => {
    const frame = curveFrame(
      [
        [
          { x: 0.001, y: 5 },
          { x: 1, y: 50 },
        ],
        [
          { x: 0.01, y: 10 },
          { x: 100, y: 90 },
        ],
      ],
      { percent: true },
    );
    expect(frame.xRange?.[0]).toBeCloseTo(0.001 / halfDecade, 12);
    expect(frame.xRange?.[1]).toBeCloseTo(100 * halfDecade, 9);
  });

  it("keeps 0 % and 100 % in a % frame even when the data sits inside them", () => {
    const frame = curveFrame(
      [
        [
          { x: 1, y: 90 },
          { x: 10, y: 95 },
        ],
      ],
      { percent: true },
    );
    expect(frame.yRange).toEqual([-10, 110]);
  });

  it("widens a % frame so no point is clipped", () => {
    const frame = curveFrame([[{ x: 1, y: -20 }], [{ x: 2, y: 130 }]], { percent: true });
    expect(frame.yRange).toEqual([-35, 145]);
  });

  it("fits a raw-signal frame to the data with a 5 % margin", () => {
    const frame = curveFrame(
      [
        [
          { x: 1, y: 1000 },
          { x: 10, y: 3000 },
        ],
      ],
      { percent: false },
    );
    expect(frame.yRange).toEqual([900, 3100]);
  });

  it("gives a flat raw-signal series a visible band", () => {
    const frame = curveFrame(
      [
        [
          { x: 1, y: 200 },
          { x: 10, y: 200 },
        ],
      ],
      { percent: false },
    );
    expect(frame.yRange).toEqual([190, 210]);
  });

  it("ignores non-finite values and non-positive doses", () => {
    const frame = curveFrame(
      [
        [
          { x: 0, y: 500 },
          { x: -1, y: 50 },
          { x: 1, y: Number.NaN },
          { x: 10, y: 40 },
        ],
      ],
      { percent: true },
    );
    expect(frame.xRange?.[0]).toBeCloseTo(10 / halfDecade, 9);
    expect(frame.yRange).toEqual([-10, 110]);
  });

  it("reads curve rows stored as concentration / response", () => {
    const frame = curveFrame([[{ concentration: 1, response: 150 }]], { percent: true });
    expect(frame.xRange?.[0]).toBeCloseTo(1 / halfDecade, 12);
    expect(frame.yRange).toEqual([-15, 165]);
  });

  it("leaves both axes to the chart when there are no usable points", () => {
    expect(curveFrame([null, undefined, []], { percent: true })).toEqual({
      xRange: undefined,
      yRange: undefined,
    });
  });
});

describe("curveLayer", () => {
  const readouts = [
    { name: "Signal", normalizations: ["none", "percent_inhibition", "z_score"] },
    { name: "Raw", normalizations: [] },
    {
      name: "IC50",
      dose_response_config: { y_readout_name: "Signal", y_normalization: "z_score" },
    },
    { name: "EC50", dose_response_config: { y_readout_name: "Signal", y_normalization: null } },
    { name: "Raw fit", dose_response_config: { y_readout_name: "Raw", y_normalization: null } },
  ];

  it("is the layer the curve names", () => {
    expect(curveLayer(readouts, "IC50")).toBe("z_score");
  });

  it("falls back to the Y readout's first calculated layer", () => {
    expect(curveLayer(readouts, "EC50")).toBe("percent_inhibition");
  });

  it("is null for a curve on raw values or an unknown curve", () => {
    expect(curveLayer(readouts, "Raw fit")).toBeNull();
    expect(curveLayer(readouts, "nope")).toBeNull();
  });

  it("takes the protocol's first curve when no name is given", () => {
    expect(curveLayer(readouts)).toBe("z_score");
  });
});

describe("percentYRange", () => {
  const pct = (y: number, excludedY?: number) => ({
    fitted_layer: "percent_inhibition",
    raw_data: [{ concentration: 1, response: y }],
    excluded_points: excludedY == null ? null : [{ concentration: 2, response: excludedY }],
  });

  it("keeps the 0 % and 100 % anchors and every point, excluded ones too", () => {
    expect(percentYRange([pct(90)])).toEqual([-10, 110]);
    expect(percentYRange([pct(90, 130)])).toEqual([-13, 143]);
  });

  it("leaves a chart with any non-% curve, or no curve, to frame itself", () => {
    expect(
      percentYRange([pct(90), { fitted_layer: null, raw_data: [{ x: 1, y: 900 }] }]),
    ).toBeUndefined();
    expect(percentYRange([])).toBeUndefined();
  });
});
