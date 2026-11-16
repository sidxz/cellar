import { CHART_COLORS, GROUP_PALETTE } from "@/shared/lib/chart-colors";
import type { Appearance } from "../store/workbench-store";
import type { Dataset } from "../types";
import { column, numberAt } from "./dataset";
import { NONE, categoryColor, groupsOf } from "./traces/common";

export const WELL_TYPE_SYMBOLS: Record<string, string> = {
  sample: "circle",
  negative_control: "square",
  positive_control: "diamond",
  blank: "triangle-up",
  reference: "star",
};
const SYMBOLS = ["circle", "square", "diamond", "triangle-up", "star", "cross", "pentagon"];
export const SIZE_MIN = 5;
export const SIZE_MAX = 16;

const fmt = (v: number) => v.toLocaleString(undefined, { maximumSignificantDigits: 4 });

/** Smallest and largest finite value of a numeric column over every row, if any. */
export function numericRange(ds: Dataset, key: string): [number, number] | null {
  let lo = Number.POSITIVE_INFINITY;
  let hi = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < ds.row_ids.length; i++) {
    const v = numberAt(ds, key, i);
    if (v === null) continue;
    lo = Math.min(lo, v);
    hi = Math.max(hi, v);
  }
  return lo <= hi ? [lo, hi] : null;
}

const hex = (c: string) => [1, 3, 5].map((k) => Number.parseInt(c.slice(k, k + 2), 16));
function mix(a: string, b: string, f: number): string {
  if (f === 0) return a;
  const [p, q] = [hex(a), hex(b)];
  return `#${p
    .map((v, k) =>
      Math.round(v + (q[k] - v) * f)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

/** ``n`` bin colors from low to high along green → amber → red. */
function rampColors(n: number): string[] {
  const stops = [CHART_COLORS.success, CHART_COLORS.warning, CHART_COLORS.error];
  return Array.from({ length: n }, (_, k) => {
    const t = n === 1 ? 0 : (2 * k) / (n - 1);
    const s = Math.min(1, Math.floor(t));
    return mix(stops[s], stops[s + 1], t - s);
  });
}

/** A numeric color-by cut into bins: sorted cut-offs (default: 3 equal-width bins over the
 * whole column, so bins never move as filters change), one color and legend label per bin,
 * and the bin a value falls in (a value on a cut-off belongs to the bin above). */
export function colorBins(ds: Dataset, key: string, cuts?: number[]) {
  let c = cuts?.length ? [...cuts].sort((p, q) => p - q) : [];
  if (!cuts?.length) {
    const r = numericRange(ds, key);
    if (r) {
      // Rounded to about a hundredth of the range, so the inputs show 33, not 33.333….
      const span = r[1] - r[0];
      const digits = span > 0 ? Math.min(20, Math.max(0, 2 - Math.floor(Math.log10(span)))) : 20;
      c = [1, 2].map((k) => Number((r[0] + (span * k) / 3).toFixed(digits)));
    }
  }
  const labels = c.length
    ? [
        `< ${fmt(c[0])}`,
        ...c.slice(1).map((v, k) => `${fmt(c[k])} to ${fmt(v)}`),
        `≥ ${fmt(c[c.length - 1])}`,
      ]
    : ["All"];
  const binOf = (v: number) => {
    let k = 0;
    while (k < c.length && v >= c[k]) k++;
    return k;
  };
  return { cuts: c, colors: rampColors(c.length + 1), labels, binOf };
}

/** Most named color groups (one palette color each); rarer categories pool as "Other". */
export const MAX_COLOR_GROUPS = GROUP_PALETTE.length;

/** Coloring as named groups (legend entries) — a category, or a binned number — or null
 * when nothing colors the plot or a number colors it on a continuous scale. */
export interface ColorGroups {
  /** Every group in legend order: "(none)" after the named ones, "Other" last. */
  order: string[];
  /** Index into ``order`` of row ``i``'s group. */
  of: (i: number) => number;
  /** Color of each group, parallel to ``order``. */
  colors: string[];
  /** Legend title (binned numbers only; categories name themselves). */
  title?: string;
}

export function colorGroups(ds: Dataset, a: Appearance): ColorGroups | null {
  const col = a.colorBy ? column(ds, a.colorBy) : undefined;
  if (!col) return null;
  if (col.kind === "number") {
    if (a.colorMode !== "bins") return null;
    const b = colorBins(ds, col.key, a.colorBins);
    return {
      order: [...b.labels, NONE],
      of: (i) => {
        const v = numberAt(ds, col.key, i);
        return v === null ? b.labels.length : b.binOf(v);
      },
      colors: [...b.colors, CHART_COLORS.neutral],
      title: col.label,
    };
  }
  const g = groupsOf(ds, col.key, MAX_COLOR_GROUPS);
  return {
    order: g.labels,
    of: g.of,
    colors: g.labels.map((label, k) => categoryColor(col.key, label, k)),
  };
}

/** Marker color of each of ``rows``: a color per category or bin, or the value itself for
 * a continuous colorscale (null when missing). Palettes are fixed over the whole dataset,
 * so a row's color never depends on which rows are asked for. */
export function colorFor(ds: Dataset, a: Appearance, rows: number[]): string[] | (number | null)[] {
  const groups = colorGroups(ds, a);
  if (groups) return rows.map((i) => groups.colors[groups.of(i)]);
  const key = a.colorBy;
  if (key && column(ds, key)?.kind === "number") return rows.map((i) => numberAt(ds, key, i));
  return rows.map(() => CHART_COLORS.primary);
}

/** Marker symbol of each of ``rows``: well types keep fixed shapes; other categories take
 * one symbol each, the rarest sharing the last one as "Other". */
export function shapeFor(ds: Dataset, a: Appearance, rows: number[]): string[] {
  const key = a.shapeBy;
  if (!key) return rows.map(() => "circle");
  if (key === "well_type") {
    return rows.map((i) => WELL_TYPE_SYMBOLS[String(ds.values[key]?.[i])] ?? "circle");
  }
  const g = groupsOf(ds, key, SYMBOLS.length - 1);
  return rows.map((i) => SYMBOLS[g.of(i)]);
}

/** Marker size of each of ``rows``: a numeric size-by mapped onto 5–16 px over the whole
 * column (missing → smallest), else ``auto``. */
export function sizeFor(ds: Dataset, a: Appearance, rows: number[], auto: number): number[] {
  const key = a.sizeBy;
  const r = key ? numericRange(ds, key) : null;
  if (!key || !r) return rows.map(() => auto);
  const span = r[1] - r[0];
  return rows.map((i) => {
    const v = numberAt(ds, key, i);
    if (v === null) return SIZE_MIN;
    return span > 0
      ? SIZE_MIN + ((SIZE_MAX - SIZE_MIN) * (v - r[0])) / span
      : (SIZE_MIN + SIZE_MAX) / 2;
  });
}
