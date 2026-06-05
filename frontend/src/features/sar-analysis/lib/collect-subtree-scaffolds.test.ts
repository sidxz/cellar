import { describe, expect, it } from "vitest";
import type { ScaffoldTreeResult } from "../types/scaffold-tree";
import { collectSubtreeScaffolds } from "./collect-subtree-scaffolds";

const node = (scaffold_smiles: string, molecule_ids: string[] = []) => ({
  scaffold_smiles,
  molecule_ids,
  molecule_count: molecule_ids.length,
  subtree_molecule_count: molecule_ids.length,
});

const stats = { node_count: 0, elapsed_ms: 0, cache_hit: false };

describe("collectSubtreeScaffolds", () => {
  it("returns [node.scaffold_smiles] for a leaf node", () => {
    const tree: ScaffoldTreeResult = {
      nodes: [node("c1ccccc1")],
      edges: [],
      stats,
    };
    expect(collectSubtreeScaffolds("c1ccccc1", tree)).toEqual(["c1ccccc1"]);
  });

  it("returns the inner node plus all descendants in a Schuffenhauer DAG", () => {
    // benzene → naphthalene → anthracene
    const tree: ScaffoldTreeResult = {
      nodes: [node("c1ccccc1"), node("c1ccc2ccccc2c1"), node("c1ccc2cc3ccccc3cc2c1")],
      edges: [
        { parent_smiles: "c1ccccc1", child_smiles: "c1ccc2ccccc2c1" },
        { parent_smiles: "c1ccc2ccccc2c1", child_smiles: "c1ccc2cc3ccccc3cc2c1" },
      ],
      stats,
    };
    const out = collectSubtreeScaffolds("c1ccc2ccccc2c1", tree);
    expect(new Set(out)).toEqual(new Set(["c1ccc2ccccc2c1", "c1ccc2cc3ccccc3cc2c1"]));
  });

  it("de-dupes when DAG has diamond shape (two parents → same descendant)", () => {
    // A → B, A → C, B → D, C → D  (D reachable via two paths)
    const tree: ScaffoldTreeResult = {
      nodes: [node("A"), node("B"), node("C"), node("D")],
      edges: [
        { parent_smiles: "A", child_smiles: "B" },
        { parent_smiles: "A", child_smiles: "C" },
        { parent_smiles: "B", child_smiles: "D" },
        { parent_smiles: "C", child_smiles: "D" },
      ],
      stats,
    };
    const out = collectSubtreeScaffolds("A", tree);
    expect(out.length).toBe(4); // A, B, C, D — exactly once each
    expect(new Set(out)).toEqual(new Set(["A", "B", "C", "D"]));
  });

  it("returns [] when scaffold_smiles is not in the tree", () => {
    const tree: ScaffoldTreeResult = {
      nodes: [node("c1ccccc1")],
      edges: [],
      stats,
    };
    expect(collectSubtreeScaffolds("c1ccncc1", tree)).toEqual([]);
  });
});
