import { CHART_COLORS, WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { buildBarFigure } from "./bar";
import { MAX_CATEGORIES } from "./common";
import { dataset, panel, pass, traces } from "./test-fixtures";

const ds = () =>
  dataset({
    plate: ["2", "1", "2", "1", "2", "10"],
    well_type: ["sample", "sample", "blank", "sample", null, "sample"],
    y: [5, 1, 9, 3, 7, null],
  });

describe("buildBarFigure", () => {
  it("counts passing rows per category, in natural order", () => {
    const fig = buildBarFigure(ds(), panel("bar", { category: "plate" }), pass(6));
    const [t] = traces(fig);
    expect(t.x).toEqual(["1", "2", "10"]);
    expect(t.y).toEqual([2, 3, 1]);
    expect(t.marker.color).toBe(CHART_COLORS.primary);
    expect(fig.layout.xaxis).toMatchObject({ type: "category" });
    const some = traces(
      buildBarFigure(
        ds(),
        panel("bar", { category: "plate" }),
        Uint8Array.from([0, 1, 1, 1, 1, 1]),
      ),
    );
    expect(some[0].y).toEqual([2, 2, 1]);
  });

  it("takes the median (and mean) of Y per category", () => {
    const median = buildBarFigure(
      ds(),
      panel("bar", { category: "plate", agg: "median", y: "y" }),
      pass(6),
    );
    expect(traces(median)[0].y).toEqual([2, 7, null]);
    expect(median.note).toBe("1 row lacks Signal");
    expect(median.layout.yaxis).toMatchObject({ title: { text: "Median Signal" } });
    const mean = buildBarFigure(
      ds(),
      panel("bar", { category: "plate", agg: "mean", y: "y" }),
      pass(6),
    );
    expect(traces(mean)[0].y).toEqual([2, 7, null]);
  });

  it("leaves censored values out of the mean and says how many", () => {
    const d = dataset({
      plate: ["1", "1", "1", "2"],
      y: [10, 20, 100, 5],
      "y:q": [null, null, ">", "<"],
    });
    const fig = buildBarFigure(
      d,
      panel("bar", { category: "plate", agg: "mean", y: "y" }),
      pass(4),
    );
    expect(traces(fig)[0].y).toEqual([15, null]);
    expect(fig.note).toBe("2 censored values not included");
    const count = buildBarFigure(d, panel("bar", { category: "plate" }), pass(4));
    expect([traces(count)[0].y, count.note]).toEqual([[3, 1], null]);
  });

  it("caps a 100k-compound group at the category limit, pooling the rest as Other", () => {
    const N = 100_000;
    const d = dataset({ compound: Array.from({ length: N }, (_, i) => `CEL-${i}`) });
    const start = performance.now();
    const fig = buildBarFigure(d, panel("bar", { category: "compound" }), pass(N));
    expect(performance.now() - start).toBeLessThan(2000);
    const [t] = traces(fig);
    expect(t.x).toHaveLength(MAX_CATEGORIES + 1);
    expect(t.x.at(-1)).toBe("Other");
    expect(t.y.at(-1)).toBe(N - MAX_CATEGORIES);
  });

  it("colors well-type bars and labels a log axis", () => {
    const fig = buildBarFigure(ds(), panel("bar", { category: "well_type", logY: true }), pass(6));
    const [t] = traces(fig);
    expect(t.x).toEqual(["Blank", "Sample", "(none)"]);
    expect(t.marker.color).toEqual([
      WELL_TYPE_COLORS.blank,
      WELL_TYPE_COLORS.sample,
      CHART_COLORS.neutral,
    ]);
    expect(fig.layout.yaxis).toMatchObject({ type: "log", title: { text: "Count (log)" } });
  });
});
