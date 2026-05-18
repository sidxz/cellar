import { describe, it, expect } from "vitest";
import {
  buildChildIndex,
  collectSubtreeMolIds,
  rootNodes,
} from "./scaffold-tree-math";
import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeResult,
} from "../types/scaffold-tree";

const tree: ScaffoldTreeResult = {
  nodes: [
    { scaffold_smiles: "c1ccccc1",          molecule_ids: ["m1"],       molecule_count: 1, subtree_molecule_count: 3 },
    { scaffold_smiles: "c1ccc2ccccc2c1",    molecule_ids: ["m2"],       molecule_count: 1, subtree_molecule_count: 2 },
    { scaffold_smiles: "c1ccc2cc(N)ccc2c1", molecule_ids: ["m3"],       molecule_count: 1, subtree_molecule_count: 1 },
    { scaffold_smiles: NO_SCAFFOLD_SENTINEL, molecule_ids: ["m4","m5"], molecule_count: 2, subtree_molecule_count: 2 },
  ],
  edges: [
    { parent_smiles: "c1ccccc1",       child_smiles: "c1ccc2ccccc2c1" },
    { parent_smiles: "c1ccc2ccccc2c1", child_smiles: "c1ccc2cc(N)ccc2c1" },
  ],
  stats: { node_count: 4, elapsed_ms: 0, cache_hit: false },
};

describe("scaffold-tree-math", () => {
  it("buildChildIndex returns parent->children map", () => {
    const idx = buildChildIndex(tree);
    expect(idx.get("c1ccccc1")).toEqual(["c1ccc2ccccc2c1"]);
    expect(idx.get("c1ccc2ccccc2c1")).toEqual(["c1ccc2cc(N)ccc2c1"]);
    expect(idx.get("c1ccc2cc(N)ccc2c1")).toBeUndefined();
  });

  it("collectSubtreeMolIds gathers self + descendants", () => {
    const ids = collectSubtreeMolIds("c1ccccc1", tree);
    expect(new Set(ids)).toEqual(new Set(["m1", "m2", "m3"]));
  });

  it("collectSubtreeMolIds for leaf returns only own", () => {
    const ids = collectSubtreeMolIds("c1ccc2cc(N)ccc2c1", tree);
    expect(ids).toEqual(["m3"]);
  });

  it("collectSubtreeMolIds for no-scaffold bucket returns own", () => {
    const ids = collectSubtreeMolIds(NO_SCAFFOLD_SENTINEL, tree);
    expect(new Set(ids)).toEqual(new Set(["m4", "m5"]));
  });

  it("rootNodes returns nodes with no incoming edge", () => {
    const roots = rootNodes(tree).map((n) => n.scaffold_smiles);
    expect(new Set(roots)).toEqual(new Set(["c1ccccc1", NO_SCAFFOLD_SENTINEL]));
  });

  it("collectSubtreeMolIds handles unknown smiles gracefully", () => {
    expect(collectSubtreeMolIds("does-not-exist", tree)).toEqual([]);
  });

  it("collectSubtreeMolIds avoids double-counting in a diamond DAG", () => {
    const diamond: ScaffoldTreeResult = {
      nodes: [
        { scaffold_smiles: "A", molecule_ids: [], molecule_count: 0, subtree_molecule_count: 3 },
        { scaffold_smiles: "B", molecule_ids: ["m1"], molecule_count: 1, subtree_molecule_count: 2 },
        { scaffold_smiles: "C", molecule_ids: ["m2"], molecule_count: 1, subtree_molecule_count: 2 },
        { scaffold_smiles: "D", molecule_ids: ["m3"], molecule_count: 1, subtree_molecule_count: 1 },
      ],
      edges: [
        { parent_smiles: "A", child_smiles: "B" },
        { parent_smiles: "A", child_smiles: "C" },
        { parent_smiles: "B", child_smiles: "D" },
        { parent_smiles: "C", child_smiles: "D" },
      ],
      stats: { node_count: 4, elapsed_ms: 0, cache_hit: false },
    };
    const ids = collectSubtreeMolIds("A", diamond);
    // A->B->D, A->C->D. D visited twice via two paths; m3 appears once.
    const sorted = [...ids].sort();
    expect(sorted).toEqual(["m1", "m2", "m3"]);
  });
});
