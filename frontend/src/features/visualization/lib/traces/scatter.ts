import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { colorFor, colorGroups, numericRange, shapeFor, sizeFor, tooltipText } from "../appearance";
import { column, numberAt } from "../dataset";
import { type Figure, GRID, axisTitle, baseLayout, facetsOf, lackNote } from "./common";

/** Name of the trace holding rows the filters hide (drawn as faint ×, never selectable). */
export const FILTERED = "Filtered";
const FILTERED_COLOR = "#a1a1aa";
/** SVG draws crisper and is plenty fast below this; WebGL above it. */
const WEBGL_ABOVE = 5000;

/** 0 up to 1k points, 1 from 50k, linear in log n. */
const crowding = (n: number) => Math.min(1, Math.max(0, Math.log(n / 1000) / Math.log(50)));
/** Marker size in px: 6 at ≤1k points down to 3 at ≥50k. */
export const markerSize = (n: number) => 6 - 3 * crowding(n);
/** Multiplies the panel's opacity: 1 at ≤1k points, 0.45/0.8 at ≥50k (0.8 → 0.45 at the default). */
const opacityScale = (n: number) => 1 - (0.35 / 0.8) * crowding(n);

const axisId = (axis: "x" | "y", facet: number) => (facet === 0 ? axis : `${axis}${facet + 1}`);

/** A scatter of ``cfg.x`` × ``cfg.y``: one trace per (facet, color group), failing rows
 * as faint × in a separate trace, selection shown by ``selectedpoints`` + outline. Each
 * point's ``customdata`` is its row index, so selections resolve to stable row ids. */
export function buildScatterFigure(
  ds: Dataset,
  cfg: PanelConfig,
  mask: Uint8Array,
  selection: ReadonlySet<string>,
  dark = false,
): Figure {
  const a = cfg.appearance;
  const xTitle = axisTitle(ds, cfg.x, cfg.logX);
  const yTitle = axisTitle(ds, cfg.y, cfg.logY);
  const facets = facetsOf(ds, a.splitBy);
  // Named groups (categories, bins) get a trace each and a legend entry; a number on a
  // continuous scale colors points through a colorscale instead.
  const groupsOf = colorGroups(ds, a);
  const colorCol = a.colorBy ? column(ds, a.colorBy) : undefined;
  const range = !groupsOf && colorCol?.kind === "number" ? numericRange(ds, colorCol.key) : null;

  const value = (key: string | undefined, i: number, log?: boolean) => {
    const v = key ? numberAt(ds, key, i) : null;
    return v === null || (log && v <= 0) ? null : v;
  };

  const groups = new Map<string, { facet: number; label: string; rows: number[] }>();
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
    const label = groupsOf ? groupsOf.labelOf(i) : "";
    const k = `${facet}|${label}`;
    let g = groups.get(k);
    if (!g) {
      g = { facet, label, rows: [] };
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

  const order = groupsOf?.order ?? [];
  const ordered = [...groups.values()].sort(
    (p, q) => p.facet - q.facet || order.indexOf(p.label) - order.indexOf(q.label),
  );
  // Per-point appearance for every plotted row at once; each trace takes its slice.
  const rows = ordered.flatMap((g) => g.rows);
  const colors = colorFor(ds, a, rows);
  const symbols = shapeFor(ds, a, rows);
  const sizes = sizeFor(ds, a, rows, size);
  const inLegend = new Set<string>();
  let scaleShown = false;
  let end = 0;
  for (const g of ordered) {
    const start = end;
    end += g.rows.length;
    const selected: number[] = [];
    const lineWidth = g.rows.map((i, k) => {
      if (!selection.has(ds.row_ids[i])) return 0;
      selected.push(k);
      return 1.5;
    });
    data.push({
      type,
      mode: "markers",
      // Stable per (facet, group) and a valid CSS class: Plotly selects `.cb<uid>`.
      uid: `f${g.facet}-g${order.indexOf(g.label) + 1}`,
      name: groupsOf ? g.label : yTitle,
      legendgroup: g.label,
      showlegend: Boolean(groupsOf) && !inLegend.has(g.label),
      ...place(g.facet),
      x: xs(g.rows),
      y: ys(g.rows),
      customdata: g.rows,
      text: g.rows.map((i) => tooltipText(ds, i, a.tooltip)),
      hovertemplate: `%{text}<br>${xTitle}: %{x}<br>${yTitle}: %{y}<extra></extra>`,
      marker: {
        color: range ? colors.slice(start, end) : uniform(colors.slice(start, end)),
        symbol: uniform(symbols.slice(start, end)),
        size: uniform(sizes.slice(start, end)),
        opacity,
        line: { color: outline, width: lineWidth },
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
      selectedpoints: selection.size > 0 ? selected : undefined,
      // A size-by keeps each point's own size; the outline marks the selection.
      selected: { marker: { opacity: 1, ...(a.sizeBy ? {} : { size: size + 2 }) } },
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
    ...baseLayout(cfg.id),
    dragmode: "lasso",
    hovermode: "closest",
    margin: { l: 56, r: 12, t: split ? 52 : 32, b: 44 },
  };
  if (groupsOf?.title) {
    const legend = baseLayout(cfg.id).legend as Record<string, unknown>;
    layout.legend = { ...legend, title: { text: groupsOf.title } };
  }
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
  const note = lackNote(skipped, what);
  return { data, layout, skipped, note };
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
