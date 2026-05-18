import type { ScaffoldTreeNode, ScaffoldTreeResult } from "../types/scaffold-tree";

/** Returns a Map from parent scaffold SMILES → list of child scaffold SMILES. */
export function buildChildIndex(tree: ScaffoldTreeResult): Map<string, string[]> {
  const idx = new Map<string, string[]>();
  for (const e of tree.edges) {
    const arr = idx.get(e.parent_smiles) ?? [];
    arr.push(e.child_smiles);
    idx.set(e.parent_smiles, arr);
  }
  return idx;
}

/**
 * Collects all molecule IDs in the subtree rooted at `scaffoldSmiles`
 * (the node itself plus all descendants).
 *
 * Uses an iterative DFS with a visited set so diamond DAGs are handled
 * without double-counting molecule IDs from a shared descendant.
 *
 * Returns [] when `scaffoldSmiles` is not present in the tree.
 */
export function collectSubtreeMolIds(
  scaffoldSmiles: string,
  tree: ScaffoldTreeResult,
): string[] {
  const byScaffold = new Map<string, ScaffoldTreeNode>(
    tree.nodes.map((n) => [n.scaffold_smiles, n]),
  );
  const children = buildChildIndex(tree);
  const visited = new Set<string>();
  const acc: string[] = [];
  const stack: string[] = [scaffoldSmiles];

  while (stack.length > 0) {
    const s = stack.pop()!;
    if (visited.has(s)) continue;
    visited.add(s);
    const node = byScaffold.get(s);
    if (node) acc.push(...node.molecule_ids);
    for (const c of children.get(s) ?? []) stack.push(c);
  }

  return acc;
}

/** Returns nodes that have no incoming edge (i.e. true root nodes). */
export function rootNodes(tree: ScaffoldTreeResult): ScaffoldTreeNode[] {
  const hasParent = new Set<string>(tree.edges.map((e) => e.child_smiles));
  return tree.nodes.filter((n) => !hasParent.has(n.scaffold_smiles));
}
