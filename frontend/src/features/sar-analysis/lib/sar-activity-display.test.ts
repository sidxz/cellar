import { describe, expect, it } from "vitest";
import { pickReference, potencyShade } from "./sar-activity-display";

describe("sar-activity-display potency helpers", () => {
  it("pickReference = min non-null (most potent)", () => {
    expect(pickReference([5, null, 0.2, 1])).toBe(0.2);
    expect(pickReference([null, null])).toBeNull();
  });

  it("potencyShade greens the reference, reds far-off", () => {
    expect(potencyShade(0.2, 0.2)).toContain("green");
    expect(potencyShade(50, 0.2)).toContain("red");
    expect(potencyShade(null, 0.2)).toBe("");
  });
});
