import type { Appearance, PanelConfig, PanelPatch, PanelType } from "../store/workbench-store";
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

/** The patch that turns panel ``p`` into a ``type`` panel. The measured field carries over
 * (a scatter/bar/box Y is a histogram's X), as do a bar/box group and a scatter's X; fields
 * still missing come from panelDefaults (appearance only where unset), and data fields the
 * new type does not draw are cleared. */
export function retypePanel(ds: Dataset, p: PanelConfig, type: PanelType): PanelPatch {
  const d = panelDefaults(ds, type);
  const value = p.type === "histogram" ? p.x : p.y;
  const appearance = Object.fromEntries(
    Object.entries(d.appearance ?? {}).filter(
      ([k]) => p.appearance[k as keyof Appearance] === undefined,
    ),
  );
  const base: PanelPatch = {
    type,
    x: undefined,
    y: undefined,
    category: undefined,
    logX: undefined,
    logY: undefined,
    appearance,
  };
  switch (type) {
    case "scatter":
      return { ...base, x: p.type === "scatter" ? p.x : d.x, y: value ?? d.y, logY: p.logY };
    case "histogram":
      return { ...base, x: value ?? d.x };
    case "bar":
      return { ...base, category: p.category ?? d.category, agg: p.agg ?? d.agg, y: value };
    case "box":
      return { ...base, category: p.category ?? d.category, y: value ?? d.y, logY: p.logY };
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
