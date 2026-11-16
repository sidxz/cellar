import type { PanelPatch, PanelType } from "../store/workbench-store";
import type { Dataset, DatasetColumn } from "../types";
import { categoryColumns, column, valueColumns } from "./dataset";

/** The first readout value column that holds numbers, if any. */
export function numericValueColumn(ds: Dataset): DatasetColumn | undefined {
  return valueColumns(ds).find((c) => c.kind === "number");
}

/** The fields a newly added panel of ``type`` starts with: numeric fields take the first
 * numeric readout, category fields well type (else the first category column), and well
 * type colors (and stacks) the plot when the dataset has it. */
export function panelDefaults(ds: Dataset, type: PanelType): PanelPatch {
  const value = numericValueColumn(ds)?.key;
  const wellType = column(ds, "well_type")?.key;
  const category = wellType ?? categoryColumns(ds)[0]?.key;
  switch (type) {
    case "scatter":
      return {
        x: column(ds, "well_order")?.key ?? value,
        y: value,
        appearance: { colorBy: wellType, shapeBy: wellType },
      };
    case "histogram":
      return { x: value, appearance: { colorBy: wellType } };
    case "bar":
      return { agg: "count", category };
    case "box":
      return { y: value, category };
  }
}

/** The panels a fresh workbench opens with: a plate-order scatter of the first numeric
 * readout split by plate, or, when nothing numeric exists, a count bar so the chemist
 * still sees something. */
export function defaultPanels(ds: Dataset): Array<{ type: PanelType; defaults: PanelPatch }> {
  if (numericValueColumn(ds)) {
    const scatter = panelDefaults(ds, "scatter");
    return [
      {
        type: "scatter",
        defaults: { ...scatter, appearance: { splitBy: "plate", ...scatter.appearance } },
      },
    ];
  }
  const bar = panelDefaults(ds, "bar");
  return bar.category ? [{ type: "bar", defaults: bar }] : [];
}
