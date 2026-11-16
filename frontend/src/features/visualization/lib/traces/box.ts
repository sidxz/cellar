import { CHART_COLORS } from "@/shared/lib/chart-colors";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { categoryLabel, numberAt } from "../dataset";
import {
  type Figure,
  axis,
  axisTitle,
  baseLayout,
  categoryColor,
  edgeColor,
  hoverText,
  lackNote,
  levels,
} from "./common";

// ponytail: SVG box points stall the page past a few thousand; above this only outliers
// are drawn. Raise it if a WebGL box trace ever lands in plotly.js.
const ALL_POINTS_UP_TO = 5000;

/** One box of ``cfg.y`` per ``cfg.category`` value (natural order), passing rows only,
 * with the points drawn over it. */
export function buildBoxFigure(
  ds: Dataset,
  cfg: PanelConfig,
  mask: Uint8Array,
  dark = false,
): Figure {
  const key = cfg.category;
  const yTitle = axisTitle(ds, cfg.y, cfg.logY);
  const labels = key ? levels(ds, key) : [yTitle];
  const index = new Map(labels.map((label, k) => [label, k]));
  const rows: number[][] = labels.map(() => []);
  let skipped = 0;
  for (let i = 0; i < mask.length; i++) {
    if (!mask[i]) continue;
    const v = cfg.y ? numberAt(ds, cfg.y, i) : null;
    if (v === null || (cfg.logY && v <= 0)) {
      skipped += 1;
      continue;
    }
    rows[key ? (index.get(categoryLabel(key, ds.values[key]?.[i])) ?? 0) : 0].push(i);
  }

  const shown = rows.reduce((n, r) => n + r.length, 0);
  const data = labels.flatMap((label, k) => {
    if (rows[k].length === 0) return [];
    const color = key ? categoryColor(key, label, labels) : CHART_COLORS.primary;
    return [
      {
        type: "box",
        name: label,
        x: rows[k].map(() => label),
        y: rows[k].map((i) => numberAt(ds, cfg.y as string, i)),
        text: rows[k].map((i) => hoverText(ds, i)),
        boxpoints: shown > ALL_POINTS_UP_TO ? "outliers" : "all",
        jitter: 0.4,
        pointpos: 0,
        line: { color, width: 1.5 },
        marker: { color, size: 4, opacity: 0.7, line: { color: edgeColor(dark), width: 0.5 } },
      },
    ];
  });

  return {
    data,
    layout: {
      ...baseLayout(cfg.id),
      showlegend: false,
      xaxis: axis(key ? axisTitle(ds, key) : "", {
        type: "category",
        categoryorder: "array",
        categoryarray: labels,
      }),
      yaxis: axis(yTitle, { type: cfg.logY ? "log" : "linear" }),
    },
    skipped,
    note: lackNote(skipped, axisTitle(ds, cfg.y)),
  };
}
