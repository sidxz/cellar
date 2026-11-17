import type { Dataset } from "../types";
import { column, numberAt } from "./dataset";
import type { Filter } from "./filters";

/** A Compounds dataset joining more than one protocol. */
export const isCrossProtocol = (ds: Dataset) => (ds.protocols?.length ?? 0) > 1;

export const protocolName = (ds: Dataset, id: string) =>
  ds.protocols?.find((p) => p.protocol_id === id)?.name ?? "Unknown protocol";

/** The column saying whether a compound was tested in compared protocol ``pid``. */
export const testedKey = (pid: string) => `tested:${pid}`;

/** The two p columns of a selectivity (Δ) column ``sel:<a>|<b>``, else null. */
export function selectivityKeys(key: string): [string, string] | null {
  if (!key.startsWith("sel:")) return null;
  const bar = key.indexOf("|");
  return bar < 0 ? null : [key.slice(4, bar), key.slice(bar + 1)];
}

/** Whether ``key`` is a number a loaded protocol measured, or a Δ between two, in a
 * cross-protocol dataset: a value whose absence has a reason ("Not tested in …"). */
export function isComparedValue(ds: Dataset, key: string | undefined): boolean {
  const c = key && isCrossProtocol(ds) ? column(ds, key) : undefined;
  return c?.kind === "number" && (!!c.provenance.readout_definition_id || !!selectivityKeys(c.key));
}

/** "Not tested in {protocol}" when row ``i`` was not tested in a protocol column ``key``
 * reads (for a Δ: either of its inputs), else null. */
function notTested(ds: Dataset, key: string, i: number): string | null {
  for (const k of selectivityKeys(key) ?? [key]) {
    const pid = column(ds, k)?.provenance.protocol_id;
    if (pid && ds.values[testedKey(pid)]?.[i] === "Not tested") {
      return `Not tested in ${protocolName(ds, pid)}`;
    }
  }
  return null;
}

/** Why row ``i`` has no value in ``key``; null when it has one. */
export function missingReason(ds: Dataset, key: string, i: number): string | null {
  if (ds.values[key]?.[i] != null) return null;
  return notTested(ds, key, i) ?? "No value";
}

/** Passing rows with a number on both axes, and the others grouped by why they lack one
 * ("Not tested in …" before "No value" when a row lacks both), in first-seen order. */
export function pairCounts(
  ds: Dataset,
  xKey: string,
  yKey: string,
  mask: Uint8Array,
): { pairs: number; missing: Array<{ reason: string; n: number }> } {
  let pairs = 0;
  const missing = new Map<string, number>();
  for (let i = 0; i < ds.row_count; i++) {
    if (!mask[i]) continue;
    if (numberAt(ds, xKey, i) !== null && numberAt(ds, yKey, i) !== null) {
      pairs++;
      continue;
    }
    const reason = notTested(ds, xKey, i) ?? notTested(ds, yKey, i) ?? "No value";
    missing.set(reason, (missing.get(reason) ?? 0) + 1);
  }
  return { pairs, missing: [...missing].map(([reason, n]) => ({ reason, n })) };
}

/** Ids of the compared protocols (every one but the first) that have a tested column. */
const comparedIds = (ds: Dataset) =>
  (ds.protocols ?? [])
    .slice(1)
    .map((p) => p.protocol_id)
    .filter((pid) => column(ds, testedKey(pid)));

/** "Only compounds tested in all": one filter per compared protocol keeping "Tested". */
export function testedInAllFilters(ds: Dataset): Extract<Filter, { kind: "category" }>[] {
  return comparedIds(ds).map((pid) => ({
    id: `tested-all:${pid}`,
    kind: "category",
    key: testedKey(pid),
    values: ["Tested"],
    includeMissing: false,
  }));
}

/** Whether ``filters`` keep only compounds tested in every compared protocol. */
export function isTestedInAll(filters: Filter[], ds: Dataset): boolean {
  const ids = comparedIds(ds);
  return (
    ids.length > 0 &&
    ids.every((pid) =>
      filters.some(
        (f) =>
          f.kind === "category" &&
          f.key === testedKey(pid) &&
          !f.includeMissing &&
          f.values.length === 1 &&
          f.values[0] === "Tested",
      ),
    )
  );
}

/** Compounds tested in compared protocol ``pid``. */
export const testedCount = (ds: Dataset, pid: string) =>
  (ds.values[testedKey(pid)] ?? []).filter((v) => v === "Tested").length;
