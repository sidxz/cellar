import { CHART_COLORS } from "@/shared/lib/chart-colors";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { tooltipText } from "../appearance";
import { isComparedValue, missingReason, pairCounts } from "../cross-protocol";
import { numberAt } from "../dataset";
import { type Figure, axisTitle } from "./common";
import { WEBGL_ABOVE, plottedX, plottedY } from "./scatter";

const NO_VALUE = "No value";
const NOT_TESTED = "Not tested";
const STRIP_FILL = "rgba(113,113,122,0.08)";

/** Where row ``i`` sits around its slot: within ±0.3, the same on every build. */
const jitter = (i: number) => (((i * 0.6180339887) % 1) - 0.5) * 0.6;

const lower = (s: string) => s[0].toLowerCase() + s.slice(1);

/** "1 measured pair · 3 not tested in Counter · 2 no value" over the passing rows. */
function pairNote(ds: Dataset, x: string, y: string, mask: Uint8Array): string {
  const { pairs, missing } = pairCounts(ds, x, y, mask);
  return [
    `${pairs.toLocaleString()} measured ${pairs === 1 ? "pair" : "pairs"}`,
    ...missing.map((m) => `${m.n.toLocaleString()} ${lower(m.reason)}`),
  ].join(" · ");
}

type Side = "x" | "y";

/** The strip of ``side``'s missing values: passing rows with a value on the other axis but
 * none on ``side``, in one slot per kind of reason ("Not tested" before "No value"; the
 * protocol stays in each point's hover), jittered across the slot. */
function stripOf(ds: Dataset, cfg: PanelConfig, mask: Uint8Array, side: Side, dark: boolean) {
  const onX = side === "x";
  const key = (onX ? cfg.x : cfg.y) as string;
  const otherAt = onX ? plottedY(ds, cfg) : plottedX(ds, cfg);
  const reasons = new Map<number, string>();
  const bySlot = new Map<string, number[]>();
  for (let i = 0; i < ds.row_count; i++) {
    if (!mask[i] || numberAt(ds, key, i) !== null || otherAt(i) === null) continue;
    const reason = missingReason(ds, key, i) ?? NO_VALUE;
    const slot = reason.startsWith(NOT_TESTED) ? NOT_TESTED : NO_VALUE;
    reasons.set(i, reason);
    const rows = bySlot.get(slot);
    if (rows) rows.push(i);
    else bySlot.set(slot, [i]);
  }
  if (bySlot.size === 0) return null;

  const slots = [...bySlot.keys()].sort((a, b) => +(a === NO_VALUE) - +(b === NO_VALUE));
  const points = slots.flatMap((s, k) => (bySlot.get(s) ?? []).map((i) => ({ i, k })));
  const rows = points.map((p) => p.i);
  const across = points.map((p) => p.k + jitter(p.i));
  const along = rows.map(otherAt);
  const otherTitle = onX
    ? axisTitle(ds, cfg.y, cfg.logY)
    : axisTitle(ds, cfg.x, cfg.logX && cfg.x !== "run_date");
  const trace = {
    type: rows.length > WEBGL_ABOVE ? "scattergl" : "scatter",
    mode: "markers",
    uid: onX ? "strip" : "strip-y",
    name: onX ? "No X value" : "No Y value",
    showlegend: false,
    xaxis: onX ? "x2" : "x",
    yaxis: onX ? "y" : "y2",
    x: onX ? across : along,
    y: onX ? along : across,
    customdata: rows,
    text: rows.map((i) => `${tooltipText(ds, i, cfg.appearance.tooltip)}<br>${reasons.get(i)}`),
    hovertemplate: `%{text}<br>${otherTitle}: %{${onX ? "y" : "x"}}<extra></extra>`,
    marker: {
      symbol: onX ? "line-ns-open" : "line-ew-open",
      size: 10,
      color: CHART_COLORS.neutral,
      line: { color: CHART_COLORS.neutral, width: 0 },
    },
    selected: { marker: { opacity: 1, color: dark ? "#f1f5f9" : "#111827" } },
    unselected: { marker: { opacity: 0.35 } },
  };
  // Free at the plot's edge, beside the main axis's ticks, so the two strips never collide.
  const axis = {
    domain: [0, 0.08],
    anchor: "free",
    position: 0,
    range: [-0.5, slots.length - 0.5],
    tickvals: slots.map((_, k) => k),
    ticktext: slots.map((s) => `${s} (${(bySlot.get(s) ?? []).length.toLocaleString()})`),
    ...(onX ? { tickangle: -90 } : {}),
    tickfont: { size: 10 },
    showgrid: false,
    zeroline: false,
    fixedrange: true,
    automargin: true,
  };
  const shape = {
    type: "rect",
    xref: onX ? "x2 domain" : "x domain",
    x0: 0,
    x1: 1,
    yref: onX ? "y domain" : "y2 domain",
    y0: 0,
    y1: 1,
    fillcolor: STRIP_FILL,
    line: { width: 0 },
    layer: "below",
  };
  return { trace, axis, shape, count: rows.length };
}

/** A cross-protocol scatter's untested compounds, kept apart from the measured pairs: the
 * footer counts pairs and why the other rows have none; on an unsplit plot, passing rows
 * with a Y but no X (a protocol's X) sit on a categorical strip left of the X axis, and
 * rows with an X but no Y (a protocol's Y) on one below it, selectable like any point.
 * Overlays stay on the main axes, so guides stop at the strips. */
export function addMissingStrip(
  fig: Figure,
  ds: Dataset,
  cfg: PanelConfig,
  mask: Uint8Array,
  dark = false,
): { fig: Figure; stripped: number } {
  const { x, y } = cfg;
  if (!x || !y || (!isComparedValue(ds, x) && !isComparedValue(ds, y))) {
    return { fig, stripped: 0 };
  }
  const counted = { ...fig, note: pairNote(ds, x, y, mask) };
  if (cfg.appearance.splitBy) return { fig: counted, stripped: 0 };

  const strips = (["x", "y"] as const).map((side) =>
    isComparedValue(ds, side === "x" ? x : y) ? stripOf(ds, cfg, mask, side, dark) : null,
  );
  const [xs, ys] = strips;
  if (!xs && !ys) return { fig: counted, stripped: 0 };

  const layout = fig.layout;
  const shapes = (layout.shapes as Record<string, unknown>[] | undefined) ?? [];
  return {
    stripped: (xs?.count ?? 0) + (ys?.count ?? 0),
    fig: {
      ...counted,
      data: [...fig.data, ...(xs ? [xs.trace] : []), ...(ys ? [ys.trace] : [])],
      layout: {
        ...layout,
        // Each main axis makes room for the other's strip and stands beyond it.
        xaxis: {
          ...(layout.xaxis as object),
          ...(xs && { domain: [0.11, 1] }),
          ...(ys && { anchor: "free", position: 0 }),
        },
        yaxis: {
          ...(layout.yaxis as object),
          ...(ys && { domain: [0.11, 1] }),
          ...(xs && { anchor: "free", position: 0 }),
        },
        ...(xs && { xaxis2: xs.axis }),
        ...(ys && { yaxis2: ys.axis }),
        shapes: [...shapes, ...(xs ? [xs.shape] : []), ...(ys ? [ys.shape] : [])],
      },
    },
  };
}
