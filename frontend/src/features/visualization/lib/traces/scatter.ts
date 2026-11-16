import {
  CHART_AXIS,
  CHART_COLORS,
  GROUP_PALETTE,
  WELL_TYPE_COLORS,
} from "@/shared/lib/chart-colors";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { categoryLabel, column, numberAt } from "../dataset";

/** Name of the trace holding rows the filters hide (drawn as faint ×, never selectable). */
export const FILTERED = "Filtered";
export const MAX_FACETS = 6;
const OTHER = "Other";
const NONE = categoryLabel("", null);
const GRID = "rgba(113,113,122,0.2)";
const FILTERED_COLOR = "#a1a1aa";
/** SVG draws crisper and is plenty fast below this; WebGL above it. */
const WEBGL_ABOVE = 5000;

export const WELL_TYPE_SYMBOLS: Record<string, string> = {
  sample: "circle",
  negative_control: "square",
  positive_control: "diamond",
  blank: "triangle-up",
  reference: "star",
};
const SYMBOLS = ["circle", "square", "diamond", "triangle-up", "star", "cross", "pentagon"];

const collator = new Intl.Collator(undefined, { numeric: true });

/** 0 up to 1k points, 1 from 50k, linear in log n. */
const crowding = (n: number) => Math.min(1, Math.max(0, Math.log(n / 1000) / Math.log(50)));
/** Marker size in px: 6 at ≤1k points down to 3 at ≥50k. */
export const markerSize = (n: number) => 6 - 3 * crowding(n);
/** Multiplies the panel's opacity: 1 at ≤1k points, 0.45/0.8 at ≥50k (0.8 → 0.45 at the default). */
const opacityScale = (n: number) => 1 - (0.35 / 0.8) * crowding(n);

/** A category column's distinct display labels, natural order, "(none)" last. */
function levels(ds: Dataset, key: string): string[] {
  const seen = new Set<string>();
  for (const v of ds.values[key] ?? []) seen.add(categoryLabel(key, v));
  return [...seen].sort(
    (a, b) => Number(a === NONE) - Number(b === NONE) || collator.compare(a, b),
  );
}

/** Facets for split-by: up to MAX_FACETS named, the rest pooled as "Other". Built from
 * every row, so facets never move as filters change. */
function facetsOf(ds: Dataset, key: string | undefined) {
  const all = key ? levels(ds, key) : [];
  if (!key || all.length === 0) return { labels: [""], of: (_i: number) => 0 };
  const index = new Map(all.map((label, k) => [label, Math.min(k, MAX_FACETS)]));
  const labels = all.length > MAX_FACETS ? [...all.slice(0, MAX_FACETS), OTHER] : all;
  return { labels, of: (i: number) => index.get(categoryLabel(key, ds.values[key]?.[i])) ?? 0 };
}

const axisId = (axis: "x" | "y", facet: number) => (facet === 0 ? axis : `${axis}${facet + 1}`);

function axisTitle(ds: Dataset, key: string | undefined, log?: boolean): string {
  const label = key ? (column(ds, key)?.label ?? key) : "—";
  return log ? `${label} (log)` : label;
}

function hoverText(ds: Dataset, i: number): string {
  const plate = ds.values.plate?.[i];
  const place = [plate != null ? `Plate ${plate}` : null, ds.values.well?.[i]].filter(Boolean);
  return [ds.values.compound?.[i] ?? "No compound", place.join(" ")].filter(Boolean).join(" · ");
}

function symbolFor(ds: Dataset, key: string, i: number, order: string[]): string {
  const v = ds.values[key]?.[i];
  if (key === "well_type") return WELL_TYPE_SYMBOLS[String(v)] ?? "circle";
  return SYMBOLS[Math.max(0, order.indexOf(categoryLabel(key, v))) % SYMBOLS.length];
}

function categoryColor(key: string, raw: unknown, label: string, order: string[]): string {
  if (label === NONE) return CHART_COLORS.neutral;
  if (key === "well_type") return WELL_TYPE_COLORS[String(raw)] ?? CHART_COLORS.neutral;
  return GROUP_PALETTE[order.indexOf(label) % GROUP_PALETTE.length];
}

export interface ScatterFigure {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
  /** Passing rows that cannot be plotted (no X or Y, or ≤ 0 on a log axis). */
  skipped: number;
  /** "38 rows lack Signal (AU)", or null when every passing row is plotted. */
  note: string | null;
}

/** A scatter of ``cfg.x`` × ``cfg.y``: one trace per (facet, color category), failing rows
 * as faint × in a separate trace, selection shown by ``selectedpoints`` + outline. Each
 * point's ``customdata`` is its row index, so selections resolve to stable row ids. */
export function buildScatterFigure(
  ds: Dataset,
  cfg: PanelConfig,
  mask: Uint8Array,
  selection: ReadonlySet<string>,
  dark = false,
): ScatterFigure {
  const a = cfg.appearance;
  const xTitle = axisTitle(ds, cfg.x, cfg.logX);
  const yTitle = axisTitle(ds, cfg.y, cfg.logY);
  const facets = facetsOf(ds, a.splitBy);
  const colorCol = a.colorBy ? column(ds, a.colorBy) : undefined;
  const numericColor = colorCol?.kind === "number";
  const colorKey = colorCol && !numericColor ? colorCol.key : undefined;
  const colorOrder = colorKey ? levels(ds, colorKey) : [];
  const shapeOrder = a.shapeBy ? levels(ds, a.shapeBy) : [];

  const value = (key: string | undefined, i: number, log?: boolean) => {
    const v = key ? numberAt(ds, key, i) : null;
    return v === null || (log && v <= 0) ? null : v;
  };

  const groups = new Map<string, { facet: number; label: string; raw: unknown; rows: number[] }>();
  const filtered: number[][] = facets.labels.map(() => []);
  let skipped = 0;
  let lackX = 0;
  let lackY = 0;
  let n = 0;
  for (let i = 0; i < ds.row_ids.length; i++) {
    const x = value(cfg.x, i, cfg.logX);
    const y = value(cfg.y, i, cfg.logY);
    if (!mask[i]) {
      if (a.showFiltered && x !== null && y !== null) filtered[facets.of(i)].push(i);
      continue;
    }
    if (x === null || y === null) {
      skipped += 1;
      if (x === null) lackX += 1;
      if (y === null) lackY += 1;
      continue;
    }
    n += 1;
    const facet = facets.of(i);
    const raw = colorKey ? ds.values[colorKey]?.[i] : undefined;
    const label = colorKey ? categoryLabel(colorKey, raw) : "";
    const k = `${facet}|${label}`;
    let g = groups.get(k);
    if (!g) {
      g = { facet, label, raw, rows: [] };
      groups.set(k, g);
    }
    g.rows.push(i);
  }

  const type = n > WEBGL_ABOVE ? "scattergl" : "scatter";
  const size = markerSize(n);
  const opacity = a.opacity * opacityScale(n);
  const outline = dark ? "#f1f5f9" : "#111827";
  const xs = (rows: number[]) => rows.map((i) => numberAt(ds, cfg.x as string, i));
  const ys = (rows: number[]) => rows.map((i) => numberAt(ds, cfg.y as string, i));
  const place = (facet: number) => ({ xaxis: axisId("x", facet), yaxis: axisId("y", facet) });

  let colorRange: [number, number] | null = null;
  if (numericColor && colorCol) {
    let lo = Number.POSITIVE_INFINITY;
    let hi = Number.NEGATIVE_INFINITY;
    for (let i = 0; i < ds.row_ids.length; i++) {
      const v = numberAt(ds, colorCol.key, i);
      if (v === null) continue;
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
    if (lo <= hi) colorRange = [lo, hi];
  }

  const data: Record<string, unknown>[] = [];
  filtered.forEach((rows, facet) => {
    if (rows.length === 0) return;
    data.push({
      type,
      mode: "markers",
      uid: `${facet}|${FILTERED}`,
      name: FILTERED,
      legendgroup: FILTERED,
      showlegend: !data.length,
      ...place(facet),
      x: xs(rows),
      y: ys(rows),
      hoverinfo: "skip",
      marker: {
        symbol: "x-thin",
        size,
        color: FILTERED_COLOR,
        opacity: 0.5,
        line: { width: 1, color: FILTERED_COLOR },
      },
      selected: { marker: { opacity: 0.5 } },
      unselected: { marker: { opacity: 0.5 } },
    });
  });

  const ordered = [...groups.values()].sort(
    (p, q) => p.facet - q.facet || colorOrder.indexOf(p.label) - colorOrder.indexOf(q.label),
  );
  const inLegend = new Set<string>();
  let scaleShown = false;
  for (const g of ordered) {
    const selected: number[] = [];
    const lineWidth = g.rows.map((i, k) => {
      if (!selection.has(ds.row_ids[i])) return 0;
      selected.push(k);
      return 1.5;
    });
    const symbols = a.shapeBy
      ? g.rows.map((i) => symbolFor(ds, a.shapeBy as string, i, shapeOrder))
      : [];
    const color = colorKey
      ? categoryColor(colorKey, g.raw, g.label, colorOrder)
      : numericColor && colorCol
        ? g.rows.map((i) => numberAt(ds, colorCol.key, i))
        : CHART_COLORS.primary;
    data.push({
      type,
      mode: "markers",
      uid: `${g.facet}|${g.label}`,
      name: colorKey ? g.label : yTitle,
      legendgroup: g.label,
      showlegend: Boolean(colorKey) && !inLegend.has(g.label),
      ...place(g.facet),
      x: xs(g.rows),
      y: ys(g.rows),
      customdata: g.rows,
      text: g.rows.map((i) => hoverText(ds, i)),
      hovertemplate: `%{text}<br>${xTitle}: %{x}<br>${yTitle}: %{y}<extra></extra>`,
      marker: {
        color,
        symbol:
          symbols.length === 0
            ? "circle"
            : symbols.every((s) => s === symbols[0])
              ? symbols[0]
              : symbols,
        size,
        opacity,
        line: { color: outline, width: lineWidth },
        ...(Array.isArray(color) && colorRange
          ? {
              colorscale: "Viridis",
              cmin: colorRange[0],
              cmax: colorRange[1],
              showscale: !scaleShown,
              colorbar: { title: { text: colorCol?.label }, thickness: 10 },
            }
          : {}),
      },
      selectedpoints: selection.size > 0 ? selected : undefined,
      selected: { marker: { opacity: 1, size: size + 2 } },
      unselected: { marker: { opacity: opacity * 0.35 } },
    });
    inLegend.add(g.label);
    scaleShown = true;
  }

  const count = facets.labels.length;
  const gridRows = count > 3 ? 2 : 1;
  const gridCols = Math.ceil(count / gridRows);
  const split = Boolean(a.splitBy);
  const layout: Record<string, unknown> = {
    autosize: true,
    uirevision: cfg.id,
    dragmode: "lasso",
    hovermode: "closest",
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: CHART_AXIS.tick, size: 11 },
    margin: { l: 56, r: 12, t: split ? 52 : 32, b: 44 },
    legend: { orientation: "h", x: 1, xanchor: "right", y: 1, yanchor: "top", yref: "container" },
  };
  for (let f = 0; f < count; f++) {
    const bottom = f >= (gridRows - 1) * gridCols;
    const left = f % gridCols === 0;
    layout[f === 0 ? "xaxis" : `xaxis${f + 1}`] = {
      type: cfg.logX ? "log" : "linear",
      title: bottom ? { text: xTitle } : undefined,
      gridcolor: GRID,
      zeroline: false,
      automargin: true,
    };
    layout[f === 0 ? "yaxis" : `yaxis${f + 1}`] = {
      type: cfg.logY ? "log" : "linear",
      title: left ? { text: yTitle } : undefined,
      gridcolor: GRID,
      zeroline: false,
      automargin: true,
      ...(f > 0 ? { matches: "y" } : {}),
    };
  }
  if (count > 1) {
    layout.grid = {
      rows: gridRows,
      columns: gridCols,
      pattern: "independent",
      roworder: "top to bottom",
    };
  }
  if (split) {
    layout.annotations = facets.labels.map((text, f) => ({
      text,
      xref: `${axisId("x", f)} domain`,
      yref: `${axisId("y", f)} domain`,
      x: 0.5,
      y: 1,
      xanchor: "center",
      yanchor: "bottom",
      showarrow: false,
    }));
  }

  const what = lackX && lackY ? `${xTitle} or ${yTitle}` : lackX ? xTitle : yTitle;
  const note = skipped
    ? `${skipped.toLocaleString()} ${skipped === 1 ? "row lacks" : "rows lack"} ${what}`
    : null;
  return { data, layout, skipped, note };
}

/** The part of a Plotly selection or click event we read. */
export type PointEvent = { points?: { customdata?: unknown }[] };

/** Row ids of the points a Plotly selection or click event names. Points without a row
 * index (the filtered trace carries none) are ignored. */
export function rowIdsFromEvent(ds: Dataset, ev: PointEvent | null | undefined): string[] {
  const ids: string[] = [];
  for (const p of ev?.points ?? []) {
    if (typeof p.customdata === "number") ids.push(ds.row_ids[p.customdata]);
  }
  return ids;
}
