import { describe, expect, it } from "vitest";
import { curveFrame } from "./curve-frame";

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

  it("leaves both axes to the chart when there are no usable points", () => {
    expect(curveFrame([null, undefined, []], { percent: true })).toEqual({
      xRange: undefined,
      yRange: undefined,
    });
  });
});
