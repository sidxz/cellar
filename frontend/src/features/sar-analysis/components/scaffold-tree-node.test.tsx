import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ScaffoldTreeNode } from "./scaffold-tree-node";
import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeNode as ScaffoldTreeNodeData,
} from "../types/scaffold-tree";
import {
  consumeScaffoldSearch,
  STORAGE_KEY,
} from "@/features/research-organization/lib/scaffold-search-handoff";

// StructureThumbnail renders via RDKit.js WASM — stub it in tests.
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => (
    <div data-testid="structure-thumb" data-smiles={smiles} />
  ),
}));

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const tree = {
  nodes: [
    { scaffold_smiles: "c1ccccc1", molecule_ids: ["m1"], molecule_count: 1, subtree_molecule_count: 2 },
    { scaffold_smiles: "c1ccc2ccccc2c1", molecule_ids: ["m2"], molecule_count: 1, subtree_molecule_count: 1 },
  ],
  edges: [{ parent_smiles: "c1ccccc1", child_smiles: "c1ccc2ccccc2c1" }],
  stats: { node_count: 2, elapsed_ms: 0, cache_hit: false },
};

// The component now takes a prebuilt smiles->node map (built once at the tree
// root) rather than the whole tree. Mirror that here.
const nodeMap = (t: { nodes: ScaffoldTreeNodeData[] }) =>
  new Map<string, ScaffoldTreeNodeData>(
    t.nodes.map((n) => [n.scaffold_smiles, n]),
  );

describe("ScaffoldTreeNode", () => {
  it("renders subtree count when greater than own count", () => {
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        nodesBySmiles={nodeMap(tree)}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        childIndex={new Map()}
        colorBins={new Map()}
      />,
    );
    // Format: "1 mol · 2 sub" — own count then descendant count
    expect(screen.getByText(/1/)).toBeInTheDocument();
    expect(screen.getByText(/2 sub/)).toBeInTheDocument();
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
        nodesBySmiles={nodeMap(leaf)}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        childIndex={new Map()}
        colorBins={new Map()}
      />,
    );
    // Just "1" + "mol" (singular), no "sub"
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText(/^mol$/i)).toBeInTheDocument();
    expect(screen.queryByText(/sub/i)).not.toBeInTheDocument();
  });

  it("emits onSelect with scaffold smiles on row click", () => {
    const handle = vi.fn();
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        nodesBySmiles={nodeMap(tree)}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={handle}
        childIndex={new Map()}
        colorBins={new Map()}
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
        nodesBySmiles={nodeMap(treeWithBucket)}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        childIndex={new Map()}
        colorBins={new Map()}
      />,
    );
    expect(screen.getByText(/no scaffold/i)).toBeInTheDocument();
  });

  it("toggles expand via caret click WITHOUT firing select", () => {
    const onToggle = vi.fn();
    const onSelect = vi.fn();
    const childIndex = new Map<string, string[]>([
      ["c1ccccc1", ["c1ccc2ccccc2c1"]],
    ]);
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        nodesBySmiles={nodeMap(tree)}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={onToggle}
        onSelect={onSelect}
        childIndex={childIndex}
        colorBins={new Map()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /expand/i }));
    expect(onToggle).toHaveBeenCalledWith("c1ccccc1");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("recursively renders children when expanded", () => {
    const childIndex = new Map<string, string[]>([
      ["c1ccccc1", ["c1ccc2ccccc2c1"]],
    ]);
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        nodesBySmiles={nodeMap(tree)}
        depth={0}
        expanded={new Set(["c1ccccc1"])}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        childIndex={childIndex}
        colorBins={new Map()}
      />,
    );
    // Child node should be rendered
    expect(screen.getByTestId("scaffold-node-c1ccc2ccccc2c1")).toBeInTheDocument();
  });
});

describe("scaffold → search loop closer", () => {
  beforeEach(() => {
    mockPush.mockClear();
    window.sessionStorage.removeItem(STORAGE_KEY);
  });

  it("clicking the 'open in search' action stashes the scaffold and navigates", () => {
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccncc1"
        nodesBySmiles={nodeMap({
          nodes: [{ scaffold_smiles: "c1ccncc1", molecule_count: 1, subtree_molecule_count: 1, molecule_ids: ["m1"] }],
        })}
        childIndex={new Map()}
        colorBins={new Map()}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    const action = screen.getByRole("button", { name: /find compounds with this scaffold/i });
    fireEvent.click(action);
    expect(mockPush).toHaveBeenCalledWith("/search");
    expect(consumeScaffoldSearch()).toEqual({
      type: "scaffold",
      mode: "exact_match",
      scaffold_smiles: "c1ccncc1",
    });
  });

  it("clicking the action on the NO_SCAFFOLD bucket stashes as acyclic_only", () => {
    render(
      <ScaffoldTreeNode
        scaffoldSmiles={NO_SCAFFOLD_SENTINEL}
        nodesBySmiles={nodeMap({
          nodes: [{ scaffold_smiles: NO_SCAFFOLD_SENTINEL, molecule_count: 5, subtree_molecule_count: 5, molecule_ids: [] }],
        })}
        childIndex={new Map()}
        colorBins={new Map()}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /find compounds with this scaffold/i }));
    expect(mockPush).toHaveBeenCalledWith("/search");
    expect(consumeScaffoldSearch()).toEqual({
      type: "scaffold",
      mode: "acyclic_only",
    });
  });

  it("action button click does NOT fire the row select handler", () => {
    const onSelect = vi.fn();
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccncc1"
        nodesBySmiles={nodeMap({
          nodes: [{ scaffold_smiles: "c1ccncc1", molecule_count: 1, subtree_molecule_count: 1, molecule_ids: ["m1"] }],
        })}
        childIndex={new Map()}
        colorBins={new Map()}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={vi.fn()}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /find compounds with this scaffold/i }));
    expect(onSelect).not.toHaveBeenCalled();
  });
});
