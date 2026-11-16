import { describe, expect, it } from "vitest";
import { dataset, panel, pass } from "../traces/test-fixtures";
import { EMPTY_PARTS, buildOverlays, mergeOverlays } from "./build";

describe("overlays", () => {
  it("draws nothing for a panel with no overlay switched on", () => {
    const ds = dataset({ well_order: [1], y: [2], well_type: ["sample"] });
    const facets = [{ label: "", rows: [0], xaxis: "x", yaxis: "y" }];
    expect(
      buildOverlays(ds, panel("scatter", { x: "well_order", y: "y" }), pass(1), facets),
    ).toEqual(EMPTY_PARTS);
  });

  it("lays overlay parts over the figure, showing the legend when one has an entry", () => {
    const fig = {
      data: [{ name: "points" }],
      layout: { showlegend: false, annotations: [{ text: "Plate 1" }] },
      skipped: 1,
      note: "1 row lacks Signal",
    };
    const merged = mergeOverlays(fig, {
      traces: [{ name: "Negative control trend", showlegend: true }],
      shapes: [{ type: "rect" }],
      annotations: [{ text: "Z′ not stored" }],
      notes: ["Plate 3: no control wells"],
    });
    expect(merged.data.map((t) => t.name)).toEqual(["points", "Negative control trend"]);
    expect(merged.layout).toMatchObject({
      showlegend: true,
      shapes: [{ type: "rect" }],
      annotations: [{ text: "Plate 1" }, { text: "Z′ not stored" }],
    });
    expect(merged.note).toBe("1 row lacks Signal · Plate 3: no control wells");
    expect(mergeOverlays(fig, EMPTY_PARTS)).toBe(fig);
  });
});
