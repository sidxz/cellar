import type { Level } from "../types";

/** What one row is at each level, and how counts name rows. */
export const LEVELS: Record<Level, { label: string; caption: string; one: string; many: string }> =
  {
    wells: { label: "Wells", caption: "Each row: one well", one: "well", many: "wells" },
    runs: { label: "Runs", caption: "Each row: compound × batch × run", one: "row", many: "rows" },
    batches: {
      label: "Batches",
      caption: "Each row: compound × batch",
      one: "batch",
      many: "batches",
    },
    compounds: {
      label: "Compounds",
      caption: "Each row: compound",
      one: "compound",
      many: "compounds",
    },
  };

/** Finest grain first. */
export const LEVEL_ORDER: Level[] = ["wells", "runs", "batches", "compounds"];

const COUNTED_STATUSES = new Set(["completed", "approved"]);

/** Whether a run in ``status`` contributes rows at ``level``: Batches and Compounds pool
 * completed or approved runs only, as the protocol's Activity does; Wells and Runs show
 * every run. */
export function countsAtLevel(level: Level, status: string): boolean {
  return (level !== "batches" && level !== "compounds") || COUNTED_STATUSES.has(status);
}
