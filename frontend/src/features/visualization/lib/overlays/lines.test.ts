import { CHART_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import type { OverlayConfig, PanelPatch } from "../../store/workbench-store";
import type { Dataset, Level } from "../../types";
import { buildBoxFigure } from "../traces/box";
import { buildScatterBase } from "../traces/scatter";
import { dataset, panel, pass } from "../traces/test-fixtures";
import { buildOverlays } from "./build";

type Mark = Record<string, unknown>;

/** ``ds`` at ``level`` with column overrides (unit, p-potency provenance). */
const at = (level: Level, ds: Dataset, cols: Record<string, Partial<Mark>> = {}): Dataset => ({
  ...ds,
  level,
  columns: ds.columns.map((c) => ({ ...c, ...cols[c.key] })),
});

/** The overlays a scatter of ``ds`` draws with ``overlays`` on, laid into its own facets. */
function draw(ds: Dataset, overlays: OverlayConfig, patch: PanelPatch = {}, mask?: Uint8Array) {
  const p = panel("scatter", { x: "well_order", y: "y", overlays, ...patch });
  const m = mask ?? pass(ds.row_ids.length);
  return buildOverlays(ds, p, m, buildScatterBase(ds, p, m).facets ?? []);
}

const texts = (marks: Mark[]) => marks.map((a) => a.text);

describe("reference line", () => {
  const ds = at(
    "wells",
    dataset({
      well_order: [1, 2, 1, 2],
      y: [10, 40, 20, 50],
      plate: ["Plate 1", "Plate 1", "Plate 2", "Plate 2"],
    }),
    { y: { unit: "%" } },
  );

  it("draws one display-only line per facet, labeled and in the legend once", () => {
    const { shapes, annotations, traces, notes } = draw(
      ds,
      { refLine: 30 },
      { appearance: { splitBy: "plate" } },
    );
    expect(shapes).toEqual([
      expect.objectContaining({
        type: "line",
        xref: "x domain",
        x0: 0,
        x1: 1,
        yref: "y",
        y0: 30,
        y1: 30,
        name: "Reference 30 % · display only",
        showlegend: true,
      }),
      expect.objectContaining({ xref: "x2 domain", yref: "y2", y0: 30, showlegend: false }),
    ]);
    expect(texts(annotations)).toEqual(["Reference 30 % · display only"]);
    expect([...traces, ...notes]).toEqual([]);
  });

  it("draws on a box plot too, with 3 significant figures", () => {
    const p = panel("box", { y: "y", category: "plate", overlays: { refLine: 33.333 } });
    const fig = buildBoxFigure(ds, p, pass(4));
    const { shapes } = buildOverlays(ds, p, pass(4), fig.facets ?? []);
    expect(shapes).toEqual([
      expect.objectContaining({ y0: 33.333, name: "Reference 33.3 % · display only" }),
    ]);
  });
});

describe("control limits", () => {
  const DATES = ["2026-08-01", "2026-08-08", "2026-08-15", "2026-08-22", "2026-08-29"];
  const runs = (y: number[], extra: Record<string, unknown[]> = {}) =>
    at(
      "runs",
      dataset({
        run_date: y.map((_, k) => `2026-09-${String(k + 1).padStart(2, "0")}`),
        y,
        ...extra,
      }),
    );
  const five = at("runs", dataset({ run_date: DATES, y: [7.4, 7.5, 7.3, 7.4, 6.5] }));
  const onDates = { x: "run_date" };

  it("draws the mean and ± 3 SD of the plotted points, saying where they come from", () => {
    const { shapes, annotations, traces } = draw(five, { limits: { mode: "plotted" } }, onDates);
    // Mean 7.22, sample SD √0.167.
    const sd = Math.sqrt(0.167);
    const ys = shapes.map((s) => s.y0 as number);
    expect(ys[0]).toBeCloseTo(7.22, 9);
    expect(ys[1]).toBeCloseTo(7.22 + 3 * sd, 9);
    expect(ys[2]).toBeCloseTo(7.22 - 3 * sd, 9);
    expect(shapes.map((s) => [s.name, s.showlegend, (s.line as Mark).dash])).toEqual([
      ["Control limits (from plotted points)", true, "solid"],
      ["Control limits (from plotted points)", false, "dash"],
      ["Control limits (from plotted points)", false, "dash"],
    ]);
    expect(texts(annotations)).toEqual([
      "Mean 7.22 · from plotted points",
      "+3 SD 8.45",
      "−3 SD 5.99",
    ]);
    // Five points cannot sit beyond 3 sample SDs of their own mean: no rings.
    expect(traces).toEqual([]);
  });

  it("rings the points outside the limits in the warning color, unselectably", () => {
    const y = [...Array.from({ length: 16 }, (_, k) => (k % 2 ? 7.5 : 7.3)), 6.5];
    const { traces } = draw(runs(y), { limits: { mode: "plotted" } }, onDates);
    expect(traces).toEqual([
      expect.objectContaining({
        mode: "markers",
        name: "Outside limits (1)",
        showlegend: true,
        x: ["2026-09-17"],
        y: [6.5],
        hoverinfo: "skip",
        marker: expect.objectContaining({ symbol: "circle-open", color: CHART_COLORS.warning }),
      }),
    ]);
    expect(traces[0]).not.toHaveProperty("customdata");
  });

  it("draws entered limits as given", () => {
    const limits = { mode: "entered" as const, lower: 7, upper: 7.8 };
    const { shapes, annotations, traces } = draw(five, { limits }, onDates);
    expect(shapes.map((s) => [s.y0, s.name, s.showlegend])).toEqual([
      [7.8, "Control limits (entered)", true],
      [7, "Control limits (entered)", false],
    ]);
    expect(texts(annotations)).toEqual(["Upper 7.8 · entered", "Lower 7 · entered"]);
    expect(traces.map((t) => [t.name, t.y])).toEqual([["Outside limits (1)", [6.5]]]);
  });

  it("needs two plotted points to compute limits", () => {
    const { shapes, annotations, notes } = draw(
      runs([7.4, 7.5]),
      { limits: { mode: "plotted" } },
      onDates,
      Uint8Array.from([1, 0]),
    );
    expect([...shapes, ...annotations]).toEqual([]);
    expect(notes).toEqual(["Control limits need at least 2 plotted points"]);
  });

  it("leaves censored values out of the math and says so", () => {
    const ds = runs([7, 8, 3], { "y:q": [null, null, "<"] });
    const { shapes, notes } = draw(ds, { limits: { mode: "plotted" } }, onDates);
    expect(shapes[0].y0).toBe(7.5);
    expect(notes).toEqual(["1 censored value left out of the control limits"]);
  });
});

describe("LipE guides", () => {
  const P = { aggregation: "p" };
  const compounds = at("compounds", dataset({ logp: [1, 4, 2], y: [5, 9, 7], mw: [300, 1, 2] }), {
    y: { provenance: P },
  });
  const onLogP = { x: "logp" };

  it("draws y = x + LipE across the plotted points, each labeled, one legend entry", () => {
    const { shapes, annotations, notes } = draw(compounds, { lipe: [3, 5] }, onLogP);
    expect(shapes.map((s) => [s.x0, s.y0, s.x1, s.y1, s.showlegend])).toEqual([
      [2, 5, 4, 7, true],
      [1, 6, 4, 9, false],
    ]);
    expect(shapes[0]).toMatchObject({ type: "line", xref: "x", yref: "y", name: "LipE guides" });
    expect(texts(annotations)).toEqual(["LipE 3", "LipE 5"]);
    expect(notes).toEqual([]);
  });

  it("says when a LipE value misses the plotted points", () => {
    const { shapes, notes } = draw(compounds, { lipe: [8] }, onLogP);
    expect(shapes).toEqual([]);
    expect(notes).toEqual(["LipE 8 lies outside the plotted points"]);
  });

  it("draws nothing unless Y is a p-potency and X is logP", () => {
    const notP = at("compounds", dataset({ logp: [1, 4], y: [5, 9], pic50: [1, 2] }), {
      pic50: { provenance: P },
    });
    expect(draw(notP, { lipe: [3] }, onLogP).shapes).toEqual([]);
    expect(draw(compounds, { lipe: [3] }, { x: "mw" }).shapes).toEqual([]);
  });
});
