import { describe, expect, it } from "vitest";

import { proposeWindows, windowLabel } from "./window-proposal";

describe("proposeWindows", () => {
  it("splits the trace at the midpoint between neighboring peaks", () => {
    expect(proposeWindows([71.3, 36.6], [25, 95], [])).toEqual([
      { peak: 36.6, low: 25, high: 54 },
      { peak: 71.3, low: 54, high: 95 },
    ]);
  });

  it("gives a single peak the whole trace, rounded to 0.1", () => {
    expect(proposeWindows([61.2], [25.04, 94.96], [])).toEqual([{ peak: 61.2, low: 25, high: 95 }]);
  });

  it("gives a peak inside an existing window no row, limits included", () => {
    const existing = [{ low: 50, high: 85 }];
    expect(proposeWindows([36.6, 71.3], [25, 95], existing).map((w) => w.peak)).toEqual([36.6]);
    expect(proposeWindows([50, 85], [25, 95], existing)).toEqual([]);
  });

  it("cuts a range back to an existing window's limit where they would overlap", () => {
    // The neighbor inside 50–85 still sets the midpoint (54), then 50 cuts it back.
    expect(proposeWindows([36.6, 71.3], [25, 95], [{ low: 50, high: 85 }])).toEqual([
      { peak: 36.6, low: 25, high: 50 },
    ]);
    // An existing window between two peaks cuts both sides.
    expect(proposeWindows([40, 80], [25, 95], [{ low: 55, high: 65 }])).toEqual([
      { peak: 40, low: 25, high: 55 },
      { peak: 80, low: 65, high: 95 },
    ]);
  });

  it("proposes nothing without a peak", () => {
    expect(proposeWindows([], [25, 95], [])).toEqual([]);
  });
});

describe("windowLabel", () => {
  it("names the window with its range", () => {
    expect(windowLabel({ window: "Main", low: 50, high: 85 })).toBe("Main 50–85 °C");
  });
});
