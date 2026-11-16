import { formatMeasurementValue } from "@/shared/lib/format-number";
import type { z } from "zod";
import type { Dataset } from "../types";
import type { filterSchema } from "./config-schema";
import { categoryLabel, column, datasetMoleculeIds, numberAt } from "./dataset";

export type Filter = z.infer<typeof filterSchema>;
export type SubstructureFilter = Extract<Filter, { kind: "substructure" }>;

type Predicate = (i: number) => boolean;

function predicate(ds: Dataset, f: Filter): Predicate {
  if (f.kind === "range") {
    return (i) => {
      const v = numberAt(ds, f.key, i);
      if (v === null) return f.includeMissing;
      return (f.min === null || v >= f.min) && (f.max === null || v <= f.max);
    };
  }
  if (f.kind === "category") {
    const allowed = new Set(f.values);
    const col = ds.values[f.key] ?? [];
    return (i) => {
      const v = col[i];
      if (v === null || v === undefined) return f.includeMissing;
      return allowed.has(String(v));
    };
  }
  if (f.kind === "substructure") {
    const ids = new Set(f.moleculeIds);
    const molecules = ds.values.molecule_id ?? [];
    return (i) => ids.has(molecules[i] as string);
  }
  const ids = new Set(f.rowIds);
  return (i) => ids.has(ds.row_ids[i]);
}

/** 1 where a row passes every filter (AND); ``exceptId`` skips one filter, which is how
 * a filter card shows the distribution of the rows the *other* filters keep. */
export function computePassMask(ds: Dataset, filters: Filter[], exceptId?: string): Uint8Array {
  const n = ds.row_ids.length;
  const preds = filters.filter((f) => f.id !== exceptId).map((f) => predicate(ds, f));
  const mask = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    let ok = 1;
    for (const p of preds) {
      if (!p(i)) {
        ok = 0;
        break;
      }
    }
    mask[i] = ok;
  }
  return mask;
}

/** Bin edges over the whole column (ignoring filters) so bars never jump as filters change. */
export function fixedBins(ds: Dataset, key: string, count = 30): { edges: number[] } {
  let lo = Number.POSITIVE_INFINITY;
  let hi = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < ds.row_ids.length; i++) {
    const v = numberAt(ds, key, i);
    if (v === null) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo === Number.POSITIVE_INFINITY) return { edges: [0, 1] };
  if (lo === hi) {
    lo -= 0.5;
    hi += 0.5;
  }
  const step = (hi - lo) / count;
  return { edges: Array.from({ length: count + 1 }, (_, k) => (k === count ? hi : lo + k * step)) };
}

/** Counts per bin for rows passing ``mask``; the maximum falls in the last bin. */
export function binCounts(ds: Dataset, key: string, edges: number[], mask: Uint8Array): number[] {
  const bins = edges.length - 1;
  const counts = new Array<number>(bins).fill(0);
  const lo = edges[0];
  const hi = edges[bins];
  const step = (hi - lo) / bins;
  for (let i = 0; i < ds.row_ids.length; i++) {
    if (!mask[i]) continue;
    const v = numberAt(ds, key, i);
    if (v === null || v < lo || v > hi) continue;
    counts[Math.min(bins - 1, Math.floor((v - lo) / step))] += 1;
  }
  return counts;
}

const collator = new Intl.Collator(undefined, { numeric: true });

/** A category column's distinct values as filters hold them (``String(v)``), in display
 * order, and whether any row lacks a value. */
export function categoryValues(
  ds: Dataset,
  key: string,
): { values: string[]; hasMissing: boolean } {
  const seen = new Set<string>();
  let hasMissing = false;
  for (const v of ds.values[key] ?? []) {
    if (v === null || v === undefined) hasMissing = true;
    else seen.add(String(v));
  }
  const values = [...seen].sort((a, b) =>
    collator.compare(categoryLabel(key, a), categoryLabel(key, b)),
  );
  return { values, hasMissing };
}

let filterSeq = 0;

/** A filter on ``key`` that keeps every row: a range for numbers, a checklist for
 * categories; null for other kinds. */
export function newFilter(ds: Dataset, key: string): Filter | null {
  const kind = column(ds, key)?.kind;
  filterSeq += 1;
  const id = `filter-${Date.now().toString(36)}-${filterSeq}`;
  if (kind === "number") {
    return { id, kind: "range", key, min: null, max: null, includeMissing: true };
  }
  if (kind === "category" || kind === "user") {
    return {
      id,
      kind: "category",
      key,
      values: categoryValues(ds, key).values,
      includeMissing: true,
    };
  }
  return null;
}

/** A filter is active when, on its own, it leaves out at least one row. */
export const isFilterActive = (ds: Dataset, f: Filter) => computePassMask(ds, [f]).includes(0);

/** "Contains c1ccccc1", the query cut to 24 characters. */
export function substructureSummary(f: SubstructureFilter): string {
  const q = f.query.length > 24 ? `${f.query.slice(0, 23)}…` : f.query;
  return `Contains ${q}`;
}

/** How many of the dataset's compounds the substructure filter keeps, of how many. */
export function substructureCounts(
  ds: Dataset,
  f: SubstructureFilter,
): { matched: number; total: number } {
  const all = datasetMoleculeIds(ds);
  const kept = new Set(f.moleculeIds);
  return { matched: all.filter((id) => kept.has(id)).length, total: all.length };
}

/** What a filter keeps, without its field: "≥ 30", "30 … 80", "2 of 3", "12 rows",
 * "3 of 40 compounds". An untouched range shows the column's span. */
export function filterCondition(ds: Dataset, f: Filter): string {
  if (f.kind === "rows") return `${f.rowIds.length.toLocaleString()} rows`;
  if (f.kind === "substructure") {
    const { matched, total } = substructureCounts(ds, f);
    return `${matched.toLocaleString()} of ${total.toLocaleString()} compounds`;
  }
  if (f.kind === "category") {
    const { values, hasMissing } = categoryValues(ds, f.key);
    const kept = new Set(f.values);
    const total = values.length + Number(hasMissing);
    const n = values.filter((v) => kept.has(v)).length + Number(hasMissing && f.includeMissing);
    return n === total ? `all ${total}` : `${n} of ${total}`;
  }
  let text: string;
  if (f.min !== null && f.max !== null) text = `${f.min} … ${f.max}`;
  else if (f.min !== null) text = `≥ ${f.min}`;
  else if (f.max !== null) text = `≤ ${f.max}`;
  else if (!f.includeMissing) return "no missing";
  else {
    const { edges } = fixedBins(ds, f.key, 1);
    text = `${formatMeasurementValue(edges[0])} … ${formatMeasurementValue(edges[1])}`;
  }
  return f.includeMissing ? text : `${text}, no missing`;
}

/** The field and its condition: "% inhibition ≥ 30", "Well type: 2 of 3", "Contains c1ccccc1". */
export function filterSummary(ds: Dataset, f: Filter): string {
  if (f.kind === "substructure") return substructureSummary(f);
  const label = f.kind === "rows" ? "Selection" : (column(ds, f.key)?.label ?? f.key);
  const sep = f.kind === "range" ? " " : ": ";
  return `${label}${sep}${filterCondition(ds, f)}`;
}
