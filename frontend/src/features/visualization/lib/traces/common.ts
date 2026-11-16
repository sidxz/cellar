import {
  CHART_AXIS,
  CHART_COLORS,
  GROUP_PALETTE,
  WELL_TYPE_COLORS,
} from "@/shared/lib/chart-colors";
import type { Dataset } from "../../types";
import { categoryLabel, column } from "../dataset";

export const MAX_FACETS = 6;
export const OTHER = "Other";
export const NONE = categoryLabel("", null);
export const GRID = "rgba(113,113,122,0.2)";

/** What every built panel returns: the figure plus the rows it could not plot. */
export interface Figure {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
  /** Passing rows that cannot be plotted (missing value, or ≤ 0 on a log axis). */
  skipped: number;
  /** "38 rows lack Signal (AU)", or null when every passing row is plotted. */
  note: string | null;
  /** The subplots overlays draw into (scatter and box only). */
  facets?: Facet[];
}

/** One subplot: its title, every row it holds whatever the filters, and its axis ids. */
export interface Facet {
  label: string;
  rows: number[];
  xaxis: string;
  yaxis: string;
}

/** Most groups a bar or box panel draws (one bar or box each); the rest pool as "Other". */
export const MAX_CATEGORIES = 500;
const OTHER_COLOR = "#a1a1aa";

const collator = new Intl.Collator(undefined, { numeric: true });

/** Groups of a category column: ``labels`` in display order, ``of(i)`` the index of row
 * ``i``'s group in them. */
export interface Groups {
  labels: string[];
  of: (i: number) => number;
}

interface Tally {
  labels: string[];
  counts: Map<string, number>;
  capped: Map<number, Groups>;
}

// A loaded dataset never changes, so each column is tallied (and sorted) once.
const tallies = new WeakMap<Dataset, Map<string, Tally>>();

function tally(ds: Dataset, key: string): Tally {
  let byKey = tallies.get(ds);
  if (!byKey) {
    byKey = new Map();
    tallies.set(ds, byKey);
  }
  let t = byKey.get(key);
  if (!t) {
    const counts = new Map<string, number>();
    for (const v of ds.values[key] ?? []) {
      const label = categoryLabel(key, v);
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    const labels = [...counts.keys()].sort(
      (a, b) => Number(a === NONE) - Number(b === NONE) || collator.compare(a, b),
    );
    t = { labels, counts, capped: new Map() };
    byKey.set(key, t);
  }
  return t;
}

/** A category column's distinct display labels, natural order, "(none)" last. */
export function levels(ds: Dataset, key: string): string[] {
  return tally(ds, key).labels;
}

/** Groups of a category column: every label when there are at most ``max``, else the
 * ``max`` most frequent (in natural order; ties go to the earlier label) and "Other"
 * pooling the rest. Built from every row, so groups never move as filters change. */
export function groupsOf(ds: Dataset, key: string | undefined, max: number): Groups {
  const t = key ? tally(ds, key) : undefined;
  if (!key || !t || t.labels.length === 0) return { labels: [""], of: () => 0 };
  const cached = t.capped.get(max);
  if (cached) return cached;
  let named = t.labels;
  if (named.length > max) {
    // A stable sort by count keeps natural order among equal counts.
    const count = (label: string) => t.counts.get(label) ?? 0;
    const top = new Set([...named].sort((a, b) => count(b) - count(a)).slice(0, max));
    named = named.filter((label) => top.has(label));
  }
  const index = new Map(named.map((label, k) => [label, k]));
  const values = ds.values[key] ?? [];
  const groups: Groups = {
    labels: named.length < t.labels.length ? [...named, OTHER] : named,
    of: (i) => index.get(categoryLabel(key, values[i])) ?? named.length,
  };
  t.capped.set(max, groups);
  return groups;
}

/** Facets of a split: up to MAX_FACETS named, the rest pooled as "Other". */
export const facetsOf = (ds: Dataset, key: string | undefined) => groupsOf(ds, key, MAX_FACETS);

/** "CEL-12 · Plate 3 B07": what a hovered point is (the plate value is its full label). */
export function hoverText(ds: Dataset, i: number): string {
  const place = [ds.values.plate?.[i], ds.values.well?.[i]].filter(Boolean);
  return [ds.values.compound?.[i] ?? "No compound", place.join(" ")].filter(Boolean).join(" · ");
}

export function axisTitle(ds: Dataset, key: string | undefined, log?: boolean): string {
  const label = key ? (column(ds, key)?.label ?? key) : "—";
  return log ? `${label} (log)` : label;
}

const WELL_TYPE_BY_LABEL = new Map(
  Object.entries(WELL_TYPE_COLORS).map(([type, color]) => [
    categoryLabel("well_type", type),
    color,
  ]),
);

/** The color of label ``k`` of a group list: well types keep WELL_TYPE_COLORS, "(none)" is
 * neutral, "Other" a light grey, anything else its place around GROUP_PALETTE. */
export function categoryColor(key: string, label: string, k: number): string {
  if (label === NONE) return CHART_COLORS.neutral;
  if (label === OTHER) return OTHER_COLOR;
  if (key === "well_type") return WELL_TYPE_BY_LABEL.get(label) ?? CHART_COLORS.neutral;
  return GROUP_PALETTE[k % GROUP_PALETTE.length];
}

/** Whether row ``i``'s ``key`` value is censored: its qualifier is a bound (`>`, `<`), so
 * the true value is unknown and means, medians and boxes leave it out. */
export function isCensored(ds: Dataset, key: string, i: number): boolean {
  const q = ds.values[`${key}:q`]?.[i];
  return typeof q === "string" && (q.startsWith(">") || q.startsWith("<"));
}

/** The panel note: rows lacking a value, then censored values left out. */
export function panelNote(lack: string | null, censored: number): string | null {
  const left = censored
    ? `${censored.toLocaleString()} censored ${censored === 1 ? "value" : "values"} not included`
    : null;
  return [lack, left].filter(Boolean).join(" · ") || null;
}

/** Hairline between bars and around box points: the card surface of the theme. */
export const edgeColor = (dark: boolean) => (dark ? "#1e293b" : "#ffffff");

/** Layout keys every panel shares; ``uirevision`` per panel keeps zoom across redraws. */
export function baseLayout(panelId: string): Record<string, unknown> {
  return {
    autosize: true,
    uirevision: panelId,
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: CHART_AXIS.tick, size: 11 },
    margin: { l: 56, r: 12, t: 32, b: 44 },
    legend: { orientation: "h", x: 1, xanchor: "right", y: 1, yanchor: "top", yref: "container" },
  };
}

export const axis = (title: string, extra: Record<string, unknown> = {}) => ({
  title: { text: title },
  gridcolor: GRID,
  zeroline: false,
  automargin: true,
  ...extra,
});

export function lackNote(skipped: number, what: string): string | null {
  if (!skipped) return null;
  return `${skipped.toLocaleString()} ${skipped === 1 ? "row lacks" : "rows lack"} ${what}`;
}
