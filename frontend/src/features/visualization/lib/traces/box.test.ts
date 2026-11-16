import { WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { buildBoxFigure } from "./box";
import { MAX_CATEGORIES } from "./common";
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

  it("hands point and box hovers to the panel's card, each point carrying its row", () => {
    const fig = buildBoxFigure(ds(), cfg(), pass(5));
    expect(fig.data.map((t) => [t.hoverinfo, t.customdata, t.text])).toEqual([
      ["none", [2, 4], undefined],
      ["none", [0, 1, 3], undefined],
    ]);
    // A box mean would add an eighth hover value: the card reads exactly seven.
    expect(fig.data.map((t) => t.boxmean)).toEqual([undefined, undefined]);
  });

  it("leaves out rows that fail the filters", () => {
    const fig = buildBoxFigure(ds(), cfg(), Uint8Array.from([1, 0, 1, 1, 0]));
    expect(traces(fig).map((t) => t.y)).toEqual([[3], [1, 0]]);
  });

  it("leaves censored values out of the boxes and says how many", () => {
    const d = dataset({
      well_type: ["sample", "sample", "sample"],
      y: [1, 2, 50],
      "y:q": [null, null, ">"],
    });
    const fig = buildBoxFigure(d, cfg(), pass(3));
    expect(traces(fig).map((t) => t.y)).toEqual([[1, 2]]);
    expect(fig.note).toBe("1 censored value not included");
  });

  it("caps a 100k-compound group at the category limit", () => {
    const N = 100_000;
    const rows = Array.from({ length: N }, (_, i) => i);
    const d = dataset({ compound: rows.map((i) => `CEL-${i}`), y: rows });
    const start = performance.now();
    const fig = buildBoxFigure(d, cfg({ category: "compound" }), pass(N));
    expect(performance.now() - start).toBeLessThan(2000);
    expect(fig.data).toHaveLength(MAX_CATEGORIES + 1);
    expect(traces(fig).at(-1)?.name).toBe("Other");
  });

  it("labels a log axis and notes values it cannot show", () => {
    const fig = buildBoxFigure(ds(), cfg({ logY: true }), pass(5));
    expect(fig.layout.yaxis).toMatchObject({ type: "log", title: { text: "Signal (log)" } });
    expect(fig.skipped).toBe(1);
    expect(fig.note).toBe("1 row lacks Signal");
  });
});
