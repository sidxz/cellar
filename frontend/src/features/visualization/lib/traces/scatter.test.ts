import { CHART_COLORS, WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { type Appearance, DEFAULT_APPEARANCE, type PanelConfig } from "../../store/workbench-store";
import type { Dataset, DatasetColumn } from "../../types";
import { MAX_COLOR_GROUPS } from "../appearance";
import {
  FILTERED,
  buildScatterBase,
  buildScatterFigure,
  markerSize,
  rowIdsFromEvent,
  selectScatter,
} from "./scatter";

type Kind = DatasetColumn["kind"];
interface Trace {
  name?: string;
  customdata?: number[];
  x: unknown[];
  y: unknown[];
  xaxis?: string;
  selectedpoints?: number[];
  text?: string[];
  marker: { symbol?: unknown; color?: unknown; size?: unknown };
}

function dataset(values: Record<string, unknown[]>, kinds: Record<string, Kind> = {}): Dataset {
  const n = Object.values(values)[0].length;
  const kindOf = (k: string): Kind =>
    kinds[k] ?? (typeof values[k].find((v) => v != null) === "number" ? "number" : "category");
  return {
    revision: "r",
    level: "wells",
    row_count: n,
    row_ids: Array.from({ length: n }, (_, i) => `w${i}`),
    columns: Object.keys(values).map((key) => ({
      key,
      label: key === "y" ? "Signal" : key,
      kind: kindOf(key),
      provenance: {},
    })),
    values,
  };
}

const panel = (appearance: Partial<Appearance> = {}, patch: Partial<PanelConfig> = {}) => ({
  id: "p1",
  type: "scatter" as const,
  x: "well_order",
  y: "y",
  ...patch,
  appearance: { ...DEFAULT_APPEARANCE, ...appearance },
});
const pass = (n: number) => new Uint8Array(n).fill(1);
const NONE = new Set<string>();
const traces = (fig: { data: Record<string, unknown>[] }) => fig.data as unknown as Trace[];
const plotted = (fig: { data: Record<string, unknown>[] }) =>
  traces(fig).filter((t) => t.name !== FILTERED);

describe("buildScatterFigure", () => {
  const four = () => dataset({ well_order: [1, 2, 3, 4], y: [10, 20, 30, 40] });

  it("draws failing rows only in the filtered trace, and drops it when hidden", () => {
    const mask = Uint8Array.from([1, 0, 1, 0]);
    const fig = buildScatterFigure(four(), panel(), mask, NONE);
    expect(plotted(fig).flatMap((t) => t.customdata)).toEqual([0, 2]);
    const filtered = traces(fig).filter((t) => t.name === FILTERED);
    expect(filtered).toHaveLength(1);
    expect(filtered[0].x).toEqual([2, 4]);
    expect(filtered[0].marker.symbol).toBe("x-thin");
    expect(filtered[0].customdata).toBeUndefined();

    const hidden = buildScatterFigure(four(), panel({ showFiltered: false }), mask, NONE);
    expect(traces(hidden).some((t) => t.name === FILTERED)).toBe(false);
  });

  it("gives each well type its color and shape", () => {
    const types = ["sample", "negative_control", "positive_control", "blank", "reference"];
    const ds = dataset({ well_order: [1, 2, 3, 4, 5], y: [1, 2, 3, 4, 5], well_type: types });
    const fig = buildScatterFigure(
      ds,
      panel({ colorBy: "well_type", shapeBy: "well_type" }),
      pass(5),
      NONE,
    );
    const byName = Object.fromEntries(
      plotted(fig).map((t) => [t.name, [t.marker.symbol, t.marker.color]]),
    );
    expect(byName).toEqual({
      Sample: ["circle", WELL_TYPE_COLORS.sample],
      "Negative control": ["square", WELL_TYPE_COLORS.negative_control],
      "Positive control": ["diamond", WELL_TYPE_COLORS.positive_control],
      Blank: ["triangle-up", WELL_TYPE_COLORS.blank],
      Reference: ["star", WELL_TYPE_COLORS.reference],
    });
  });

  it("groups numeric color bins into legend entries titled by the field", () => {
    const ds = dataset({ well_order: [1, 2, 3], y: [0.2, 0.4, 0.6] });
    const a = { colorBy: "y", colorMode: "bins" as const, colorBins: [0.3, 0.5] };
    const fig = buildScatterFigure(ds, panel(a), pass(3), NONE);
    expect(plotted(fig).map((t) => [t.name, t.marker.color])).toEqual([
      ["< 0.3", CHART_COLORS.success],
      ["0.3 to 0.5", CHART_COLORS.warning],
      ["≥ 0.5", CHART_COLORS.error],
    ]);
    expect(fig.layout.legend).toMatchObject({ title: { text: "Signal" } });
  });

  it("sizes points by a numeric field and adds tooltip fields to the hover", () => {
    const ds = dataset({ well_order: [1, 2], y: [10, 30], plate: ["Plate 1", "Plate 2"] });
    const fig = buildScatterFigure(ds, panel({ sizeBy: "y", tooltip: ["plate"] }), pass(2), NONE);
    const [t] = plotted(fig);
    expect(t.marker.size).toEqual([5, 16]);
    expect(t.text?.[1]).toBe("No compound · Plate 2<br>plate: Plate 2");
  });

  it("gives traces uids that are valid CSS class names", () => {
    // Plotly removes a vanished trace's colorbar by selecting `.cb<uid>`; a space or "|"
    // there throws and leaves the plot frozen on its old drawing.
    const ds = dataset({
      well_order: [1, 2, 3],
      y: [1, 2, 3],
      well_type: ["sample", "negative_control", "sample"],
    });
    const fig = buildScatterFigure(
      ds,
      panel({ colorBy: "well_type", splitBy: "well_type" }),
      Uint8Array.from([1, 1, 0]),
      NONE,
    );
    const uids = fig.data.map((t) => t.uid as string);
    expect(new Set(uids).size).toBe(uids.length);
    for (const uid of uids) expect(uid).toMatch(/^[A-Za-z][\w-]*$/);
  });

  it("marks the selected rows by their position in each trace", () => {
    const fig = buildScatterFigure(four(), panel(), pass(4), new Set(["w1", "w3"]));
    const [t] = plotted(fig);
    expect(t.selectedpoints).toEqual([1, 3]);
    expect(t.selectedpoints?.map((p) => t.customdata?.[p])).toEqual([1, 3]);
    expect(plotted(buildScatterFigure(four(), panel(), pass(4), NONE))[0].selectedpoints).toBe(
      undefined,
    );
  });

  it("counts and leaves out rows that lack a value", () => {
    const ds = dataset({ well_order: [1, 2, 3, 4], y: [1, null, Number.NaN, 4] });
    const fig = buildScatterFigure(ds, panel(), pass(4), NONE);
    expect(fig.skipped).toBe(2);
    expect(fig.note).toBe("2 rows lack Signal");
    expect(plotted(fig).flatMap((t) => t.customdata)).toEqual([0, 3]);
  });

  it("labels log axes and skips values a log axis cannot show", () => {
    const ds = dataset({ well_order: [1, 2, 3], y: [0, 5, 50] });
    const fig = buildScatterFigure(ds, panel({}, { logY: true }), pass(3), NONE);
    const yaxis = fig.layout.yaxis as { type: string; title: { text: string } };
    expect(yaxis).toMatchObject({ type: "log", title: { text: "Signal (log)" } });
    expect(fig.skipped).toBe(1);
  });

  it("splits into six facets plus Other, wrapping to two rows", () => {
    const plates = ["1", "2", "3", "4", "5", "6", "7", "8"];
    const ds = dataset({
      well_order: [1, 2, 3, 4, 5, 6, 7, 8],
      y: [1, 2, 3, 4, 5, 6, 7, 8],
      plate: plates,
    });
    const fig = buildScatterFigure(ds, panel({ splitBy: "plate" }), pass(8), NONE);
    const titles = (fig.layout.annotations as { text: string }[]).map((a) => a.text);
    expect(titles).toEqual(["1", "2", "3", "4", "5", "6", "Other"]);
    expect(fig.layout.grid).toMatchObject({ rows: 2, columns: 4 });
    const other = plotted(fig).find((t) => t.xaxis === "x7");
    expect(other?.customdata).toEqual([6, 7]);
    expect(fig.layout.yaxis7).toMatchObject({ matches: "y" });
  });

  it("returns its facets with their axes and every row, filtered or not", () => {
    const ds = dataset({ well_order: [1, 2, 3, 4], y: [1, 2, 3, 4], plate: ["1", "2", "1", "2"] });
    const mask = Uint8Array.from([1, 0, 1, 1]);
    const split = buildScatterFigure(ds, panel({ splitBy: "plate" }), mask, NONE);
    expect(split.facets).toEqual([
      { label: "1", rows: [0, 2], xaxis: "x", yaxis: "y" },
      { label: "2", rows: [1, 3], xaxis: "x2", yaxis: "y2" },
    ]);
    expect(buildScatterFigure(ds, panel(), mask, NONE).facets).toEqual([
      { label: "", rows: [0, 1, 2, 3], xaxis: "x", yaxis: "y" },
    ]);
  });

  it("plots against run date on a date axis", () => {
    const ds = dataset({ run_date: ["2026-01-02", null, "2026-01-05"], y: [7.4, 7.5, 7.3] });
    const fig = buildScatterFigure(ds, panel({}, { x: "run_date", logX: true }), pass(3), NONE);
    expect(fig.layout.xaxis).toMatchObject({ type: "date", title: { text: "run_date" } });
    expect(plotted(fig)[0].x).toEqual(["2026-01-02", "2026-01-05"]);
    expect(fig.note).toBe("1 row lacks run_date");
  });
});

describe("selectScatter", () => {
  it("marks a selection without rebuilding coordinates, colors or hover text", () => {
    const ds = dataset({ well_order: [1, 2, 3, 4], y: [10, 20, 30, 40] });
    const base = buildScatterBase(ds, panel({ colorBy: "y" }), pass(4));
    const one = selectScatter(base, ds, new Set(["w1"]));
    const two = selectScatter(base, ds, new Set(["w2", "w3"]));
    const [b, s1, s2] = [base, one, two].map((f) => plotted(f)[0]);
    for (const s of [s1, s2]) {
      expect(s.x).toBe(b.x);
      expect(s.y).toBe(b.y);
      expect(s.text).toBe(b.text);
      expect(s.customdata).toBe(b.customdata);
      expect(s.marker.color).toBe(b.marker.color);
    }
    expect([s1.selectedpoints, s2.selectedpoints]).toEqual([[1], [2, 3]]);
    expect(selectScatter(base, ds, new Set())).toBe(base);
  });
});

describe("large datasets", () => {
  const N = 100_000;
  const big = () => {
    const rows = Array.from({ length: N }, (_, i) => i);
    return dataset({
      well_order: rows,
      y: rows.map((i) => i % 97),
      compound: rows.map((i) => `CEL-${i}`),
    });
  };

  it("colors and shapes 100k distinct compounds as capped groups plus Other, quickly", () => {
    const ds = big();
    const mask = pass(N);
    mask[0] = 0;
    const start = performance.now();
    const fig = buildScatterFigure(
      ds,
      panel({ colorBy: "compound", shapeBy: "compound" }),
      mask,
      NONE,
    );
    expect(performance.now() - start).toBeLessThan(2000);
    expect(fig.data.length).toBeLessThanOrEqual(MAX_COLOR_GROUPS + 2);
    expect(plotted(fig).at(-1)?.name).toBe("Other");
  });

  it("draws with WebGL when the filtered points alone are over the SVG limit", () => {
    const mask = new Uint8Array(N);
    mask[0] = 1;
    const fig = buildScatterFigure(big(), panel(), mask, NONE);
    expect(fig.data.map((t) => t.type)).toEqual(["scattergl", "scattergl"]);
  });
});

describe("markerSize", () => {
  it("is 6 px up to 1k points and 3 px from 50k", () => {
    expect(markerSize(10)).toBe(6);
    expect(markerSize(1000)).toBe(6);
    expect(markerSize(50000)).toBe(3);
    expect(markerSize(200000)).toBe(3);
  });
});

describe("rowIdsFromEvent", () => {
  it("maps point row indices to row ids and ignores points without one", () => {
    const ds = dataset({ well_order: [1, 2, 3], y: [1, 2, 3] });
    const ev = { points: [{ customdata: 2 }, { customdata: 0 }, { x: 5 }] };
    expect(rowIdsFromEvent(ds, ev)).toEqual(["w2", "w0"]);
    expect(rowIdsFromEvent(ds, undefined)).toEqual([]);
  });
});
