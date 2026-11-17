import { CHART_COLORS, WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { buildHistogramFigure } from "./histogram";
import { dataset, panel, pass, traces } from "./test-fixtures";

const types = ["sample", "sample", "negative_control", "positive_control", "sample", "sample"];
const ds = () => dataset({ y: [0, 10, 20, 30, null, 100], well_type: types });

describe("buildHistogramFigure", () => {
  it("keeps the bins of the whole column when filters change", () => {
    const cfg = panel("histogram", { x: "y", bins: 10 });
    const all = traces(buildHistogramFigure(ds(), cfg, pass(6)));
    const some = traces(buildHistogramFigure(ds(), cfg, Uint8Array.from([1, 1, 1, 1, 1, 0])));
    expect(all[0].x).toHaveLength(10);
    expect(some[0].x).toEqual(all[0].x);
    expect(some[0].width).toBe(all[0].width);
    expect(all[0].y).toEqual([1, 1, 1, 1, 0, 0, 0, 0, 0, 1]);
    expect(some[0].y).toEqual([1, 1, 1, 1, 0, 0, 0, 0, 0, 0]);
  });

  it("stacks one trace per well type in its color", () => {
    const cfg = panel("histogram", { x: "y", bins: 10, appearance: { colorBy: "well_type" } });
    const fig = buildHistogramFigure(ds(), cfg, pass(6));
    expect(fig.layout.barmode).toBe("stack");
    const byName = Object.fromEntries(traces(fig).map((t) => [t.name, t.marker.color]));
    expect(byName).toEqual({
      Sample: WELL_TYPE_COLORS.sample,
      "Negative control": WELL_TYPE_COLORS.negative_control,
      "Positive control": WELL_TYPE_COLORS.positive_control,
    });
    const sample = traces(fig).find((t) => t.name === "Sample");
    expect(sample?.y).toEqual([1, 1, 0, 0, 0, 0, 0, 0, 0, 1]);
  });

  it("draws one unstacked series when colored by nothing", () => {
    const fig = buildHistogramFigure(ds(), panel("histogram", { x: "y" }), pass(6));
    expect(traces(fig)).toHaveLength(1);
    expect(traces(fig)[0].marker.color).toBe(CHART_COLORS.primary);
    expect(traces(fig)[0].x).toHaveLength(30);
  });

  it("notes passing rows that lack the value, ignoring failing ones", () => {
    const cfg = panel("histogram", { x: "y" });
    expect(buildHistogramFigure(ds(), cfg, pass(6)).note).toBe("1 row lacks Signal");
    expect(buildHistogramFigure(ds(), cfg, Uint8Array.from([1, 1, 1, 1, 0, 1])).note).toBeNull();
  });

  it("separates bars with the card color of the theme", () => {
    const cfg = panel("histogram", { x: "y" });
    const edge = (dark: boolean) =>
      (buildHistogramFigure(ds(), cfg, pass(6), dark).data[0].marker as { line: { color: string } })
        .line.color;
    expect(edge(false)).not.toBe(edge(true));
  });
});
