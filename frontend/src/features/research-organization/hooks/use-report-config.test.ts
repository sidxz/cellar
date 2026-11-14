import { beforeEach, describe, expect, it } from "vitest";
import { shownPlotLayout, useReportConfig } from "./use-report-config";

const load = (columns: Record<string, unknown> | null) =>
  useReportConfig.getState().loadFromSavedSearch(columns);
const layout = () => useReportConfig.getState().config.plotLayout;
const preset = () => useReportConfig.getState().config.displayPreset;

describe("plot layout", () => {
  beforeEach(() => load(null));

  it("defaults to separate plots", () => {
    expect(layout()).toBe("side_by_side");
  });

  it("opens a saved search from before the option with separate plots", () => {
    load({ reportConfig: { displayPreset: "curves" } });
    expect(layout()).toBe("side_by_side");
  });

  it("restores an overlaid saved search", () => {
    load({ reportConfig: { plotLayout: "overlay" } });
    expect(layout()).toBe("overlay");
  });

  it("treats an unknown value as separate plots", () => {
    load({ reportConfig: { plotLayout: "stacked" } });
    expect(layout()).toBe("side_by_side");
  });
});

describe("display preset", () => {
  it("starts in the Detailed display with medium structures", () => {
    load(null);
    expect(preset()).toBe("detailed");
    expect(useReportConfig.getState().config.imageSize).toBe("medium");
  });

  it("opens searches saved in the old Structure and Curves displays as Detailed", () => {
    load({ reportConfig: { displayPreset: "structure" } });
    expect(preset()).toBe("detailed");
    load({ reportConfig: { displayPreset: "curves" } });
    expect(preset()).toBe("detailed");
    load({ reportConfig: {} });
    expect(preset()).toBe("detailed");
  });

  it("keeps a search saved as Compact compact", () => {
    load({ reportConfig: { displayPreset: "compact" } });
    expect(preset()).toBe("compact");
  });
});

describe("shownPlotLayout", () => {
  it("overlays only in the Detailed display, where plots show", () => {
    const base = {
      imageSize: "small" as const,
      visibleFields: { structure: [], properties: [], molecule: [] },
    };
    expect(shownPlotLayout({ ...base, displayPreset: "detailed", plotLayout: "overlay" })).toBe(
      "overlay",
    );
    expect(shownPlotLayout({ ...base, displayPreset: "compact", plotLayout: "overlay" })).toBe(
      "side_by_side",
    );
  });
});
