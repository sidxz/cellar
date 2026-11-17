import type { Dataset } from "../types";

/** Whether row ``i`` holds a value flagged as an outlier (its well is, on the Wells level). */
export function isOutlierRow(ds: Dataset, i: number): boolean {
  for (const key in ds.values) {
    if (key.endsWith(":outlier") && ds.values[key][i] != null) return true;
  }
  return false;
}

/** The wells of ``rows`` that can take or lose an outlier flag, by run: well rows
 * (``<run>:<well>``) of ``editable`` runs, split by whether they are flagged now. */
export function outlierTargets(
  ds: Dataset,
  rows: readonly number[],
  editable: ReadonlySet<string>,
): { flag: Map<string, string[]>; unflag: Map<string, string[]> } {
  const flag = new Map<string, string[]>();
  const unflag = new Map<string, string[]>();
  for (const i of rows) {
    const [run, well, ...rest] = ds.row_ids[i].split(":");
    if (rest.length > 0 || well === undefined || !editable.has(run)) continue;
    const into = isOutlierRow(ds, i) ? unflag : flag;
    const wells = into.get(run) ?? [];
    wells.push(well);
    into.set(run, wells);
  }
  return { flag, unflag };
}
