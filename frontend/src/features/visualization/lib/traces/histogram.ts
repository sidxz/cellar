import { CHART_COLORS } from "@/shared/lib/chart-colors";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { MAX_COLOR_GROUPS } from "../appearance";
import { column, numberAt } from "../dataset";
import { binCounts, fixedBins } from "../filters";
import {
  type Figure,
  axis,
  axisTitle,
  baseLayout,
  categoryColor,
  edgeColor,
  groupsOf,
  lackNote,
} from "./common";

const fmt = (v: number) => v.toLocaleString(undefined, { maximumSignificantDigits: 4 });

/** Counts of ``cfg.x`` over bins fixed on the whole column (so bars never shift as filters
 * change), stacked by ``appearance.colorBy`` when it is a category (capped like scatter colors). */
export function buildHistogramFigure(
  ds: Dataset,
  cfg: PanelConfig,
  mask: Uint8Array,
  dark = false,
): Figure {
  const key = cfg.x;
  const title = axisTitle(ds, key);
  const stackCol = cfg.appearance.colorBy ? column(ds, cfg.appearance.colorBy) : undefined;
  const stackKey = stackCol && stackCol.kind !== "number" ? stackCol.key : undefined;
  // Same groups (and so colors) as a scatter colored by the field.
  const stacks = groupsOf(ds, stackKey, MAX_COLOR_GROUPS);

  // One mask per stack: passing rows of that group that have a value.
  const masks = stacks.labels.map(() => new Uint8Array(mask.length));
  let skipped = 0;
  for (let i = 0; i < mask.length; i++) {
    if (!mask[i]) continue;
    if (!key || numberAt(ds, key, i) === null) skipped += 1;
    else masks[stacks.of(i)][i] = 1;
  }

  const { edges } = key ? fixedBins(ds, key, cfg.bins ?? 30) : { edges: [0, 1] };
  const bins = edges.slice(0, -1);
  const centers = bins.map((lo, k) => (lo + edges[k + 1]) / 2);
  const ranges = bins.map((lo, k) => `${fmt(lo)} to ${fmt(edges[k + 1])}`);
  const data = stacks.labels.map((label, g) => ({
    type: "bar",
    name: stackKey ? label : title,
    showlegend: Boolean(stackKey),
    x: centers,
    y: key ? binCounts(ds, key, edges, masks[g]) : [],
    width: edges[1] - edges[0],
    hovertext: ranges,
    hovertemplate: `%{hovertext}: %{y}<extra>${stackKey ? "%{fullData.name}" : ""}</extra>`,
    marker: {
      color: stackKey ? categoryColor(ds, stackKey, label, g) : CHART_COLORS.primary,
      line: { color: edgeColor(dark), width: 0.5 },
    },
  }));

  return {
    data,
    layout: {
      ...baseLayout(cfg.id),
      barmode: "stack",
      bargap: 0,
      xaxis: axis(title),
      yaxis: axis("Count"),
    },
    skipped,
    note: lackNote(skipped, title),
  };
}
