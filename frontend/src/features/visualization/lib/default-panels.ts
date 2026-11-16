import type { PanelPatch, PanelType } from "../store/workbench-store";
import type { Dataset, DatasetColumn } from "../types";
import { categoryColumns, column, valueColumns } from "./dataset";

/** The first readout value column that holds numbers, if any. */
export function numericValueColumn(ds: Dataset): DatasetColumn | undefined {
  return valueColumns(ds).find((c) => c.kind === "number");
}

/** The panels a fresh workbench opens with: a plate-order scatter of the first numeric
 * readout, or, when nothing numeric exists, a count bar so the chemist still sees something. */
export function defaultPanels(ds: Dataset): Array<{ type: PanelType; defaults: PanelPatch }> {
  const y = numericValueColumn(ds);
  if (y) {
    return [
      {
        type: "scatter",
        defaults: {
          x: "well_order",
          y: y.key,
          appearance: { splitBy: "plate", colorBy: "well_type", shapeBy: "well_type" },
        },
      },
    ];
  }
  const category = column(ds, "well_type")?.key ?? categoryColumns(ds)[0]?.key;
  return category ? [{ type: "bar", defaults: { agg: "count", category } }] : [];
}
