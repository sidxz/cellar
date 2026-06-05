import { describe, expect, it } from "vitest";
import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeEdge,
  type ScaffoldTreeJob,
  type ScaffoldTreeNode,
  type ScaffoldTreeResult,
} from "./scaffold-tree";

describe("scaffold-tree types", () => {
  it("exposes NO_SCAFFOLD_SENTINEL", () => {
    expect(NO_SCAFFOLD_SENTINEL).toBe("__no_scaffold__");
  });

  it("allows valid node construction", () => {
    const node: ScaffoldTreeNode = {
      scaffold_smiles: "c1ccccc1",
      molecule_ids: ["mol-1"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    };
    expect(node.scaffold_smiles).toBe("c1ccccc1");
  });

  it("allows result with empty nodes", () => {
    const r: ScaffoldTreeResult = {
      nodes: [],
      edges: [],
      stats: { node_count: 0, elapsed_ms: 0, cache_hit: false, truncated: false },
    };
    expect(r.nodes).toHaveLength(0);
  });

  it("models job lifecycle status union", () => {
    const job: ScaffoldTreeJob = {
      id: "uuid",
      status: "pending",
      ids_hash: "hash",
      requested_at: "2026-05-17T00:00:00Z",
    };
    expect(job.status).toBe("pending");
  });

  it("allows edge with parent + child", () => {
    const e: ScaffoldTreeEdge = { parent_smiles: "c1ccccc1", child_smiles: "c1ccc2ccccc2c1" };
    expect(e.parent_smiles).toBe("c1ccccc1");
  });
});
