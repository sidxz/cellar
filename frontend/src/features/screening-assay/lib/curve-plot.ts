/** The curve viewer's figure and table, built from a set of positions and
 *  their curves that may come from several runs. Pure. It draws what the API
 *  sends and knows nothing about what a reported value means. */

import { CHART_AXIS, CHART_CANVAS, MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import { shortId } from "@/shared/lib/utils";
import type { CurveView } from "../hooks/use-run-curves";
import {
  type CurvePositions,
  RUN_STATUS_LABELS,
  type RunCurves,
  type RunStatus,
  WELL_TYPE_LABELS,
  type WellType,
} from "../types";
import { holderOrder } from "./curve-selection";

export type CurvePosition = RunCurves["positions"][number];
export type CurveSeriesData = RunCurves["curves"][number];
export interface CurveRunInfo {
  runId: string;
  runDate: string;
  operator: string;
  status: string;
  notes: string | null;
}

/** The positions of one run's holder. */
export interface CurveGroup {
  /** The run id. */
  key: string;
  /** Null on the run's own Curves tab, where the page already says which run it is. */
  run: CurveRunInfo | null;
  holder: RunCurves["holder"];
  /** Holder order. */
  positions: CurvePosition[];
}

/** What the curve viewer draws: groups of positions and, for one signal and
 *  view, their curves. */
export interface CurveSet {
  doseUnit: string;
  channels: RunCurves["channels"];
  channel: string | null;
  view: CurveView;
  window: number | null;
  groups: CurveGroup[];
  /** By well id, for `channel` and `view`. */
  curves: ReadonlyMap<string, CurveSeriesData>;
}

export function curveSetFromRun(data: RunCurves): CurveSet {
  return {
    doseUnit: data.dose_unit,
    channels: data.channels,
    channel: data.channel,
    view: data.view as CurveView,
    window: data.window,
    groups: [
      { key: data.run_id, run: null, holder: data.holder, positions: holderOrder(data.positions) },
    ],
    curves: new Map(data.curves.map((c) => [c.well_id, c])),
  };
}

/** Positions found across runs, with the curves fetched so far. One group per
 *  run that has a position, in the API's run order, leaving out runs whose
 *  status is hidden; the signals are the union over those runs. */
export function curveSetFromPositions(
  found: CurvePositions,
  args: {
    channel: string | undefined;
    view: CurveView;
    window: number | null;
    curves: ReadonlyMap<string, CurveSeriesData>;
    hideStatuses?: readonly string[];
  },
): CurveSet {
  const groups: CurveGroup[] = [];
  const channels = new Map<string, RunCurves["channels"][number]>();
  for (const r of found.runs) {
    if (args.hideStatuses?.includes(r.status)) continue;
    const positions = found.positions.filter((p) => p.run_id === r.run_id);
    if (positions.length === 0) continue;
    for (const c of r.channels) if (!channels.has(c.key)) channels.set(c.key, c);
    groups.push({
      key: r.run_id,
      run: {
        runId: r.run_id,
        runDate: r.run_date,
        operator: r.operator,
        status: r.status,
        notes: r.notes,
      },
      holder: r.holder,
      positions: holderOrder(positions),
    });
  }
  return {
    doseUnit: found.dose_unit,
    channels: [...channels.values()],
    channel: args.channel ?? channels.keys().next().value ?? null,
    view: args.view,
    window: args.window,
    groups,
    curves: args.curves,
  };
}

/** A run group's heading. Two runs on one date are told apart by the start of
 *  their notes, or by a short id when a run has none. */
export function runHeading(
  run: CurveRunInfo,
  opts: { scientist: string; sameDate: boolean },
): string {
  const status = RUN_STATUS_LABELS[run.status as RunStatus] ?? run.status;
  const heading = `${run.runDate} · ${opts.scientist} · ${status}`;
  if (!opts.sameDate) return heading;
  const notes = run.notes?.trim();
  return `${heading} · ${notes ? notes.slice(0, 40) : `Run ${shortId(run.runId)}`}`;
}

/** The ids of the runs that share their date with another run. */
export function runsSharingADate(runs: readonly CurveRunInfo[]): ReadonlySet<string> {
  const count = new Map<string, number>();
  for (const r of runs) count.set(r.runDate, (count.get(r.runDate) ?? 0) + 1);
  return new Set(runs.filter((r) => (count.get(r.runDate) ?? 0) > 1).map((r) => r.runId));
}

/** Group order, then holder order. */
export function orderedPositions(set: CurveSet): CurvePosition[] {
  return set.groups.flatMap((g) => g.positions);
}

export type ColourMode = "highlight" | "distinct" | "group";
export type GroupBy = "run" | "compound" | "batch" | "role";
export type CurvePalette = "dark" | "light";

/** The key of a position's colour group; `groupKey` is its CurveGroup's key. */
export function colourGroupKey(p: CurvePosition, groupKey: string, by: GroupBy): string {
  if (by === "run") return groupKey;
  if (by === "compound") return p.molecule_id ?? "none";
  if (by === "batch") return p.batch_id ?? "none";
  return p.well_type;
}

export function colourGroupLabel(p: CurvePosition, runHeading: string | null, by: GroupBy): string {
  if (by === "run") return runHeading ?? "Run";
  if (by === "compound") return p.molecule_name ?? "No compound";
  if (by === "batch") return p.batch_number ?? "No batch";
  return WELL_TYPE_LABELS[p.well_type as WellType] ?? p.well_type;
}

export interface CurveColouring {
  /** Distinct and group use `slots`; a position without a slot gets highlight colours. */
  colourMode: ColourMode;
  /** Distinct: by well id. Group: by group key. */
  slots: ReadonlyMap<string, number>;
  /** Group mode: the colour group of each selected position, by well id. */
  groups?: ReadonlyMap<string, { key: string; label: string }>;
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
  position: Pick<CurvePosition, "well_id" | "well_type">,
  c: CurveColouring,
): CurveStyle {
  const colours = MEASURED_CURVE_COLORS[c.palette];
  const focused = c.focusedId === position.well_id;
  const slotKey =
    c.colourMode === "distinct"
      ? position.well_id
      : c.colourMode === "group"
        ? c.groups?.get(position.well_id)?.key
        : undefined;
  const slot = slotKey === undefined ? undefined : c.slots.get(slotKey);
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

export function positionName(p: Pick<CurvePosition, "position_label" | "label">): string {
  return p.label ? `${p.position_label} · ${p.label}` : p.position_label;
}

export function currentChannel(set: CurveSet) {
  return set.channels.find((c) => c.key === set.channel);
}

export function buildCurveFigure(
  args: {
    set: CurveSet;
    drawn: ReadonlySet<string>;
    showReported: boolean;
    canvas: "screen" | "export";
  } & CurveColouring,
): { data: Record<string, unknown>[]; layout: Record<string, unknown> } {
  const { set, drawn, showReported, canvas } = args;
  const exporting = canvas === "export";
  // The exported figure sits on white, so it always takes the light set.
  const colouring: CurveColouring = {
    ...args,
    palette: exporting ? "light" : args.palette,
    focusedId: exporting ? null : args.focusedId,
  };
  const channel = currentChannel(set);
  const xUnit = channel?.x_unit ?? "";
  const xTitle = channel?.x_label ? `${channel.x_label} [${xUnit}]` : xUnit;

  const traces: Record<string, unknown>[] = [];
  const shapes: Record<string, unknown>[] = [];
  const byGroup = colouring.colourMode === "group";
  const inLegend = new Set<string>();
  for (const p of orderedPositions(set)) {
    const curve = set.curves.get(p.well_id);
    if (!drawn.has(p.well_id) || !curve) continue;
    const style = curveStyle(p, colouring);
    // By group, the legend has one entry per group; the hover still names the
    // position. A drawn position with no group is a reference the switch added.
    const group = byGroup
      ? (colouring.groups?.get(p.well_id) ?? { key: "", label: "Reference positions" })
      : null;
    const firstOfGroup = group !== null && !inLegend.has(group.key);
    if (group) inLegend.add(group.key);
    traces.push({
      type: "scatter",
      mode: "lines",
      x: curve.x,
      y: curve.y,
      name: group ? group.label : positionName(p),
      meta: p.well_id,
      line: { color: style.color, width: style.width },
      opacity: style.opacity,
      hovertemplate: `<b>${group ? positionName(p) : "%{fullData.name}"}</b><br>%{x} ${xUnit} · %{y:.4g}<extra></extra>`,
      ...(group && { legendgroup: group.key, showlegend: firstOfGroup }),
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
    : set.view === "derivative"
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
      showlegend: exporting && colouring.colourMode !== "highlight",
      hovermode: "closest",
      font: { color: ink, size: 12 },
      shapes,
      xaxis: { title: { text: xTitle }, gridcolor: grid, linecolor: grid, zeroline: false },
      yaxis: {
        title: { text: yTitle },
        gridcolor: grid,
        linecolor: grid,
        zeroline: false,
        uirevision: `${set.channel}:${set.view}`,
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
export function reportedColumns(set: CurveSet): ReportedColumn[] {
  const columns = new Map<string, ReportedColumn & { kind: string; ordinal: number }>();
  for (const curve of set.curves.values()) {
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

/** Positions to draw that have no curve in the set, in the order given. */
export function positionsNotShown(set: CurveSet, drawn: readonly string[]): CurvePosition[] {
  const byId = new Map(orderedPositions(set).map((p) => [p.well_id, p]));
  return drawn.flatMap((id) => {
    const p = byId.get(id);
    return p && !set.curves.has(id) ? [p] : [];
  });
}

export interface CurveTableRow {
  wellId: string;
  /** The position's run; null on a set without run information. */
  run: CurveRunInfo | null;
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

export function tableRows(set: CurveSet, selected: ReadonlySet<string>): CurveTableRow[] {
  return set.groups.flatMap((g) =>
    g.positions
      .filter((p) => selected.has(p.well_id))
      .map((p) => ({
        wellId: p.well_id,
        run: g.run,
        wellType: p.well_type,
        positionLabel: p.position_label,
        label: p.label,
        compound: p.molecule_name ?? null,
        batch: p.batch_number ?? null,
        dose: p.dose ?? null,
        role: WELL_TYPE_LABELS[p.well_type as WellType] ?? p.well_type,
        note: p.note,
        reported: Object.fromEntries(
          (set.curves.get(p.well_id)?.reported ?? []).map((r) => [reportedKey(r), r.value]),
        ),
      })),
  );
}
