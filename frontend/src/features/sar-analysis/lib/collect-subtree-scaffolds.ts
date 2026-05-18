import type { ScaffoldTreeResult } from "../types/scaffold-tree";
import { buildChildIndex } from "./scaffold-tree-math";

/**
 * Collects the scaffold SMILES for the subtree rooted at `scaffoldSmiles`
 * (the node itself plus all descendants), Set-deduped.
 *
 * Mirror of `collectSubtreeMolIds` but returns scaffold SMILES instead of
 * molecule IDs. Used by V4 Path A to drive the `exact_match_in` server-side
 * scaffold-membership filter when a Hierarchy node selects its whole subtree.
 *
 * Returns [] when `scaffoldSmiles` is not present in the tree.
 */
export function collectSubtreeScaffolds(
  scaffoldSmiles: string,
  tree: ScaffoldTreeResult,
): string[] {
  const scaffoldSet = new Set(tree.nodes.map((n) => n.scaffold_smiles));
  if (!scaffoldSet.has(scaffoldSmiles)) return [];

  const children = buildChildIndex(tree);
  const visited = new Set<string>();
  const acc: string[] = [];
  const stack: string[] = [scaffoldSmiles];

  while (stack.length > 0) {
    const s = stack.pop()!;
    if (visited.has(s)) continue;
    visited.add(s);
    acc.push(s);
    for (const c of children.get(s) ?? []) stack.push(c);
  }

  return acc;
}
