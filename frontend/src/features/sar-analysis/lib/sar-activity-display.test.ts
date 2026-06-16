import { describe, expect, it } from "vitest";
import { potencyShade } from "./sar-activity-display";

describe("sar-activity-display potency helpers", () => {
  it("potencyShade greens the reference, reds far-off", () => {
    expect(potencyShade(0.2, 0.2)).toContain("green");
    expect(potencyShade(50, 0.2)).toContain("red");
    expect(potencyShade(null, 0.2)).toBe("");
  });
});
