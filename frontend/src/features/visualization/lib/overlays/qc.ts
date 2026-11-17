import { Z_PRIME_BADGE } from "@/features/screening-assay/components/z-prime-badge";
import { type ZPrimeQuality, classifyZPrime } from "@/features/screening-assay/lib/qc-metrics";
import {
  READOUT_NORMALIZATION_LABELS,
  type ReadoutNormalization,
} from "@/features/screening-assay/types";
import { CHART_COLORS } from "@/shared/lib/chart-colors";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { categoryLabel, column } from "../dataset";
import { type Facet, wellColorsOf } from "../traces/common";
import { plottedX, plottedY } from "../traces/scatter";
import type { OverlayParts } from "./build";
import { linearFit, meanSd } from "./math";

/** Well types that get bands and trends, in legend order. */
const CONTROLS = ["negative_control", "positive_control", "blank", "reference"];

const Z_PRIME_HOVER =
  "Stored plate Z′ from the run's QC — the Heat Map's value, not recomputed here.";
const Z_PRIME_COLORS: Record<ZPrimeQuality, string> = {
  excellent: CHART_COLORS.success,
  marginal: CHART_COLORS.warning,
  poor: CHART_COLORS.error,
};

export const parts = (p: Partial<OverlayParts>): OverlayParts => ({
  traces: [],
  shapes: [],
  annotations: [],
  notes: [],
  ...p,
});

/** A facet's note: "Plate 3: no control wells", or the bare sentence when unsplit. */
export const say = (f: Facet, text: string) =>
  f.label ? `${f.label}: ${text}` : text[0].toUpperCase() + text.slice(1);

/** One control type's wells in a facet: ``drawn`` = plotted (passing, X and Y present),
 * ``used`` = those the math takes (outlier-flagged wells left out). */
interface Controls {
  type: string;
  label: string;
  /** Its well-type colour, by effect under the protocol's convention. */
  color: string;
  drawn: number[];
  used: number[];
}

/** The plotted control wells of each facet, by type in CONTROLS order. */
function controlsOf(ds: Dataset, p: PanelConfig, mask: Uint8Array, facets: Facet[]) {
  const xAt = plottedX(ds, p);
  const yAt = plottedY(ds, p);
  const types = ds.values.well_type ?? [];
  const flags = ds.values[`${p.y}:outlier`];
  const colors = wellColorsOf(ds);
  return facets.map((f) => {
    const byType = new Map<string, Controls>();
    for (const i of f.rows) {
      const type = types[i] as string;
      if (!mask[i] || !CONTROLS.includes(type) || xAt(i) === null || yAt(i) === null) continue;
      let c = byType.get(type);
      if (!c) {
        c = {
          type,
          label: categoryLabel("well_type", type),
          color: colors[type],
          drawn: [],
          used: [],
        };
        byType.set(type, c);
      }
      c.drawn.push(i);
      if (!flags?.[i]) c.used.push(i);
    }
    return CONTROLS.flatMap((t) => byType.get(t) ?? []);
  });
}

/** Why ``c`` gets no ``what``: one usable well, or every well flagged. */
const tooFew = (c: Controls, what: string) =>
  c.used.length === 0
    ? `${c.label} wells are all flagged outliers — no ${what}`
    : `1 ${c.label} well — no ${what}`;

/** Runs ``draw`` over each facet that has control wells; facets without any get a note
 * (one unprefixed note when no facet has them). */
function eachFacet(
  ds: Dataset,
  p: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
  draw: (f: Facet, controls: Controls[], notes: string[]) => void,
): string[] {
  const all = controlsOf(ds, p, mask, facets);
  if (all.every((c) => c.length === 0)) return ["No control wells"];
  const notes: string[] = [];
  facets.forEach((f, k) => {
    if (all[k].length === 0) notes.push(say(f, "no control wells"));
    else draw(f, all[k], notes);
  });
  return notes;
}

/** A translucent band in ``color``; the first of each ``name`` takes the legend. */
function band(
  color: string,
  name: string,
  shown: Set<string>,
  place: Record<string, unknown>,
  stats: { mean: number; sd: number },
): Record<string, unknown> {
  const first = !shown.has(name);
  shown.add(name);
  return {
    type: "rect",
    ...place,
    y0: stats.mean - 3 * stats.sd,
    y1: stats.mean + 3 * stats.sd,
    // Alpha on the colors, not shape opacity: the legend swatch takes the shape's opacity.
    fillcolor: `${color}14`,
    line: { width: 1, color: `${color}66` },
    layer: "below",
    name,
    legendgroup: name,
    showlegend: first,
  };
}

/** The flat mean ± 3 SD band of ``c``'s plotted Y across facet ``f``; null below 2 wells. */
function flatBand(
  f: Facet,
  c: Controls,
  yAt: (i: number) => number | null,
  shown: Set<string>,
): Record<string, unknown> | null {
  const stats = meanSd(c.used.map((i) => yAt(i) as number));
  if (stats?.sd == null) return null;
  const place = { xref: `${f.xaxis} domain`, x0: 0, x1: 1, yref: f.yaxis };
  return band(c.color, `${c.label} ± 3 SD`, shown, place, { ...stats, sd: stats.sd });
}

/** Mean ± 3 SD of each control type's plotted Y, across each facet. */
export function drawBands(
  ds: Dataset,
  p: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  const yAt = plottedY(ds, p);
  const shapes: Record<string, unknown>[] = [];
  const shown = new Set<string>();
  const notes = eachFacet(ds, p, mask, facets, (f, controls, notes) => {
    for (const c of controls) {
      const shape = flatBand(f, c, yAt, shown);
      if (shape) shapes.push(shape);
      else notes.push(say(f, tooFew(c, "band")));
    }
  });
  return parts({ shapes, notes });
}

/** Bands per plate row (X = Well order) or plate column (X = Column): each spans its
 * group's plotted X, so drift along the plate shows as steps. With Control bands on, a
 * control type that gets no drift band in a facet keeps its flat band there. The rows
 * without a band are counted once per control type, across facets. */
export function drawDriftBands(
  ds: Dataset,
  p: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  const byRow = p.x === "well_order";
  const noun = byRow ? "plate row" : "plate column";
  const groupOf = ds.values[byRow ? "well_row" : "well_column"] ?? [];
  const key = (i: number) => {
    const g = groupOf[i];
    return g === null || g === undefined || g === "" ? null : String(g);
  };
  const xAt = plottedX(ds, p);
  const yAt = plottedY(ds, p);
  const fallback = Boolean(p.overlays?.bands);
  const shapes: Record<string, unknown>[] = [];
  const shown = new Set<string>();
  // Per control type: its label, plate rows/columns without a band, facets on the flat band.
  const lacking = new Map<string, { label: string; short: number; flat: number }>();
  const notes = eachFacet(ds, p, mask, facets, (f, controls) => {
    // Each group's span over every plotted row, samples included.
    const span = new Map<string, [number, number]>();
    for (const i of f.rows) {
      const g = key(i);
      const x = xAt(i) as number | null;
      if (!mask[i] || g === null || x === null || yAt(i) === null) continue;
      const s = span.get(g);
      span.set(g, s ? [Math.min(s[0], x), Math.max(s[1], x)] : [x, x]);
    }
    for (const c of controls) {
      const used = new Map<string, number[]>();
      for (const i of c.used) {
        const g = key(i);
        if (g === null) continue;
        const ys = used.get(g);
        if (ys) ys.push(yAt(i) as number);
        else used.set(g, [yAt(i) as number]);
      }
      const groups = new Set(c.drawn.map(key).filter((g): g is string => g !== null));
      let short = 0;
      for (const g of groups) {
        const stats = meanSd(used.get(g) ?? []);
        const s = span.get(g);
        if (stats?.sd == null || !s) {
          short += 1;
          continue;
        }
        const place = { xref: f.xaxis, x0: s[0] - 0.5, x1: s[1] + 0.5, yref: f.yaxis };
        const name = `${c.label} ± 3 SD per ${noun}`;
        shapes.push(band(c.color, name, shown, place, { ...stats, sd: stats.sd }));
      }
      const flat = short === groups.size && fallback ? flatBand(f, c, yAt, shown) : null;
      if (flat) shapes.push(flat);
      const tally = lacking.get(c.type) ?? { label: c.label, short: 0, flat: 0 };
      lacking.set(c.type, {
        ...tally,
        short: tally.short + short,
        flat: tally.flat + (flat ? 1 : 0),
      });
    }
  });
  for (const type of CONTROLS) {
    const t = lacking.get(type);
    if (!t?.short) continue;
    const where = `${t.short} ${noun}${t.short === 1 ? "" : "s"}`;
    const instead = t.flat ? "; flat ± 3 SD band instead" : "";
    notes.push(`No ${t.label} band in ${where} — fewer than 2 wells${instead}`);
  }
  return parts({ shapes, notes });
}

/** A dashed least-squares line per facet and control type, over the type's plotted X. */
export function drawTrends(
  ds: Dataset,
  p: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  const xAt = plottedX(ds, p);
  const yAt = plottedY(ds, p);
  const traces: Record<string, unknown>[] = [];
  const shown = new Set<string>();
  const notes = eachFacet(ds, p, mask, facets, (f, controls, notes) => {
    for (const c of controls) {
      const xs = c.used.map((i) => xAt(i) as number);
      const fit = linearFit(
        xs,
        c.used.map((i) => yAt(i) as number),
      );
      if (!fit) {
        const why =
          c.used.length < 2 ? tooFew(c, "trend") : `${c.label} wells share one X — no trend`;
        notes.push(say(f, why));
        continue;
      }
      const x0 = xs.reduce((a, b) => Math.min(a, b));
      const x1 = xs.reduce((a, b) => Math.max(a, b));
      const name = `${c.label} trend`;
      traces.push({
        type: "scatter",
        mode: "lines",
        name,
        legendgroup: name,
        showlegend: !shown.has(name),
        xaxis: f.xaxis,
        yaxis: f.yaxis,
        x: [x0, x1],
        y: [fit.slope * x0 + fit.intercept, fit.slope * x1 + fit.intercept],
        line: { color: c.color, dash: "dash", width: 1.5 },
        hoverinfo: "skip",
      });
      shown.add(name);
    }
  });
  return parts({ traces, notes });
}

const lowest = (values: Array<number | null>) =>
  values.reduce<number | null>((lo, v) => (v === null || (lo !== null && lo <= v) ? lo : v), null);

/** "Z′ 0.712 · Excellent · stored": the stored per-plate values of a facet with the Heat
 * Map's precision and class (of the lowest value), a range and plate count for several;
 * ``layer`` ("% Inhibition") follows the value when the Z′ is the plotted layer's own. */
export function zPrimeLabel(values: Array<number | null>, layer?: string): string {
  const lo = lowest(values);
  if (lo === null) return "Z′ not stored";
  const hi = values.reduce<number>((h, v) => (v !== null && v > h ? v : h), lo);
  const range =
    lo.toFixed(3) === hi.toFixed(3) ? lo.toFixed(3) : `${lo.toFixed(3)}–${hi.toFixed(3)}`;
  const stored = values.filter((v) => v !== null).length;
  const count =
    values.length === 1
      ? ""
      : stored === values.length
        ? ` (${stored} plates)`
        : ` (${stored} of ${values.length} plates)`;
  const of = layer ? ` · ${layer}` : "";
  return `Z′ ${range}${of} · ${Z_PRIME_BADGE[classifyZPrime(lo)].label} · stored${count}`;
}

/** The layer of value column ``key`` in words: "Raw", "% Inhibition". */
function layerName(ds: Dataset, key: string): string {
  const layer = column(ds, key)?.provenance?.layer;
  if (!layer || layer === "raw") return "Raw";
  return READOUT_NORMALIZATION_LABELS[layer as ReadoutNormalization] ?? layer;
}

/** Each facet's stored plate Z′, top right inside the facet, colored by its class. */
export function drawZPrime(
  ds: Dataset,
  p: PanelConfig,
  _mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  const ids = ds.values.plate_id ?? [];
  // The plotted readout layer's own Z′ when its plates stored one (the plate QC per
  // readout x layer); otherwise the run's stored Z′, as before.
  const own = p.y ? ds.plate_z_prime_by_column?.[p.y] : undefined;
  const stored = own ?? ds.plate_z_prime ?? {};
  const layer = own && p.y ? layerName(ds, p.y) : undefined;
  const annotations: Record<string, unknown>[] = [];
  for (const f of facets) {
    const plates = new Set<string>();
    for (const i of f.rows) {
      const id = ids[i];
      if (typeof id === "string" && id) plates.add(id);
    }
    if (plates.size === 0) continue;
    const values = [...plates].map((id) => stored[id] ?? null);
    const lo = lowest(values);
    annotations.push({
      text: zPrimeLabel(values, layer),
      xref: `${f.xaxis} domain`,
      yref: `${f.yaxis} domain`,
      x: 1,
      y: 1,
      xanchor: "right",
      yanchor: "top",
      showarrow: false,
      font: {
        size: 10,
        color: lo === null ? CHART_COLORS.neutral : Z_PRIME_COLORS[classifyZPrime(lo)],
      },
      hovertext: Z_PRIME_HOVER,
    });
  }
  return parts({ annotations });
}
