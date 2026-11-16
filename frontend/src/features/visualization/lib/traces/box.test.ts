import { WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { buildBoxFigure } from "./box";
import { dataset, panel, pass, traces } from "./test-fixtures";

const ds = () =>
  dataset({
    well_type: ["sample", "sample", "negative_control", "sample", "negative_control"],
    y: [1, 2, 3, 0, 5],
  });
const cfg = (patch = {}) => panel("box", { category: "well_type", y: "y", ...patch });

describe("buildBoxFigure", () => {
  it("draws one box per category with every point shown, in well-type colors", () => {
    const fig = buildBoxFigure(ds(), cfg(), pass(5));
    expect(traces(fig).map((t) => [t.type, t.name, t.y, t.boxpoints, t.marker.color])).toEqual([
      ["box", "Negative control", [3, 5], "all", WELL_TYPE_COLORS.negative_control],
      ["box", "Sample", [1, 2, 0], "all", WELL_TYPE_COLORS.sample],
    ]);
    expect(fig.layout.xaxis).toMatchObject({ type: "category" });
  });

  it("leaves out rows that fail the filters", () => {
    const fig = buildBoxFigure(ds(), cfg(), Uint8Array.from([1, 0, 1, 1, 0]));
    expect(traces(fig).map((t) => t.y)).toEqual([[3], [1, 0]]);
  });

  it("labels a log axis and notes values it cannot show", () => {
    const fig = buildBoxFigure(ds(), cfg({ logY: true }), pass(5));
    expect(fig.layout.yaxis).toMatchObject({ type: "log", title: { text: "Signal (log)" } });
    expect(fig.skipped).toBe(1);
    expect(fig.note).toBe("1 row lacks Signal");
  });
});
