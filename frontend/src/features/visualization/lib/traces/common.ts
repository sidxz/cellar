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
}

const collator = new Intl.Collator(undefined, { numeric: true });

/** A category column's distinct display labels, natural order, "(none)" last. */
export function levels(ds: Dataset, key: string): string[] {
  const seen = new Set<string>();
  for (const v of ds.values[key] ?? []) seen.add(categoryLabel(key, v));
  return [...seen].sort(
    (a, b) => Number(a === NONE) - Number(b === NONE) || collator.compare(a, b),
  );
}

/** Groups of a category column: up to MAX_FACETS named, the rest pooled as "Other".
 * Built from every row, so groups never move as filters change. */
export function facetsOf(ds: Dataset, key: string | undefined) {
  const all = key ? levels(ds, key) : [];
  if (!key || all.length === 0) return { labels: [""], of: (_i: number) => 0 };
  const index = new Map(all.map((label, k) => [label, Math.min(k, MAX_FACETS)]));
  const labels = all.length > MAX_FACETS ? [...all.slice(0, MAX_FACETS), OTHER] : all;
  return { labels, of: (i: number) => index.get(categoryLabel(key, ds.values[key]?.[i])) ?? 0 };
}

/** "CEL-12 · Plate 3 B07": what a hovered point is. */
export function hoverText(ds: Dataset, i: number): string {
  const plate = ds.values.plate?.[i];
  const place = [plate != null ? `Plate ${plate}` : null, ds.values.well?.[i]].filter(Boolean);
  return [ds.values.compound?.[i] ?? "No compound", place.join(" ")].filter(Boolean).join(" · ");
}

export function axisTitle(ds: Dataset, key: string | undefined, log?: boolean): string {
  const label = key ? (column(ds, key)?.label ?? key) : "—";
  return log ? `${label} (log)` : label;
}

/** A category label's color: well types keep WELL_TYPE_COLORS, "(none)" is neutral,
 * anything else takes its place in ``order`` around GROUP_PALETTE. */
export function categoryColor(key: string, label: string, order: string[]): string {
  if (label === NONE) return CHART_COLORS.neutral;
  if (key === "well_type") {
    const type = Object.keys(WELL_TYPE_COLORS).find((t) => categoryLabel(key, t) === label);
    return type ? WELL_TYPE_COLORS[type] : CHART_COLORS.neutral;
  }
  return GROUP_PALETTE[Math.max(0, order.indexOf(label)) % GROUP_PALETTE.length];
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
