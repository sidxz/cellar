import type { Dataset } from "../types";

/** Table row order: selected passing rows pinned on top, the other passing rows below
 * (the grid sorts these), and the failing rows after them only when ``showAll``. */
export function orderTableRows(
  ds: Dataset,
  mask: Uint8Array,
  selection: ReadonlySet<string>,
  showAll: boolean,
): { pinned: number[]; rest: number[] } {
  const pinned: number[] = [];
  const rest: number[] = [];
  const failing: number[] = [];
  for (let i = 0; i < ds.row_ids.length; i++) {
    if (!mask[i]) failing.push(i);
    else if (selection.has(ds.row_ids[i])) pinned.push(i);
    else rest.push(i);
  }
  return { pinned, rest: showAll ? rest.concat(failing) : rest };
}

/** Selected rows the table shows at once; past it a summary row offers Filter to selection,
 * so a selection of thousands never mounts thousands of pinned rows. */
export const MAX_PINNED = 50;

/** What the pinned "Selected" block shows of ``pinned``: at most MAX_PINNED rows (none while
 * collapsed) and how many more are selected. */
export function pinnedBlock(
  pinned: number[],
  collapsed: boolean,
): { shown: number[]; more: number } {
  const shown = collapsed ? [] : pinned.slice(0, MAX_PINNED);
  return { shown, more: collapsed ? 0 : pinned.length - shown.length };
}

/** A grid comparator ranking numbers with missing values last whichever way the column is
 * sorted (the grid negates the answer when sorting descending). */
export function nullsLast(
  a: number | null,
  b: number | null,
  _nodeA: unknown,
  _nodeB: unknown,
  descending: boolean,
): number {
  if (a === null || b === null) {
    if (a === b) return 0;
    return (a === null ? 1 : -1) * (descending ? -1 : 1);
  }
  return a - b;
}
