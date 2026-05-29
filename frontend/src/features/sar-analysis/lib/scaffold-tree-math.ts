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

/**
 * Computes, in a single pass, the subtree molecule-id set for EVERY node —
 * the node's own mol ids plus those of all descendants, Set-deduped.
 *
 * This is the batch equivalent of calling `collectSubtreeMolIds` once per
 * node, but it builds the node lookup + child index ONCE and memoizes each
 * node's result. Calling `collectSubtreeMolIds` in a per-node loop (as the
 * scaffold-tree color rollup used to) rebuilds both indexes on every call —
 * O(N²) map allocations that freeze the tab on large collections (a 5K-mol
 * collection yields ~2.6K scaffold nodes). Use this whenever you need subtree
 * mol ids for more than one node.
 *
 * Memoization is correct for DAGs (a node's subtree is independent of which
 * parent reaches it). The ancestor guard only prevents infinite recursion on
 * a malformed cyclic edge set — real scaffold networks are acyclic.
 */
export function buildSubtreeMolIdMap(
  tree: ScaffoldTreeResult,
): Map<string, string[]> {
  const byScaffold = new Map<string, ScaffoldTreeNode>(
    tree.nodes.map((n) => [n.scaffold_smiles, n]),
  );
  const children = buildChildIndex(tree);
  const memo = new Map<string, string[]>();

  const compute = (smiles: string, ancestors: Set<string>): string[] => {
    const cached = memo.get(smiles);
    if (cached) return cached;

    const ids = new Set<string>(byScaffold.get(smiles)?.molecule_ids ?? []);
    for (const child of children.get(smiles) ?? []) {
      if (ancestors.has(child)) continue; // cycle guard
      ancestors.add(child);
      for (const id of compute(child, ancestors)) ids.add(id);
      ancestors.delete(child);
    }

    const arr = [...ids];
    memo.set(smiles, arr);
    return arr;
  };

  for (const node of tree.nodes) {
    if (!memo.has(node.scaffold_smiles)) {
      compute(node.scaffold_smiles, new Set([node.scaffold_smiles]));
    }
  }
  return memo;
}

/** Returns nodes that have no incoming edge (i.e. true root nodes). */
export function rootNodes(tree: ScaffoldTreeResult): ScaffoldTreeNode[] {
  const hasParent = new Set<string>(tree.edges.map((e) => e.child_smiles));
  return tree.nodes.filter((n) => !hasParent.has(n.scaffold_smiles));
}
