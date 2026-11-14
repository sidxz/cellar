import { beforeEach, describe, expect, it } from "vitest";
import { shownPlotLayout, useReportConfig } from "./use-report-config";

const load = (columns: Record<string, unknown> | null) =>
  useReportConfig.getState().loadFromSavedSearch(columns);
const layout = () => useReportConfig.getState().config.plotLayout;

describe("plot layout", () => {
  beforeEach(() => load(null));

  it("defaults to side by side", () => {
    expect(layout()).toBe("side_by_side");
  });

  it("opens a saved search from before the option side by side", () => {
    load({ reportConfig: { displayPreset: "curves" } });
    expect(layout()).toBe("side_by_side");
  });

  it("restores an overlaid saved search", () => {
    load({ reportConfig: { plotLayout: "overlay" } });
    expect(layout()).toBe("overlay");
  });

  it("treats an unknown value as side by side", () => {
    load({ reportConfig: { plotLayout: "stacked" } });
    expect(layout()).toBe("side_by_side");
  });
});

describe("shownPlotLayout", () => {
  it("overlays only in the Curves display, where plots show", () => {
    const base = {
      imageSize: "small" as const,
      visibleFields: { structure: [], properties: [], molecule: [] },
    };
    expect(shownPlotLayout({ ...base, displayPreset: "curves", plotLayout: "overlay" })).toBe(
      "overlay",
    );
    expect(shownPlotLayout({ ...base, displayPreset: "compact", plotLayout: "overlay" })).toBe(
      "side_by_side",
    );
    expect(shownPlotLayout({ ...base, displayPreset: "structure", plotLayout: "overlay" })).toBe(
      "side_by_side",
    );
  });
});
