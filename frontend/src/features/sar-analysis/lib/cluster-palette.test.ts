import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { colorForPoint } from "./cluster-palette";

const paint = (over: Partial<Parameters<typeof colorForPoint>[1]> = {}) => ({
  clusterId: 0,
  activityPic50: null,
  scaffoldId: null,
  ...over,
});

describe("colorForPoint", () => {
  it("gives each cluster its own colour, cycling through the palette", () => {
    const cluster = (clusterId: number) => colorForPoint({ mode: "cluster" }, paint({ clusterId }));
    expect(cluster(0)).not.toBe(cluster(1));
    expect(cluster(GROUP_PALETTE.length)).toBe(cluster(0));
  });

  it("paints every point alike in none mode", () => {
    expect(colorForPoint({ mode: "none" }, paint({ clusterId: 5, scaffoldId: "s1" }))).toBe(
      colorForPoint({ mode: "none" }, paint()),
    );
  });

  it("returns hollow ring fill for activity mode with no curve", () => {
    const c = colorForPoint({ mode: "activity", protocolId: "p1" }, paint());
    expect(c).toBe("transparent");
  });

  it("gives each activity bin its own colour", () => {
    const activity = (activityPic50: number) =>
      colorForPoint({ mode: "activity", protocolId: "p1" }, paint({ activityPic50 }));
    const bins = [8.5, 7.0, 5.5, 4.0].map(activity);
    expect(new Set(bins).size).toBe(4);
    expect(activity(9.5)).toBe(activity(8.5));
  });
});
