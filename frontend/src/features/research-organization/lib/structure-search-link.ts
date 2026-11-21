import type { StructureCriterion } from "../types";

/**
 * A link that opens /search running "find similar" or "find substructure" for one molecule:
 * `/search?molecule_id=<uuid>&mode=similar|substructure[&threshold=<0..1>]`.
 *
 * The molecule is named by id, never by structure, so a proprietary structure stays out of
 * URLs, browser history and server logs. The page fetches it under the viewer's own access.
 */
export interface StructureSearchLink {
  moleculeId: string;
  mode: "similar" | "substructure";
  threshold: number;
}

/** The search form's default for "Similar". */
const DEFAULT_THRESHOLD = 0.7;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** null when the URL names no molecule; "invalid" when it names one but the link is bad. */
export function parseStructureSearchLink(
  params: URLSearchParams,
): StructureSearchLink | "invalid" | null {
  const moleculeId = params.get("molecule_id");
  if (moleculeId === null) return null;
  const mode = params.get("mode");
  if (!UUID_RE.test(moleculeId) || (mode !== "similar" && mode !== "substructure")) {
    return "invalid";
  }
  const t = Number(params.get("threshold") ?? Number.NaN);
  const threshold = Number.isFinite(t) && t > 0 && t <= 1 ? t : DEFAULT_THRESHOLD;
  return { moleculeId, mode, threshold };
}

export function structureLinkCriterion(
  link: StructureSearchLink,
  smiles: string,
): StructureCriterion {
  return link.mode === "similar"
    ? {
        type: "structure",
        search_type: "similarity",
        kind: "similarity",
        mode: "similar",
        smiles,
        threshold: link.threshold,
      }
    : {
        type: "structure",
        search_type: "substructure",
        kind: "substructure",
        smiles_or_smarts: smiles,
        query_kind: "smiles",
      };
}
