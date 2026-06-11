import { NO_SCAFFOLD_SENTINEL, type ScaffoldTreeResult } from "../types/scaffold-tree";
import { buildSubtreeMolIdMap } from "./scaffold-tree-math";

/**
 * Candidate R-group cores derived from the scaffold network, ranked by
 * COVERAGE rather than direct Bemis-Murcko membership.
 *
 * For an R-group core the question is "how many molecules CONTAIN this
 * scaffold", not "how many have it as their exact Murcko scaffold". The former
 * is the size of the node's subtree mol-id union (the node plus every more-
 * elaborate descendant) — computed exactly (Set-deduped, DAG-safe) by
 * {@link buildSubtreeMolIdMap}. This surfaces generic frameworks with their real
 * coverage instead of burying them at molecule_count 0, and it lets us drop the
 * unusable long tail of singleton/0-coverage cores.
 */

export const DEFAULT_COVERAGE_FLOOR = 3;

export type CoreCandidate = {
  scaffoldSmiles: string;
  /** Distinct molecules whose scaffold is this node OR a descendant (contain it). */
  coverage: number;
  /** Direct Bemis-Murcko membership (molecule_count) — kept for display/diagnostics. */
  directCount: number;
};

/**
 * A cheap, synchronous specificity proxy: the heavy-atom count estimated from
 * the scaffold SMILES (a larger ring system is more specific). Used only as a
 * ranking tie-break, so an approximation is fine — no RDKit needed.
 */
function heavyAtomEstimate(smiles: string): number {
  const bare = smiles.replace(/\[\*(?::\d+)?\]/g, "");
  // two-letter halogens, any bracketed atom, and single organic-subset atoms
  // (uppercase + aromatic lowercase). Bonds, digits and parens are ignored.
  const atoms = bare.match(/Cl|Br|\[[^\]]+\]|[BCNOPSFIbcnops]/g);
  return atoms ? atoms.length : 0;
}

/**
 * Build coverage-ranked core candidates from a scaffold tree.
 *
 * Excludes the acyclic NO_SCAFFOLD bucket and any core below `floor` coverage.
 * Sorted coverage DESC, then specificity (heavy-atom) DESC, then SMILES ASC for
 * a stable order. `total` is the full loaded set size (incl. acyclic molecules)
 * — the honest denominator for a "covers N of M" badge.
 */
export function buildCoreCandidates(
  tree: ScaffoldTreeResult,
  opts?: { floor?: number },
): { candidates: CoreCandidate[]; total: number } {
  const floor = opts?.floor ?? DEFAULT_COVERAGE_FLOOR;
  const total = new Set(tree.nodes.flatMap((n) => n.molecule_ids)).size;

  const subtreeMolIds = buildSubtreeMolIdMap(tree);

  const candidates = tree.nodes
    .filter((n) => n.scaffold_smiles !== NO_SCAFFOLD_SENTINEL)
    .map((n) => ({
      scaffoldSmiles: n.scaffold_smiles,
      coverage: subtreeMolIds.get(n.scaffold_smiles)?.length ?? n.molecule_ids.length,
      directCount: n.molecule_count,
    }))
    .filter((c) => c.coverage >= floor)
    .sort(
      (a, b) =>
        b.coverage - a.coverage ||
        heavyAtomEstimate(b.scaffoldSmiles) - heavyAtomEstimate(a.scaffoldSmiles) ||
        a.scaffoldSmiles.localeCompare(b.scaffoldSmiles),
    );

  return { candidates, total };
}

/**
 * The default core to pre-select: the most SPECIFIC scaffold whose coverage is
 * within a small slack of the MAXIMUM coverage. Among the broadest-covering
 * scaffolds this prefers the richest (most elaborate) one — the chemist's
 * natural starting core — while the slack tolerates a few outliers without
 * collapsing back to a too-generic framework.
 *
 *   - True analog series → the shared scaffold (e.g. quinazoline), not plain
 *     benzene and not a lone decorated leaf.
 *   - Mixed/sub-series set → the true common framework (sub-series cores stay
 *     available as chips).
 *   - No candidate above the floor → null (caller shows draw-a-core guidance).
 *
 * Candidates are assumed already coverage-DESC sorted (as built above).
 */
export function pickDefaultCore(candidates: CoreCandidate[]): string | null {
  if (candidates.length === 0) return null;

  const maxCoverage = candidates[0].coverage;
  const slack = Math.max(1, Math.ceil(0.1 * maxCoverage));
  const keep = Math.max(1, maxCoverage - slack);

  const eligible = candidates.filter((c) => c.coverage >= keep);
  // Most specific first; tie-break toward broader coverage, then stable SMILES.
  eligible.sort(
    (a, b) =>
      heavyAtomEstimate(b.scaffoldSmiles) - heavyAtomEstimate(a.scaffoldSmiles) ||
      b.coverage - a.coverage ||
      a.scaffoldSmiles.localeCompare(b.scaffoldSmiles),
  );
  return eligible[0].scaffoldSmiles;
}
