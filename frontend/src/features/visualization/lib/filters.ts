import type { Dataset } from "../types";
import { numberAt } from "./dataset";

export type Filter =
  | {
      id: string;
      kind: "range";
      key: string;
      min: number | null;
      max: number | null;
      includeMissing: boolean;
    }
  | { id: string; kind: "category"; key: string; values: string[]; includeMissing: boolean }
  | { id: string; kind: "rows"; rowIds: string[] };

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
