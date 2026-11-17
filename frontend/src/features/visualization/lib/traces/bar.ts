import { CHART_COLORS } from "@/shared/lib/chart-colors";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { numberAt } from "../dataset";
import {
  type Figure,
  MAX_CATEGORIES,
  axis,
  axisTitle,
  baseLayout,
  categoryColor,
  edgeColor,
  groupsOf,
  isCensored,
  lackNote,
  panelNote,
} from "./common";

export const mean = (vs: number[]) => vs.reduce((a, b) => a + b, 0) / vs.length;
export function median(vs: number[]): number {
  const s = [...vs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** One bar per ``cfg.category`` value (every value up to MAX_CATEGORIES, natural order, so
 * bars stay put as filters change): the count of passing rows, or the mean/median of their
 * ``cfg.y`` — censored values left out and counted in the note. */
export function buildBarFigure(
  ds: Dataset,
  cfg: PanelConfig,
  mask: Uint8Array,
  dark = false,
): Figure {
  const key = cfg.category;
  const agg = cfg.agg ?? "count";
  const groups = key ? groupsOf(ds, key, MAX_CATEGORIES) : { labels: [], of: () => 0 };
  const labels = groups.labels;
  const counts = labels.map(() => 0);
  const values: number[][] = labels.map(() => []);
  let skipped = 0;
  let censored = 0;
  for (let i = 0; key && i < mask.length; i++) {
    if (!mask[i]) continue;
    const k = groups.of(i);
    counts[k] += 1;
    if (agg === "count") continue;
    const v = cfg.y ? numberAt(ds, cfg.y, i) : null;
    if (v === null) skipped += 1;
    else if (isCensored(ds, cfg.y as string, i)) censored += 1;
    else values[k].push(v);
  }

  const yLabel = axisTitle(ds, cfg.y);
  const y =
    agg === "count"
      ? counts
      : values.map((vs) => (vs.length ? (agg === "mean" ? mean(vs) : median(vs)) : null));
  const yTitle = agg === "count" ? "Count" : `${agg === "mean" ? "Mean" : "Median"} ${yLabel}`;

  return {
    data: [
      {
        type: "bar",
        x: labels,
        y,
        hovertext: values.map((vs) => `n = ${vs.length}`),
        hovertemplate:
          agg === "count"
            ? "%{x}: %{y}<extra></extra>"
            : "%{x}: %{y}<br>%{hovertext}<extra></extra>",
        marker: {
          color:
            key === "well_type"
              ? labels.map((label, k) => categoryColor(ds, key, label, k))
              : CHART_COLORS.primary,
          line: { color: edgeColor(dark), width: 0.5 },
        },
      },
    ],
    layout: {
      ...baseLayout(cfg.id),
      xaxis: axis(axisTitle(ds, key), {
        type: "category",
        categoryorder: "array",
        categoryarray: labels,
      }),
      yaxis: axis(cfg.logY ? `${yTitle} (log)` : yTitle, { type: cfg.logY ? "log" : "linear" }),
    },
    skipped,
    note: panelNote(lackNote(skipped, yLabel), censored),
  };
}
