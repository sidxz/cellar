import { CHART_COLORS, GROUP_PALETTE, WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { type Appearance, DEFAULT_APPEARANCE } from "../store/workbench-store";
import { colorBins, colorFor, shapeFor, sizeFor, tooltipText } from "./appearance";
import { dataset } from "./traces/test-fixtures";

const look = (a: Partial<Appearance>): Appearance => ({ ...DEFAULT_APPEARANCE, ...a });
const { success: GREEN, warning: AMBER, error: RED } = CHART_COLORS;

describe("colorFor", () => {
  it("colors numeric bins by their cut-offs, low to high green, amber, red", () => {
    const ds = dataset({ y: [0.2, 0.4, 0.6, null] });
    const a = look({ colorBy: "y", colorMode: "bins", colorBins: [0.3, 0.5] });
    expect(colorFor(ds, a, [0, 1, 2, 3])).toEqual([GREEN, AMBER, RED, CHART_COLORS.neutral]);
  });

  it("defaults to three equal-width bins over the whole column", () => {
    const ds = dataset({ y: [0, 3, 6, 9] });
    expect(colorBins(ds, "y").cuts).toEqual([3, 6]);
    expect(colorBins(dataset({ y: [0, 100] }), "y").cuts).toEqual([33, 67]);
    const a = look({ colorBy: "y", colorMode: "bins" });
    expect(colorFor(ds, a, [0, 1, 2, 3])).toEqual([GREEN, AMBER, RED, RED]);
  });

  it("gives every bin its own color when there are more than three", () => {
    const { colors, labels } = colorBins(dataset({ y: [0, 10] }), "y", [2, 4, 6]);
    expect(colors).toHaveLength(4);
    expect(new Set(colors).size).toBe(4);
    expect([colors[0], colors[3]]).toEqual([GREEN, RED]);
    expect(labels).toEqual(["< 2", "2 to 4", "4 to 6", "≥ 6"]);
  });

  it("returns the numbers themselves in range mode", () => {
    const ds = dataset({ y: [1, null, 3] });
    expect(colorFor(ds, look({ colorBy: "y" }), [0, 1, 2])).toEqual([1, null, 3]);
  });

  it("keeps well types on WELL_TYPE_COLORS", () => {
    const ds = dataset({ well_type: ["sample", "positive_control", "blank"] });
    expect(colorFor(ds, look({ colorBy: "well_type" }), [0, 1, 2])).toEqual([
      WELL_TYPE_COLORS.sample,
      WELL_TYPE_COLORS.positive_control,
      WELL_TYPE_COLORS.blank,
    ]);
  });

  it("assigns other categories a palette color that does not depend on the rows asked for", () => {
    const ds = dataset({ plate: ["3", "1", "2", "1"] });
    const a = look({ colorBy: "plate" });
    const all = colorFor(ds, a, [0, 1, 2, 3]);
    expect(all).toEqual([GROUP_PALETTE[2], GROUP_PALETTE[0], GROUP_PALETTE[1], GROUP_PALETTE[0]]);
    expect(colorFor(ds, a, [2])).toEqual([all[2]]);
    expect(colorFor(ds, a, [0, 1, 2, 3])).toEqual(all);
  });

  it("uses the primary color when nothing colors the plot", () => {
    expect(colorFor(dataset({ y: [1, 2] }), look({}), [0, 1])).toEqual([
      CHART_COLORS.primary,
      CHART_COLORS.primary,
    ]);
  });
});

describe("shapeFor", () => {
  it("gives well types fixed shapes and cycles other categories", () => {
    const ds = dataset({ well_type: ["sample", "negative_control"], plate: ["2", "1"] });
    expect(shapeFor(ds, look({ shapeBy: "well_type" }), [0, 1])).toEqual(["circle", "square"]);
    expect(shapeFor(ds, look({ shapeBy: "plate" }), [0, 1])).toEqual(["square", "circle"]);
    expect(shapeFor(ds, look({}), [0])).toEqual(["circle"]);
  });
});

describe("sizeFor", () => {
  it("maps a numeric field onto 5–16 px and falls back to the auto size", () => {
    const ds = dataset({ y: [10, 20, 30, null] });
    expect(sizeFor(ds, look({ sizeBy: "y" }), [0, 1, 2, 3], 6)).toEqual([5, 10.5, 16, 5]);
    expect(sizeFor(ds, look({}), [0, 1], 6)).toEqual([6, 6]);
  });
});

describe("tooltipText", () => {
  it("adds each chosen field to the identity line", () => {
    const ds = dataset({
      compound: ["CEL-1"],
      // The backend sends the whole plate label (barcode, or "Plate n" with its run).
      plate: ["Plate 3 · 2026-11-12"],
      well: ["B07"],
      y: [12.3456],
      well_type: ["positive_control"],
      dose: [null],
    });
    expect(tooltipText(ds, 0, ["y", "well_type", "dose"])).toBe(
      "CEL-1 · Plate 3 · 2026-11-12 B07<br>Signal: 12.3<br>well_type: Positive control<br>dose: (none)",
    );
    expect(tooltipText(ds, 0, [])).toBe("CEL-1 · Plate 3 · 2026-11-12 B07");
  });
});
