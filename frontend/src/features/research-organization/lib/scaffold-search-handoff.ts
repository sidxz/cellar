import type { ScaffoldCriterion } from "../types";

export const STORAGE_KEY = "cellar:pending-search-query";

/**
 * Stash a single scaffold criterion in sessionStorage for the next /search
 * page mount to consume. Used by the scaffold-tree-node action that opens
 * /search pre-filtered for compounds matching a tree node's scaffold.
 *
 * Empty-string input → acyclic_only mode (the V2 "no scaffold" bucket).
 */
export function stashScaffoldSearch(scaffoldSmiles: string): void {
  if (typeof window === "undefined") return;
  const criterion: ScaffoldCriterion =
    scaffoldSmiles === ""
      ? { type: "scaffold", mode: "acyclic_only" }
      : { type: "scaffold", mode: "exact_match", scaffold_smiles: scaffoldSmiles };
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(criterion));
}

/**
 * Read and clear the stashed scaffold criterion. Returns null if nothing
 * was stashed or the payload is malformed. Always clears on read so the
 * pending query doesn't leak into subsequent /search visits.
 */
export function consumeScaffoldSearch(): ScaffoldCriterion | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (raw === null) return null;
  window.sessionStorage.removeItem(STORAGE_KEY);
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (
      parsed !== null &&
      typeof parsed === "object" &&
      "type" in parsed &&
      "mode" in parsed &&
      (parsed as Record<string, unknown>).type === "scaffold" &&
      ((parsed as Record<string, unknown>).mode === "exact_match" ||
        (parsed as Record<string, unknown>).mode === "acyclic_only")
    ) {
      // Guard: exact_match requires a non-empty scaffold_smiles. Without it the
      // BE returns a 422 and the search page silently shows zero results.
      if ((parsed as Record<string, unknown>).mode === "exact_match") {
        const smiles = (parsed as Record<string, unknown>).scaffold_smiles;
        if (typeof smiles !== "string" || smiles.length === 0) {
          return null;
        }
      }
      return parsed as ScaffoldCriterion;
    }
    return null;
  } catch {
    return null;
  }
}
