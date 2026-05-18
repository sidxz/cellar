import { describe, expect, it } from "vitest";
import { colorForPoint } from "./cluster-palette";

describe("colorForPoint", () => {
  it("returns palette color for cluster mode", () => {
    const c = colorForPoint(
      { mode: "cluster" },
      { clusterId: 0, activityPic50: null, scaffoldId: null },
    );
    expect(c).toMatch(/^#/);
  });

  it("returns grey for none mode", () => {
    expect(
      colorForPoint(
        { mode: "none" },
        { clusterId: 0, activityPic50: null, scaffoldId: null },
      ),
    ).toBe("#a1a1aa");
  });

  it("returns hollow ring fill for activity mode with no curve", () => {
    const c = colorForPoint(
      { mode: "activity", protocolId: "p1" },
      { clusterId: 0, activityPic50: null, scaffoldId: null },
    );
    expect(c).toBe("transparent");
  });

  it("returns gradient color for activity with pIC50", () => {
    const c = colorForPoint(
      { mode: "activity", protocolId: "p1" },
      { clusterId: 0, activityPic50: 7.0, scaffoldId: null },
    );
    expect(c).toMatch(/^#/);
  });
});
