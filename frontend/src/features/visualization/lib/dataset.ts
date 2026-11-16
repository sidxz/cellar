import type { Dataset, DatasetColumn } from "../types";

const SIBLING = /:(q|outlier)$/;

export function column(ds: Dataset, key: string): DatasetColumn | undefined {
  return ds.columns.find((c) => c.key === key);
}

/** The value at row ``i`` as a finite number, else null (missing, NaN, text). */
export function numberAt(ds: Dataset, key: string, i: number): number | null {
  const v = ds.values[key]?.[i];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function numericColumns(ds: Dataset): DatasetColumn[] {
  return ds.columns.filter((c) => c.kind === "number" && !c.hidden);
}

/** Columns usable as categories (color, split, filters). User columns count once resolved. */
export function categoryColumns(ds: Dataset): DatasetColumn[] {
  return ds.columns.filter((c) => (c.kind === "category" || c.kind === "user") && !c.hidden);
}

/** Readout value columns, without their qualifier/outlier siblings. */
export function valueColumns(ds: Dataset): DatasetColumn[] {
  return ds.columns.filter((c) => c.key.startsWith("rd:") && !SIBLING.test(c.key));
}

/** A sample well, or a well-less summary row that names a compound. */
export function isSampleRow(ds: Dataset, i: number): boolean {
  const type = ds.values.well_type?.[i];
  if (type === "sample") return true;
  return (type === null || type === undefined) && ds.values.molecule_id?.[i] != null;
}

/** Molecule ids of the sample rows among ``rows``, deduped, in first-seen order. */
export function uniqueCompounds(ds: Dataset, rows: Iterable<number>): string[] {
  const seen = new Set<string>();
  for (const i of rows) {
    const id = ds.values.molecule_id?.[i];
    if (typeof id === "string" && isSampleRow(ds, i)) seen.add(id);
  }
  return [...seen];
}

/** Replace user-id values with display names and retype those columns as categories,
 * so no raw user id ever reaches a legend, filter or table cell. */
export function resolveUserColumns(ds: Dataset, nameOf: (userId: string) => string): Dataset {
  const userKeys = ds.columns.filter((c) => c.kind === "user").map((c) => c.key);
  if (userKeys.length === 0) return ds;
  const values = { ...ds.values };
  for (const key of userKeys) {
    values[key] = (ds.values[key] ?? []).map((v) => (typeof v === "string" ? nameOf(v) : v));
  }
  return {
    ...ds,
    columns: ds.columns.map((c) => (c.kind === "user" ? { ...c, kind: "category" } : c)),
    values,
  };
}
