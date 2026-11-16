import { CHART_COLORS } from "@/shared/lib/chart-colors";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { tooltipText } from "../appearance";
import { isComparedValue, missingReason, pairCounts } from "../cross-protocol";
import { numberAt } from "../dataset";
import { type Figure, axisTitle } from "./common";
import { WEBGL_ABOVE, plottedY } from "./scatter";

const NO_VALUE = "No value";
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

/** A cross-protocol scatter's untested compounds, kept apart from the measured pairs: the
 * footer counts pairs and why the other rows have none; on an unsplit plot whose X a protocol
 * measured, passing rows with a Y but no X sit on a categorical strip left of the numeric axis
 * (one slot per reason, "Not tested in …" before "No value"), selectable like any point.
 * Overlays stay on the main axis, so guides stop at the strip. */
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
  if (!isComparedValue(ds, x) || cfg.appearance.splitBy) return { fig: counted, stripped: 0 };

  const yAt = plottedY(ds, cfg);
  const bySlot = new Map<string, number[]>();
  for (let i = 0; i < ds.row_count; i++) {
    if (!mask[i] || numberAt(ds, x, i) !== null || yAt(i) === null) continue;
    const reason = missingReason(ds, x, i) ?? NO_VALUE;
    const slot = bySlot.get(reason);
    if (slot) slot.push(i);
    else bySlot.set(reason, [i]);
  }
  if (bySlot.size === 0) return { fig: counted, stripped: 0 };

  const slots = [...bySlot.keys()].sort((a, b) => +(a === NO_VALUE) - +(b === NO_VALUE));
  const points = slots.flatMap((s, k) => (bySlot.get(s) ?? []).map((i) => ({ i, k, s })));
  const rows = points.map((p) => p.i);
  const yTitle = axisTitle(ds, y, cfg.logY);
  const strip = {
    type: rows.length > WEBGL_ABOVE ? "scattergl" : "scatter",
    mode: "markers",
    uid: "strip",
    name: "No X value",
    showlegend: false,
    xaxis: "x2",
    yaxis: "y",
    x: points.map((p) => p.k + jitter(p.i)),
    y: rows.map((i) => numberAt(ds, y, i)),
    customdata: rows,
    text: points.map((p) => `${tooltipText(ds, p.i, cfg.appearance.tooltip)}<br>${p.s}`),
    hovertemplate: `%{text}<br>${yTitle}: %{y}<extra></extra>`,
    marker: {
      symbol: "line-ns-open",
      size: 10,
      color: CHART_COLORS.neutral,
      line: { color: CHART_COLORS.neutral, width: 0 },
    },
    selected: { marker: { opacity: 1, color: dark ? "#f1f5f9" : "#111827" } },
    unselected: { marker: { opacity: 0.35 } },
  };
  const layout = fig.layout;
  return {
    stripped: rows.length,
    fig: {
      ...counted,
      data: [...fig.data, strip],
      layout: {
        ...layout,
        xaxis: { ...(layout.xaxis as object), domain: [0.11, 1] },
        // The Y axis stands left of the strip, which shares it.
        yaxis: { ...(layout.yaxis as object), anchor: "free", position: 0 },
        xaxis2: {
          domain: [0, 0.08],
          anchor: "y",
          range: [-0.5, slots.length - 0.5],
          tickvals: slots.map((_, k) => k),
          ticktext: slots.map((s) => `${s} (${(bySlot.get(s) ?? []).length.toLocaleString()})`),
          tickangle: -90,
          tickfont: { size: 10 },
          showgrid: false,
          zeroline: false,
          fixedrange: true,
          automargin: true,
        },
        shapes: [
          ...((layout.shapes as Record<string, unknown>[] | undefined) ?? []),
          {
            type: "rect",
            xref: "x2 domain",
            x0: 0,
            x1: 1,
            yref: "y domain",
            y0: 0,
            y1: 1,
            fillcolor: STRIP_FILL,
            line: { width: 0 },
            layer: "below",
          },
        ],
      },
    },
  };
}
