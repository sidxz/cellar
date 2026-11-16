import { WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { type Appearance, DEFAULT_APPEARANCE, type PanelConfig } from "../../store/workbench-store";
import type { Dataset, DatasetColumn } from "../../types";
import { FILTERED, buildScatterFigure, markerSize, rowIdsFromEvent } from "./scatter";

type Kind = DatasetColumn["kind"];
interface Trace {
  name?: string;
  customdata?: number[];
  x: unknown[];
  xaxis?: string;
  selectedpoints?: number[];
  marker: { symbol?: unknown; color?: unknown };
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
