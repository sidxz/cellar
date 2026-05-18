import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ScaffoldTreeNode } from "./scaffold-tree-node";
import { NO_SCAFFOLD_SENTINEL } from "../types/scaffold-tree";

// StructureThumbnail renders via RDKit.js WASM — stub it in tests.
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => (
    <div data-testid="structure-thumb" data-smiles={smiles} />
  ),
}));

const tree = {
  nodes: [
    { scaffold_smiles: "c1ccccc1", molecule_ids: ["m1"], molecule_count: 1, subtree_molecule_count: 2 },
    { scaffold_smiles: "c1ccc2ccccc2c1", molecule_ids: ["m2"], molecule_count: 1, subtree_molecule_count: 1 },
  ],
  edges: [{ parent_smiles: "c1ccccc1", child_smiles: "c1ccc2ccccc2c1" }],
  stats: { node_count: 2, elapsed_ms: 0, cache_hit: false },
};

describe("ScaffoldTreeNode", () => {
  it("renders subtree count when greater than own count", () => {
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        tree={tree}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    // Format: "1 · 2" (own · subtree)
    expect(screen.getByText(/1\s*·\s*2/)).toBeInTheDocument();
  });

  it("renders only own count when subtree equals own count", () => {
    const leaf = {
      ...tree,
      nodes: [
        { scaffold_smiles: "c1ccc2ccccc2c1", molecule_ids: ["m2"], molecule_count: 1, subtree_molecule_count: 1 },
      ],
      edges: [],
    };
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccc2ccccc2c1"
        tree={leaf}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    // Just "1"
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("emits onSelect with scaffold smiles on row click", () => {
    const handle = vi.fn();
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        tree={tree}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={handle}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    fireEvent.click(screen.getByTestId("scaffold-node-c1ccccc1"));
    expect(handle).toHaveBeenCalledWith("c1ccccc1");
  });

  it("renders 'no scaffold' label for the sentinel bucket", () => {
    const treeWithBucket = {
      ...tree,
      nodes: [
        ...tree.nodes,
        { scaffold_smiles: NO_SCAFFOLD_SENTINEL, molecule_ids: ["m3"], molecule_count: 1, subtree_molecule_count: 1 },
      ],
    };
    render(
      <ScaffoldTreeNode
        scaffoldSmiles={NO_SCAFFOLD_SENTINEL}
        tree={treeWithBucket}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    expect(screen.getByText(/no scaffold/i)).toBeInTheDocument();
  });

  it("toggles expand via caret click WITHOUT firing select", () => {
    const onToggle = vi.fn();
    const onSelect = vi.fn();
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        tree={tree}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={onToggle}
        onSelect={onSelect}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /expand/i }));
    expect(onToggle).toHaveBeenCalledWith("c1ccccc1");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("recursively renders children when expanded", () => {
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        tree={tree}
        depth={0}
        expanded={new Set(["c1ccccc1"])}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    // Child node should be rendered
    expect(screen.getByTestId("scaffold-node-c1ccc2ccccc2c1")).toBeInTheDocument();
  });
});
