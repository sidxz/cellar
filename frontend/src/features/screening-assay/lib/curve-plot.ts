/** The Curves tab's figure and table, built from the API's run curves. Pure.
 *  It draws what the API sends and knows nothing about what a reported value
 *  means. */

import { CHART_AXIS, CHART_CANVAS, MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import { type RunCurves, WELL_TYPE_LABELS, type WellType } from "../types";
import { holderOrder } from "./curve-selection";

type Position = RunCurves["positions"][number];

export type ColourMode = "highlight" | "distinct";
export type CurvePalette = "dark" | "light";

export interface CurveColouring {
  /** Distinct uses `slots`; a position without a slot gets highlight colours. */
  colourMode: ColourMode;
  slots: ReadonlyMap<string, number>;
  focusedId: string | null;
  palette: CurvePalette;
}

export interface CurveStyle {
  color: string;
  width: number;
  opacity: number;
}

const DIMMED = 0.35;

/** One position's line colour, width and opacity. The selector, the legend
 *  and the table use it too, so a position looks the same in all four. */
export function curveStyle(
  position: Pick<Position, "well_id" | "well_type">,
  c: CurveColouring,
): CurveStyle {
  const colours = MEASURED_CURVE_COLORS[c.palette];
  const focused = c.focusedId === position.well_id;
  const slot = c.colourMode === "distinct" ? c.slots.get(position.well_id) : undefined;
  if (slot !== undefined) {
    return { color: colours.series[slot], width: focused ? 3 : 1.6, opacity: 1 };
  }
  const reference = position.well_type === "reference";
  return {
    color: focused ? colours.focus : reference ? colours.reference : colours.neutral,
    width: focused ? 3 : reference ? 2.2 : 1.6,
    opacity: c.focusedId !== null && !focused ? DIMMED : 1,
  };
}

export function positionName(p: Pick<Position, "position_label" | "label">): string {
  return p.label ? `${p.position_label} · ${p.label}` : p.position_label;
}

export function currentChannel(data: RunCurves) {
  return data.channels.find((c) => c.key === data.channel);
}

export function buildCurveFigure(
  args: {
    data: RunCurves;
    selected: ReadonlySet<string>;
    showReported: boolean;
    canvas: "screen" | "export";
  } & CurveColouring,
): { data: Record<string, unknown>[]; layout: Record<string, unknown> } {
  const { data, selected, showReported, canvas } = args;
  const exporting = canvas === "export";
  // The exported figure sits on white, so it always takes the light set.
  const colouring: CurveColouring = {
    ...args,
    palette: exporting ? "light" : args.palette,
    focusedId: exporting ? null : args.focusedId,
  };
  const channel = currentChannel(data);
  const xUnit = channel?.x_unit ?? "";
  const xTitle = channel?.x_label ? `${channel.x_label} [${xUnit}]` : xUnit;
  const curveById = new Map(data.curves.map((c) => [c.well_id, c]));

  const traces: Record<string, unknown>[] = [];
  const shapes: Record<string, unknown>[] = [];
  for (const p of holderOrder(data.positions)) {
    const curve = curveById.get(p.well_id);
    if (!selected.has(p.well_id) || !curve) continue;
    const style = curveStyle(p, colouring);
    traces.push({
      type: "scatter",
      mode: "lines",
      x: curve.x,
      y: curve.y,
      name: positionName(p),
      meta: p.well_id,
      line: { color: style.color, width: style.width },
      opacity: style.opacity,
      hovertemplate: `<b>%{fullData.name}</b><br>%{x} ${xUnit} · %{y:.4g}<extra></extra>`,
    });
    if (!showReported) continue;
    for (const r of curve.reported) {
      if (r.unit !== xUnit) continue;
      shapes.push({
        type: "line",
        xref: "x",
        x0: r.value,
        x1: r.value,
        yref: "paper",
        y0: 0,
        y1: 1,
        line: {
          color: style.color,
          width: colouring.focusedId === p.well_id ? 2 : 1,
          dash: "dot",
        },
        opacity: 0.8 * style.opacity,
      });
    }
  }

  const light = exporting || colouring.palette === "light";
  const grid = light ? CHART_CANVAS.gridLight : CHART_AXIS.grid;
  const ink = light ? CHART_CANVAS.label : CHART_AXIS.label;
  const background = exporting ? CHART_CANVAS.background : "rgba(0,0,0,0)";
  const yTitle = !channel
    ? ""
    : data.view === "derivative"
      ? `d(${channel.label})/d(${xUnit})`
      : channel.y_unit
        ? `${channel.label} (${channel.y_unit})`
        : channel.label;

  return {
    data: traces,
    layout: {
      // Constant across hover, focus and selection, so they keep the zoom; the
      // y axis resets when the signal changes, because its scale does.
      uirevision: "run-curves",
      margin: { l: 64, r: 16, t: 10, b: 44 },
      paper_bgcolor: background,
      plot_bgcolor: background,
      // In Highlight mode every entry shares a colour, so a legend could not be read.
      showlegend: exporting && colouring.colourMode === "distinct",
      hovermode: "closest",
      font: { color: ink, size: 12 },
      shapes,
      xaxis: { title: { text: xTitle }, gridcolor: grid, linecolor: grid, zeroline: false },
      yaxis: {
        title: { text: yTitle },
        gridcolor: grid,
        linecolor: grid,
        zeroline: false,
        uirevision: `${data.channel}:${data.view}`,
      },
    },
  };
}

/** The position id of the curve under the pointer, from a Plotly hover event. */
export function focusIdFromHover(event: unknown): string | null {
  const meta = (event as { points?: { data?: { meta?: unknown } }[] } | null)?.points?.[0]?.data
    ?.meta;
  return typeof meta === "string" ? meta : null;
}

export interface ReportedColumn {
  key: string;
  label: string;
  unit: string;
}

function reportedKey(r: { kind: string; ordinal: number }): string {
  return `${r.kind}:${r.ordinal}`;
}

/** One table column per distinct reported value on this signal's curves. */
export function reportedColumns(data: RunCurves): ReportedColumn[] {
  const columns = new Map<string, ReportedColumn & { kind: string; ordinal: number }>();
  for (const curve of data.curves) {
    for (const r of curve.reported) {
      const key = reportedKey(r);
      if (!columns.has(key)) {
        columns.set(key, { key, label: r.label, unit: r.unit, kind: r.kind, ordinal: r.ordinal });
      }
    }
  }
  return [...columns.values()]
    .sort((a, b) => a.kind.localeCompare(b.kind) || a.ordinal - b.ordinal)
    .map(({ key, label, unit }) => ({ key, label, unit }));
}

export interface CurveTableRow {
  wellId: string;
  wellType: string;
  positionLabel: string;
  label: string | null;
  compound: string | null;
  batch: string | null;
  dose: number | null;
  role: string;
  note: string | null;
  reported: Record<string, number>;
}

export function tableRows(data: RunCurves, selected: ReadonlySet<string>): CurveTableRow[] {
  const curveById = new Map(data.curves.map((c) => [c.well_id, c]));
  return holderOrder(data.positions)
    .filter((p) => selected.has(p.well_id))
    .map((p) => ({
      wellId: p.well_id,
      wellType: p.well_type,
      positionLabel: p.position_label,
      label: p.label,
      compound: p.molecule_name ?? null,
      batch: p.batch_number ?? null,
      dose: p.dose ?? null,
      role: WELL_TYPE_LABELS[p.well_type as WellType] ?? p.well_type,
      note: p.note,
      reported: Object.fromEntries(
        (curveById.get(p.well_id)?.reported ?? []).map((r) => [reportedKey(r), r.value]),
      ),
    }));
}
