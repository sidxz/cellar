import type { OverlayConfig, PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { column } from "../dataset";

/** An overlay a plot can draw: a config key, or one of the two drift modes. */
export type OverlayKind = keyof OverlayConfig | "driftBand" | "trend";

const LOG = "Not available on a log axis";

/** Which overlays ``p`` can draw over ``ds``: a kind is absent when the columns it needs do
 * not exist (the control is hidden), ``true`` when it can be drawn, or the reason it cannot
 * yet (the control shows disabled with it). */
export function overlayOptions(
  ds: Dataset,
  p: PanelConfig,
): Partial<Record<OverlayKind, true | string>> {
  const out: Partial<Record<OverlayKind, true | string>> = {};
  const scatter = p.type === "scatter";
  const xCol = p.x ? column(ds, p.x) : undefined;
  const yCol = p.y ? column(ds, p.y) : undefined;
  /** ``true`` unless an axis the overlay places marks on in data units is logarithmic. */
  const linear = (...logs: (boolean | undefined)[]) => (logs.some(Boolean) ? LOG : true);

  if (scatter && column(ds, "well_type")) {
    out.bands = linear(p.logY);
    out.driftBand =
      p.x === "well_order" || p.x === "well_column"
        ? linear(p.logX, p.logY)
        : "Drift bands need X = Well order or Column";
    out.trend = xCol?.kind === "number" ? linear(p.logX, p.logY) : "Trend lines need a numeric X";
    if (column(ds, "plate_id")) {
      out.zPrime = p.appearance.splitBy === "plate" || "Split by Plate to show stored Z′";
    }
  }
  if ((scatter || p.type === "box") && yCol?.kind === "number") out.refLine = linear(p.logY);
  if (scatter && ds.level === "runs") {
    out.limits = p.x === "run_date" ? linear(p.logY) : "Set X to Run date";
  }
  const isP = (c = yCol) => c?.kind === "number" && c.provenance.aggregation === "p";
  if (scatter && column(ds, "logp") && ds.columns.some((c) => isP(c))) {
    out.lipe = !isP()
      ? "Set Y to a p-potency"
      : p.x !== "logp"
        ? "Set X to logP"
        : linear(p.logX, p.logY);
  }
  return out;
}
