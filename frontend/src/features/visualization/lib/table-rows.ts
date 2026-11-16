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
