import { CHART_COLORS, WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import type { OverlayConfig, PanelPatch } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { buildScatterBase } from "../traces/scatter";
import { dataset, panel, pass } from "../traces/test-fixtures";
import { buildOverlays } from "./build";
import { zPrimeLabel } from "./qc";

type Mark = Record<string, unknown>;

const NEG = "negative_control";
const POS = "positive_control";

/** The overlays a scatter of ``ds`` draws with ``overlays`` on, laid into its own facets. */
function draw(ds: Dataset, overlays: OverlayConfig, patch: PanelPatch = {}, mask?: Uint8Array) {
  const p = panel("scatter", { x: "well_order", y: "y", overlays, ...patch });
  const m = mask ?? pass(ds.row_ids.length);
  return buildOverlays(ds, p, m, buildScatterBase(ds, p, m).facets ?? []);
}
const byPlate = { appearance: { splitBy: "plate" } };

// Plate 1: negatives 0, 2, 4 and a flagged 100; positives 98, 100, 102.
// Plate 2: one negative. Plate 3: samples only.
const plates = dataset({
  well_order: [1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 1, 2],
  y: [0, 2, 4, 100, 98, 100, 102, 50, 5, 40, 30, 20],
  "y:outlier": [null, null, null, "outlier", null, null, null, null, null, null, null, null],
  plate: [...Array(8).fill("Plate 1"), "Plate 2", "Plate 2", "Plate 3", "Plate 3"],
  well_type: [NEG, NEG, NEG, NEG, POS, POS, POS, "sample", NEG, "sample", "sample", "sample"],
});

const rect = (marks: Mark[], name: string, yaxis = "y") =>
  marks.find((s) => s.legendgroup === name && s.yref === yaxis) as Mark | undefined;

describe("control bands", () => {
  it("spans mean ± 3 SD of each control type per facet, leaving flagged outliers out", () => {
    const { shapes } = draw(plates, { bands: true }, byPlate);
    expect(rect(shapes, "Negative control ± 3 SD")).toMatchObject({
      type: "rect",
      xref: "x domain",
      x0: 0,
      x1: 1,
      yref: "y",
      y0: -4,
      y1: 8,
      layer: "below",
    });
    expect(rect(shapes, "Positive control ± 3 SD")).toMatchObject({ y0: 94, y1: 106 });
    expect(shapes).toHaveLength(2);
    for (const s of shapes) {
      for (const k of ["x0", "x1", "y0", "y1"]) expect(Number.isFinite(s[k])).toBe(true);
    }
  });

  it("says why a facet has no band", () => {
    const { notes } = draw(plates, { bands: true }, byPlate);
    expect(notes).toEqual([
      "Plate 2: 1 Negative control well — no band",
      "Plate 3: no control wells",
    ]);
  });

  it("says so when every control well of a type is a flagged outlier", () => {
    const ds = dataset({
      well_order: [1, 2, 3],
      y: [1, 2, 50],
      "y:outlier": ["outlier", "outlier", null],
      well_type: [NEG, NEG, "sample"],
    });
    const { shapes, notes } = draw(ds, { bands: true });
    expect(shapes).toEqual([]);
    expect(notes).toEqual(["Negative control wells are all flagged outliers — no band"]);
  });

  it("leaves a control well the filters hide out of the math", () => {
    const mask = pass(12);
    mask[0] = 0; // the negative at 0
    const { shapes } = draw(plates, { bands: true }, byPlate, mask);
    const neg = rect(shapes, "Negative control ± 3 SD") as { y0: number; y1: number };
    expect(neg.y0).toBeCloseTo(3 - 3 * Math.SQRT2, 6);
    expect(neg.y1).toBeCloseTo(3 + 3 * Math.SQRT2, 6);
  });

  it("names each control type once in the legend, in its well-type color", () => {
    const ds = dataset({
      well_order: [1, 2, 1, 2],
      y: [0, 2, 1, 3],
      plate: ["Plate 1", "Plate 1", "Plate 2", "Plate 2"],
      well_type: [NEG, NEG, NEG, NEG],
    });
    const { shapes } = draw(ds, { bands: true }, byPlate);
    expect(shapes.map((s) => [s.yref, s.showlegend, s.name])).toEqual([
      ["y", true, "Negative control ± 3 SD"],
      ["y2", false, "Negative control ± 3 SD"],
    ]);
    expect(String(shapes[0].fillcolor).startsWith(WELL_TYPE_COLORS[NEG])).toBe(true);
  });

  it("says once, unprefixed, when no facet has control wells", () => {
    const ds = dataset({
      well_order: [1, 2],
      y: [1, 2],
      plate: ["Plate 1", "Plate 2"],
      well_type: ["sample", "sample"],
    });
    expect(draw(ds, { bands: true }, byPlate).notes).toEqual(["No control wells"]);
    expect(draw(ds, { bands: true }).notes).toEqual(["No control wells"]);
    // Bands and trend both notice; the footer says it once.
    expect(draw(ds, { bands: true, drift: "trend" }).notes).toEqual(["No control wells"]);
  });

  it("keeps the flat band when drift bands cannot be drawn along this X", () => {
    const { shapes } = draw(plates, { bands: true, drift: "band" }, { ...byPlate, x: "y" });
    expect(shapes.map((s) => s.xref)).toEqual(["x domain", "x domain"]);
  });
});

describe("drift bands", () => {
  // Row A: negatives at orders 1, 2 (0 and 4), samples up to order 24; row B: one negative.
  const rows = dataset({
    well_order: [1, 2, 3, 24, 25, 26],
    well_row: ["A", "A", "A", "A", "B", "B"],
    y: [0, 4, 50, 60, 3, 40],
    well_type: [NEG, NEG, "sample", "sample", NEG, "sample"],
  });

  it("replaces the flat band with one per plate row, over the row's plotted X", () => {
    const { shapes, notes } = draw(rows, { bands: true, drift: "band" });
    expect(shapes).toHaveLength(1);
    const [s] = shapes as { [k: string]: number | string | boolean }[];
    expect(s).toMatchObject({
      type: "rect",
      xref: "x",
      yref: "y",
      x0: 0.5,
      x1: 24.5,
      name: "Negative control ± 3 SD per plate row",
      showlegend: true,
    });
    expect(s.y0).toBeCloseTo(2 - 6 * Math.SQRT2, 6);
    expect(s.y1).toBeCloseTo(2 + 6 * Math.SQRT2, 6);
    expect(notes).toEqual(["No Negative control band in 1 plate row — fewer than 2 wells"]);
  });

  // One negative per plate row: no row can have a drift band.
  const lone = dataset({
    well_order: [1, 2, 13, 14],
    well_row: ["A", "A", "B", "B"],
    y: [0, 50, 4, 60],
    well_type: [NEG, "sample", NEG, "sample"],
  });

  it("falls back to the flat band where no plate row has one, while Control bands is on", () => {
    const { shapes, notes } = draw(lone, { bands: true, drift: "band" });
    expect(shapes).toMatchObject([
      { xref: "x domain", x0: 0, x1: 1, y0: 2 - 6 * Math.SQRT2, name: "Negative control ± 3 SD" },
    ]);
    expect(notes).toEqual([
      "No Negative control band in 2 plate rows — fewer than 2 wells; flat ± 3 SD band instead",
    ]);
  });

  it("draws no flat band in place of a drift band when Control bands is off", () => {
    const { shapes, notes } = draw(lone, { drift: "band" });
    expect(shapes).toEqual([]);
    expect(notes).toEqual(["No Negative control band in 2 plate rows — fewer than 2 wells"]);
  });

  it("says once per control type how many plate rows lack a band, across facets", () => {
    const ds = dataset({
      well_order: [1, 2, 13, 1, 2, 13],
      well_row: ["A", "A", "B", "A", "A", "B"],
      y: [0, 4, 3, 1, 5, 2],
      plate: ["Plate 1", "Plate 1", "Plate 1", "Plate 2", "Plate 2", "Plate 2"],
      well_type: [NEG, NEG, NEG, NEG, NEG, NEG],
    });
    const { shapes, notes } = draw(ds, { bands: true, drift: "band" }, byPlate);
    expect(shapes.map((s) => [s.yref, s.xref])).toEqual([
      ["y", "x"],
      ["y2", "x2"],
    ]);
    expect(notes).toEqual(["No Negative control band in 2 plate rows — fewer than 2 wells"]);
  });

  it("groups by plate column when X is the column", () => {
    const ds = dataset({
      well_column: [1, 1, 2],
      y: [0, 2, 9],
      well_type: [NEG, NEG, "sample"],
    });
    const { shapes } = draw(ds, { drift: "band" }, { x: "well_column" });
    expect(shapes).toMatchObject([
      { x0: 0.5, x1: 1.5, name: "Negative control ± 3 SD per plate column" },
    ]);
  });
});

describe("trend lines", () => {
  it("draws a dashed least-squares line per control type over its X, unselectable", () => {
    const ds = dataset({
      well_order: [1, 2, 3, 4],
      y: [0, 1, 2, 70],
      well_type: [NEG, NEG, NEG, "sample"],
    });
    const { traces, shapes } = draw(ds, { bands: true, drift: "trend" });
    expect(traces).toEqual([
      expect.objectContaining({
        mode: "lines",
        name: "Negative control trend",
        showlegend: true,
        x: [1, 3],
        y: [0, 2],
        xaxis: "x",
        yaxis: "y",
        line: expect.objectContaining({ color: WELL_TYPE_COLORS[NEG], dash: "dash" }),
      }),
    ]);
    expect(traces[0]).not.toHaveProperty("customdata");
    // On top of the flat band.
    expect(shapes).toHaveLength(1);
  });

  it("says why a control type has no trend", () => {
    const ds = dataset({ well_order: [1, 2], y: [0, 70], well_type: [NEG, "sample"] });
    expect(draw(ds, { drift: "trend" }).notes).toEqual(["1 Negative control well — no trend"]);
  });
});

describe("stored Z′", () => {
  const zp = {
    ...dataset({
      well_order: [1, 2, 3, 4],
      y: [1, 2, 3, 4],
      plate: ["Plate 1", "Plate 1", "Plate 2", "Plate 2"],
      plate_id: ["a", "a", "b", "b"],
      well_type: [NEG, "sample", NEG, "sample"],
    }),
    plate_z_prime: { a: 0.712 },
  };

  it("labels each plate facet with its stored value, as the Heat Map prints it", () => {
    const { annotations, shapes, traces } = draw(zp, { zPrime: true }, byPlate);
    expect(annotations).toEqual([
      expect.objectContaining({
        text: "Z′ 0.712 · Excellent · stored",
        xref: "x domain",
        yref: "y domain",
        x: 1,
        xanchor: "right",
        font: expect.objectContaining({ color: CHART_COLORS.success }),
        hovertext: "Stored plate Z′ from the run's QC — the Heat Map's value, not recomputed here.",
      }),
      expect.objectContaining({
        text: "Z′ not stored",
        xref: "x2 domain",
        font: expect.objectContaining({ color: CHART_COLORS.neutral }),
      }),
    ]);
    expect([...shapes, ...traces]).toEqual([]);
  });

  it("shows no Z′ unless split by plate", () => {
    expect(draw(zp, { zPrime: true }).annotations).toEqual([]);
  });
});

describe("zPrimeLabel", () => {
  it.each([
    [[0.712], "Z′ 0.712 · Excellent · stored"],
    [[0.4], "Z′ 0.400 · Marginal · stored"],
    [[-0.2], "Z′ -0.200 · Poor · stored"],
    [[null], "Z′ not stored"],
    [[0.712, 0.45], "Z′ 0.450–0.712 · Marginal · stored (2 plates)"],
    [[0.712, null], "Z′ 0.712 · Excellent · stored (1 of 2 plates)"],
    [[0.5, 0.5], "Z′ 0.500 · Excellent · stored (2 plates)"],
  ] as [Array<number | null>, string][])("%j → %s", (values, label) => {
    expect(zPrimeLabel(values)).toBe(label);
  });
});
