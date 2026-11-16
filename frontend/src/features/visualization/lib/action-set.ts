import type { Dataset } from "../types";

export interface ActionSet {
  /** "selected" when the chemist picked rows, else "filtered" (every passing row). */
  mode: "selected" | "filtered";
  rows: number[];
  /** Selected rows the filters currently hide; they are not acted on. */
  hiddenSelected: number;
}

/** The rows Save/Export act on: selected rows that pass the filters, or every
 * passing row when nothing is selected. Filtering never silently widens a selection. */
export function actionSet(
  ds: Dataset,
  selection: ReadonlySet<string>,
  mask: Uint8Array,
): ActionSet {
  const rows: number[] = [];
  if (selection.size === 0) {
    for (let i = 0; i < ds.row_ids.length; i++) if (mask[i]) rows.push(i);
    return { mode: "filtered", rows, hiddenSelected: 0 };
  }
  let hidden = 0;
  for (let i = 0; i < ds.row_ids.length; i++) {
    if (!selection.has(ds.row_ids[i])) continue;
    if (mask[i]) rows.push(i);
    else hidden += 1;
  }
  return { mode: "selected", rows, hiddenSelected: hidden };
}
