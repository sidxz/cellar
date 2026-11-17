import { CHART_COLORS } from "@/shared/lib/chart-colors";
import type { Appearance, PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { colorFor, colorGroups, numericRange, shapeFor, sizeFor } from "../appearance";
import { categoryLabel, column, numberAt } from "../dataset";
import {
  type Figure,
  GRID,
  OTHER,
  axisTitle,
  baseLayout,
  facetsOf,
  fieldLabel,
  lackNote,
  levels,
} from "./common";

/** Name of the trace holding rows the filters hide (drawn as faint ×, never selectable). */
export const FILTERED = "Filtered";
const FILTERED_COLOR = "#a1a1aa";
/** SVG draws crisper and is plenty fast below this; WebGL above it. */
export const WEBGL_ABOVE = 5000;

/** 0 up to 1k points, 1 from 50k, linear in log n. */
const crowding = (n: number) => Math.min(1, Math.max(0, Math.log(n / 1000) / Math.log(50)));
/** Marker size in px: 6 at ≤1k points down to 3 at ≥50k. */
export const markerSize = (n: number) => 6 - 3 * crowding(n);
/** Multiplies the panel's opacity: 1 at ≤1k points, 0.45/0.8 at ≥50k (0.8 → 0.45 at the default). */
const opacityScale = (n: number) => 1 - (0.35 / 0.8) * crowding(n);

const axisId = (axis: "x" | "y", facet: number) => (facet === 0 ? axis : `${axis}${facet + 1}`);

const plotted = (ds: Dataset, key: string | undefined, i: number, log?: boolean) => {
  const v = key ? numberAt(ds, key, i) : null;
  return v === null || (log && v <= 0) ? null : v;
};

/** Row ``i``'s X as the scatter plots it: a run date as its ISO string, else a number
 * (null when missing, or ≤ 0 on a log axis). */
export function plottedX(ds: Dataset, cfg: PanelConfig): (i: number) => number | string | null {
  if (cfg.x !== "run_date") return (i) => plotted(ds, cfg.x, i, cfg.logX);
  const dates = ds.values.run_date;
  return (i) => (dates?.[i] as string | undefined) || null;
}

/** Row ``i``'s Y as the scatter plots it (null when missing, or ≤ 0 on a log axis). */
export const plottedY =
  (ds: Dataset, cfg: PanelConfig) =>
  (i: number): number | null =>
    plotted(ds, cfg.y, i, cfg.logY);

/** A scatter with ``selection`` marked: the base figure plus the selection overlay. */
export function buildScatterFigure(
  ds: Dataset,
  cfg: PanelConfig,
  mask: Uint8Array,
  selection: ReadonlySet<string>,
  dark = false,
): Figure {
  return selectScatter(buildScatterBase(ds, cfg, mask, dark), ds, selection);
}

/** ``fig`` with ``selection`` marked: selected points outlined, the others dimmed through
 * ``selectedpoints``. Only the selection arrays are new; coordinates, colors and hover
 * text stay ``fig``'s own, so a selection change never rebuilds them. */
export function selectScatter(fig: Figure, ds: Dataset, selection: ReadonlySet<string>): Figure {
  if (selection.size === 0) return fig;
  const data = fig.data.map((t) => {
    const rows = t.customdata as number[] | undefined;
    if (!rows) return t;
    const selected: number[] = [];
    const width = rows.map((i, k) => {
      if (!selection.has(ds.row_ids[i])) return 0;
      selected.push(k);
      return 1.5;
    });
    const marker = t.marker as { line: Record<string, unknown> };
    return {
      ...t,
      selectedpoints: selected,
      marker: { ...marker, line: { ...marker.line, width } },
    };
  });
  return { ...fig, data };
}

/** A scatter of ``cfg.x`` × ``cfg.y`` without selection: one trace per (facet, color
 * group), failing rows as faint × in a separate trace. Each point's ``customdata`` is its
 * row index, so selections resolve to stable row ids. */
export function buildScatterBase(
  ds: Dataset,
  cfg: PanelConfig,
  mask: Uint8Array,
  dark = false,
): Figure {
  const a = cfg.appearance;
  // Run dates plot as ISO strings on a date axis; a log toggle does not apply there.
  const dateX = cfg.x === "run_date";
  const logX = cfg.logX && !dateX;
  const xTitle = axisTitle(ds, cfg.x, logX);
  const yTitle = axisTitle(ds, cfg.y, cfg.logY);
  const facets = facetsOf(ds, a.splitBy);
  // Named groups (categories, bins) get a trace each and a legend entry; a number on a
  // continuous scale colors points through a colorscale instead.
  const coloring = colorGroups(ds, a);
  const colorCol = a.colorBy ? column(ds, a.colorBy) : undefined;
  const range = !coloring && colorCol?.kind === "number" ? numericRange(ds, colorCol.key) : null;
  const groupCount = coloring?.order.length ?? 1;

  const xAt = plottedX(ds, cfg);
  const yAt = plottedY(ds, cfg);

  // Keyed facet-major, so sorting the keys orders traces by facet, then group.
  const groups = new Map<number, { facet: number; group: number; rows: number[] }>();
  const filtered: number[][] = facets.labels.map(() => []);
  const facetRows: number[][] = facets.labels.map(() => []);
  // A facet with no row to draw, filters aside, gets no slot (filters never move slots).
  const drawable = facets.labels.map(() => false);
  let skipped = 0;
  let lackX = 0;
  let lackY = 0;
  let n = 0;
  for (let i = 0; i < ds.row_ids.length; i++) {
    const x = xAt(i);
    const y = yAt(i);
    const facet = facets.of(i);
    facetRows[facet].push(i);
    if (x !== null && y !== null) drawable[facet] = true;
    if (!mask[i]) {
      if (a.showFiltered && x !== null && y !== null) filtered[facet].push(i);
      continue;
    }
    if (x === null || y === null) {
      skipped += 1;
      if (x === null) lackX += 1;
      if (y === null) lackY += 1;
      continue;
    }
    n += 1;
    const group = coloring ? coloring.of(i) : 0;
    const k = facet * groupCount + group;
    let g = groups.get(k);
    if (!g) {
      g = { facet, group, rows: [] };
      groups.set(k, g);
    }
    g.rows.push(i);
  }

  // The filtered × are drawn too, so they count toward the WebGL switch.
  const drawn = filtered.reduce((sum, rows) => sum + rows.length, n);
  const type = drawn > WEBGL_ABOVE ? "scattergl" : "scatter";
  const size = markerSize(n);
  const opacity = a.opacity * opacityScale(n);
  const outline = dark ? "#f1f5f9" : "#111827";
  const xs = (rows: number[]) => rows.map(xAt);
  const ys = (rows: number[]) => rows.map((i) => numberAt(ds, cfg.y as string, i));
  const kept = facets.labels.map((_, f) => f).filter((f) => drawable[f]);
  if (kept.length === 0) kept.push(0);
  const slot = new Map(kept.map((f, s) => [f, s]));
  const place = (facet: number) => {
    const s = slot.get(facet) ?? 0;
    return { xaxis: axisId("x", s), yaxis: axisId("y", s) };
  };

  const data: Record<string, unknown>[] = [];
  filtered.forEach((rows, facet) => {
    if (rows.length === 0) return;
    data.push({
      type,
      mode: "markers",
      uid: `f${facet}-filtered`,
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

  const ordered = [...groups.entries()].sort((p, q) => p[0] - q[0]).map(([, g]) => g);
  // Per-point appearance for every plotted row at once; each trace takes its slice.
  const rows = ordered.flatMap((g) => g.rows);
  const colors = colorFor(ds, a, rows);
  const symbols = shapeFor(ds, a, rows);
  const sizes = sizeFor(ds, a, rows, size);
  const inLegend = new Set<number>();
  let scaleShown = false;
  let end = 0;
  for (const g of ordered) {
    const start = end;
    end += g.rows.length;
    const label = coloring ? coloring.order[g.group] : "";
    data.push({
      type,
      mode: "markers",
      // Stable per (facet, group) and a valid CSS class: Plotly selects `.cb<uid>`.
      uid: `f${g.facet}-g${coloring ? g.group + 1 : 0}`,
      name: coloring ? label : yTitle,
      legendgroup: label,
      showlegend: Boolean(coloring) && !inLegend.has(g.group),
      ...place(g.facet),
      x: xs(g.rows),
      y: ys(g.rows),
      customdata: g.rows,
      // The panel's hover card (structure and all) replaces Plotly's label.
      hoverinfo: "none",
      marker: {
        color: range ? colors.slice(start, end) : uniform(colors.slice(start, end)),
        symbol: uniform(symbols.slice(start, end)),
        size: uniform(sizes.slice(start, end)),
        opacity,
        line: { color: outline, width: 0 },
        ...(range
          ? {
              colorscale: "Viridis",
              cmin: range[0],
              cmax: range[1],
              showscale: !scaleShown,
              colorbar: { title: { text: colorCol?.label }, thickness: 10 },
            }
          : {}),
      },
      // A size-by keeps each point's own size; the outline marks the selection.
      selected: { marker: { opacity: 1, ...(a.sizeBy ? {} : { size: size + 2 }) } },
      unselected: { marker: { opacity: opacity * 0.35 } },
    });
    inLegend.add(g.group);
    scaleShown = true;
  }
  const key = shapeKey(ds, a, rows, symbols);
  data.push(...key);

  const count = kept.length;
  const gridRows = count > 3 ? 2 : 1;
  const gridCols = Math.ceil(count / gridRows);
  const split = Boolean(a.splitBy);
  const layout: Record<string, unknown> = {
    ...baseLayout(cfg.id),
    dragmode: "lasso",
    hovermode: "closest",
    margin: { l: 56, r: 12, t: split ? 52 : 32, b: 44 },
  };
  if (coloring?.title) {
    const legend = baseLayout(cfg.id).legend as Record<string, unknown>;
    layout.legend = { ...legend, title: { text: coloring.title } };
  }
  if (key.length) layout.showlegend = true;
  for (let f = 0; f < count; f++) {
    const bottom = f >= (gridRows - 1) * gridCols;
    const left = f % gridCols === 0;
    layout[f === 0 ? "xaxis" : `xaxis${f + 1}`] = {
      type: dateX ? "date" : logX ? "log" : "linear",
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
    layout.annotations = kept.map((facet, f) => ({
      text: facets.labels[facet],
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
  const note = lackNote(skipped, what);
  const facetList = kept.map((f) => ({
    label: facets.labels[f],
    rows: facetRows[f],
    ...place(f),
  }));
  return { data, layout, skipped, note, facets: facetList };
}

/** Legend-only entries naming each drawn marker shape, unless the color legend already
 * shows them (color and shape by one field). A shape several categories share is "Other". */
function shapeKey(
  ds: Dataset,
  a: Appearance,
  rows: number[],
  symbols: string[],
): Record<string, unknown>[] {
  const key = a.shapeBy;
  if (!key || key === a.colorBy) return [];
  const bySymbol = new Map<string, Set<string>>();
  rows.forEach((i, k) => {
    const labels = bySymbol.get(symbols[k]) ?? new Set<string>();
    labels.add(categoryLabel(key, ds.values[key]?.[i]));
    bySymbol.set(symbols[k], labels);
  });
  if (bySymbol.size < 2) return [];
  const order = levels(ds, key);
  const title = fieldLabel(ds, key);
  return [...bySymbol]
    .map(([symbol, labels]) => {
      const label = labels.size === 1 ? [...labels][0] : OTHER;
      return { symbol, label, at: label === OTHER ? order.length : order.indexOf(label) };
    })
    .sort((p, q) => p.at - q.at)
    .map(({ symbol, label }) => ({
      type: "scatter",
      mode: "markers",
      uid: `shape-${symbol}`,
      name: label,
      legendgroup: "shape",
      legendgrouptitle: { text: title },
      showlegend: true,
      x: [null],
      y: [null],
      hoverinfo: "skip",
      marker: { symbol, size: 8, color: CHART_COLORS.neutral },
    }));
}

/** One value when every entry is the same (Plotly draws it faster), else the array. */
function uniform(values: unknown[]): unknown {
  return values.length > 0 && values.every((v) => v === values[0]) ? values[0] : values;
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
