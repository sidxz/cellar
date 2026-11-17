import { CHART_COLORS } from "@/shared/lib/chart-colors";
import { formatMeasurementValue as sig } from "@/shared/lib/format-number";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { protocolName } from "../cross-protocol";
import { column } from "../dataset";
import { shortName } from "../short-name";
import { type Facet, isCensored } from "../traces/common";
import { WEBGL_ABOVE, plottedX, plottedY } from "../traces/scatter";
import type { OverlayParts } from "./build";
import { clipDiagonal, meanSd } from "./math";
import { parts, say } from "./qc";

type Mark = Record<string, unknown>;
type Line = { color: string; width: number; dash: string };

const REFERENCE: Line = { color: CHART_COLORS.purple, width: 1.5, dash: "solid" };
const MEAN: Line = { color: CHART_COLORS.neutral, width: 1.2, dash: "solid" };
const LIMIT: Line = { color: CHART_COLORS.warning, width: 1.2, dash: "dash" };
const LIPE: Line = { color: CHART_COLORS.neutral, width: 1, dash: "dot" };
const PARITY: Line = { color: CHART_COLORS.neutral, width: 1, dash: "dot" };
const FOLD: Line = { color: CHART_COLORS.primary, width: 1, dash: "dash" };
const OUTSIDE = "outside-limits";

/** A line shape in ``line``'s style; the first of each ``name`` takes the legend. */
function mark(name: string, shown: Set<string>, place: Mark, line: Line): Mark {
  const first = !shown.has(name);
  shown.add(name);
  return { type: "line", ...place, line, name, legendgroup: name, showlegend: first };
}

/** A horizontal line across facet ``f`` at ``y``. */
const across = (f: Facet, y: number) => ({
  xref: `${f.xaxis} domain`,
  x0: 0,
  x1: 1,
  yref: f.yaxis,
  y0: y,
  y1: y,
});

/** ``text`` just above the point (``x``, ``y``), ending there. */
const label = (text: string, place: Mark, line: Line): Mark => ({
  text,
  ...place,
  xanchor: "right",
  yanchor: "bottom",
  showarrow: false,
  font: { size: 10, color: line.color },
});

/** The rows of ``f`` the scatter plots: passing, with an X and a Y. */
function plottedRows(ds: Dataset, p: PanelConfig, mask: Uint8Array, f: Facet): number[] {
  const xAt = plottedX(ds, p);
  const yAt = plottedY(ds, p);
  return f.rows.filter((i) => mask[i] && xAt(i) !== null && yAt(i) !== null);
}

/** A horizontal line at the user's value in every facet — display only, it changes no
 * hit criteria. */
export function drawRefLine(
  ds: Dataset,
  p: PanelConfig,
  _mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  const v = p.overlays?.refLine as number;
  const unit = p.y ? column(ds, p.y)?.unit : null;
  const name = `Reference ${sig(v)}${unit ? ` ${unit}` : ""} · display only`;
  const shown = new Set<string>();
  const shapes = facets.map((f) => mark(name, shown, across(f, v), REFERENCE));
  const annotations = facets.slice(0, 1).map((f) => {
    const place = { xref: `${f.xaxis} domain`, x: 1, yref: f.yaxis, y: v };
    return label(name, place, REFERENCE);
  });
  return parts({ shapes, annotations });
}

/** Control-chart limits per facet — mean ± 3 SD of the plotted points (censored values left
 * out) or the entered pair — with the points beyond them ringed in the warning color (a
 * censored value only when its bound proves it beyond). */
export function drawLimits(
  ds: Dataset,
  p: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  const limits = p.overlays?.limits;
  if (!limits) return parts({});
  const entered = limits.mode === "entered";
  const name = `Control limits (${entered ? "entered" : "from plotted points"})`;
  const xAt = plottedX(ds, p);
  const yAt = plottedY(ds, p);
  const shown = new Set<string>();
  const shapes: Mark[] = [];
  const annotations: Mark[] = [];
  const notes: string[] = [];
  const outside: { f: Facet; rows: number[] }[] = [];
  let censored = 0;
  facets.forEach((f, k) => {
    const rows = plottedRows(ds, p, mask, f);
    let lines: [number, string, Line][];
    if (limits.mode === "entered") {
      lines = [
        [limits.upper, `Upper ${sig(limits.upper)} · entered`, LIMIT],
        [limits.lower, `Lower ${sig(limits.lower)} · entered`, LIMIT],
      ];
    } else {
      const used = rows.filter((i) => !isCensored(ds, p.y as string, i));
      censored += rows.length - used.length;
      const stats = meanSd(used.map((i) => yAt(i) as number));
      if (stats?.sd == null) {
        notes.push(say(f, "control limits need at least 2 plotted points"));
        return;
      }
      const hi = stats.mean + 3 * stats.sd;
      const lo = stats.mean - 3 * stats.sd;
      lines = [
        [stats.mean, `Mean ${sig(stats.mean)} · from plotted points`, MEAN],
        [hi, `+3 SD ${sig(hi)}`, LIMIT],
        [lo, `−3 SD ${sig(lo)}`, LIMIT],
      ];
    }
    for (const [y, text, line] of lines) {
      shapes.push(mark(name, shown, across(f, y), line));
      // Entered limits are the same everywhere: labeled once.
      if (!entered || k === 0) {
        annotations.push(label(text, { xref: `${f.xaxis} domain`, x: 1, yref: f.yaxis, y }, line));
      }
    }
    const ys = lines.map(([y]) => y);
    const lo = Math.min(...ys);
    const hi = Math.max(...ys);
    const out = rows.filter((i) => {
      const y = yAt(i) as number;
      if (!isCensored(ds, p.y as string, i)) return y < lo || y > hi;
      // A bound is outside only when every value it allows is: ">8" above 8, not ">=8".
      const q = String(ds.values[`${p.y}:q`]?.[i]);
      const strict = !q.endsWith("=");
      return q.startsWith(">") ? y > hi || (strict && y === hi) : y < lo || (strict && y === lo);
    });
    if (out.length) outside.push({ f, rows: out });
  });
  if (censored) {
    const values = censored === 1 ? "value" : "values";
    notes.push(`${censored.toLocaleString()} censored ${values} left out of the control limits`);
  }
  const total = outside.reduce((n, o) => n + o.rows.length, 0);
  const traces = outside.map(({ f, rows }, k) => ({
    type: total > WEBGL_ABOVE ? "scattergl" : "scatter",
    mode: "markers",
    name: `Outside limits (${total.toLocaleString()})`,
    legendgroup: OUTSIDE,
    showlegend: k === 0,
    xaxis: f.xaxis,
    yaxis: f.yaxis,
    x: rows.map(xAt),
    y: rows.map(yAt),
    hoverinfo: "skip",
    marker: {
      symbol: "circle-open",
      size: 14,
      color: CHART_COLORS.warning,
      line: { width: 2, color: CHART_COLORS.warning },
    },
    // A lasso never dims the rings.
    selected: { marker: { opacity: 1 } },
    unselected: { marker: { opacity: 1 } },
  }));
  return parts({ traces, shapes, annotations, notes });
}

type Box = { x0: number; x1: number; y0: number; y1: number };

/** The box around the points the scatter plots in ``f``; null when it plots none. */
function pointsBox(ds: Dataset, p: PanelConfig, mask: Uint8Array, f: Facet): Box | null {
  const rows = plottedRows(ds, p, mask, f);
  if (rows.length === 0) return null;
  const xAt = plottedX(ds, p);
  const yAt = plottedY(ds, p);
  // A loop, not Math.min(...xs): a spread of 100k rows overflows the stack.
  const box = {
    x0: Number.POSITIVE_INFINITY,
    x1: Number.NEGATIVE_INFINITY,
    y0: Number.POSITIVE_INFINITY,
    y1: Number.NEGATIVE_INFINITY,
  };
  for (const i of rows) {
    const x = xAt(i) as number;
    const y = yAt(i) as number;
    box.x0 = Math.min(box.x0, x);
    box.x1 = Math.max(box.x1, x);
    box.y0 = Math.min(box.y0, y);
    box.y1 = Math.max(box.y1, y);
  }
  return box;
}

/** A diagonal guide: ``y = x + offset``, labeled ``text`` (``hover`` in full); ``key`` names
 * the value it draws; ``below`` labels it below-right of its midpoint instead of above-left
 * of its upper end. */
type Diagonal = {
  offset: number;
  text: string;
  hover?: string;
  line: Line;
  key: number;
  below?: boolean;
};

/** ``guides`` clipped to each facet's plotted points (so they never stretch the axes), each
 * labeled at one end, one legend entry ``name``; ``hit`` holds the keys drawn anywhere and
 * ``plotted`` whether any facet plots a point. */
function drawDiagonals(
  ds: Dataset,
  p: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
  name: string,
  guides: Diagonal[],
) {
  const shown = new Set<string>();
  const hit = new Set<number>();
  const shapes: Mark[] = [];
  const annotations: Mark[] = [];
  let plotted = false;
  for (const f of facets) {
    const box = pointsBox(ds, p, mask, f);
    if (!box) continue;
    plotted = true;
    for (const g of guides) {
      const seg = clipDiagonal(g.offset, box);
      if (!seg) continue;
      hit.add(g.key);
      const [x0, y0, x1, y1] = seg;
      const place = { xref: f.xaxis, yref: f.yaxis };
      shapes.push(mark(name, shown, { ...place, x0, y0, x1, y1 }, g.line));
      annotations.push({
        // A lower guide's end sits on the pairs' bottom edge, above the X ticks and any
        // missing-Y strip: its label hangs from the midpoint instead.
        ...label(
          g.text,
          { ...place, x: g.below ? (x0 + x1) / 2 : x1, y: g.below ? (y0 + y1) / 2 : y1 },
          g.line,
        ),
        ...(g.below && { xanchor: "left", yanchor: "top" }),
        ...(g.hover && { hovertext: g.hover }),
      });
    }
  }
  return { shapes, annotations, hit, plotted };
}

/** Dotted LipE guides (pIC50 = logP + LipE) clipped to each facet's plotted points. */
export function drawLipe(
  ds: Dataset,
  p: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  const values = [...new Set(p.overlays?.lipe ?? [])];
  const guides = values.map((v) => ({ offset: v, text: `LipE ${sig(v)}`, line: LIPE, key: v }));
  const { shapes, annotations, hit, plotted } = drawDiagonals(
    ds,
    p,
    mask,
    facets,
    "LipE guides",
    guides,
  );
  const notes = plotted
    ? values.filter((v) => !hit.has(v)).map((v) => `LipE ${sig(v)} lies outside the plotted points`)
    : [];
  return parts({ shapes, annotations, notes });
}

/** Selectivity guides on a p-potency × p-potency scatter of two protocols: parity (1×) and,
 * per fold k, y = x ± log10 k, each saying for which protocol the points beyond it are at
 * least k× selective, labeled inside that region (Y's above-left of the upper guide, X's
 * below-right of the lower one). Clipped to the measured pairs. */
export function drawSelectivity(
  ds: Dataset,
  p: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  const values = [...new Set(p.overlays?.selectivity ?? [])];
  const folds = values.filter((k) => k > 1);
  const protocolOf = (key?: string) =>
    protocolName(ds, (key && column(ds, key)?.provenance.protocol_id) || "");
  const guides: Diagonal[] = [{ offset: 0, text: "1×", line: PARITY, key: 1 }];
  for (const k of folds) {
    const offset = Math.log10(k);
    const fold = `≥${sig(k)}× selective for `;
    const named = (side?: string) => {
      const name = protocolOf(side);
      return { text: fold + shortName(name), hover: fold + name, line: FOLD, key: k };
    };
    guides.push({ offset, ...named(p.y) });
    guides.push({ offset: -offset, ...named(p.x), below: true });
  }
  const { shapes, annotations, hit, plotted } = drawDiagonals(
    ds,
    p,
    mask,
    facets,
    "Selectivity guides",
    guides,
  );
  const notes = [
    ...values
      .filter((k) => !(k > 1))
      .map((k) => `Selectivity fold ${sig(k)} left out: folds start above 1`),
    ...(plotted
      ? folds
          .filter((k) => !hit.has(k))
          .map((k) => `${sig(k)}× guides lie outside the measured pairs`)
      : []),
  ];
  return parts({ shapes, annotations, notes });
}
