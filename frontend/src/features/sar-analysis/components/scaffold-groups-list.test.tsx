import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ScaffoldGroupsList } from "./scaffold-groups-list";
import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeResult,
} from "../types/scaffold-tree";

vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => (
    <div data-testid="structure-thumb" data-smiles={smiles} />
  ),
}));

const tree: ScaffoldTreeResult = {
  nodes: [
    // tied counts — alphabetical secondary sort
    {
      scaffold_smiles: "c1ccccc1",
      molecule_ids: ["m1", "m2", "m3"],
      molecule_count: 3,
      subtree_molecule_count: 5,
    },
    {
      scaffold_smiles: "c1ccncc1",
      molecule_ids: ["m4", "m5"],
      molecule_count: 2,
      subtree_molecule_count: 2,
    },
    {
      scaffold_smiles: "c1ccoc1",
      molecule_ids: ["m6"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    },
    // phantom intermediate — molecule_count=0, must be hidden in Groups view
    {
      scaffold_smiles: "phantom",
      molecule_ids: [],
      molecule_count: 0,
      subtree_molecule_count: 6,
    },
  ],
  edges: [],
  stats: { node_count: 4, elapsed_ms: 1, cache_hit: false },
};

describe("ScaffoldGroupsList", () => {
  it("renders only nodes with molecule_count > 0 (no phantoms)", () => {
    render(
      <ScaffoldGroupsList
        tree={tree}
        colorBins={new Map()}
        minMembers={1}
        selected={null}
        onSelect={() => {}}
      />,
    );
    expect(screen.queryByTestId("scaffold-group-phantom")).toBeNull();
    expect(
      screen.getByTestId("scaffold-group-c1ccccc1"),
    ).toBeInTheDocument();
  });

  it("sorts by molecule_count DESC", () => {
    render(
      <ScaffoldGroupsList
        tree={tree}
        colorBins={new Map()}
        minMembers={1}
        selected={null}
        onSelect={() => {}}
      />,
    );
    const rows = screen
      .getAllByTestId(/^scaffold-group-/)
      .map((el) => el.getAttribute("data-testid"));
    expect(rows).toEqual([
      "scaffold-group-c1ccccc1", // 3 mols
      "scaffold-group-c1ccncc1", // 2 mols
      "scaffold-group-c1ccoc1", // 1 mol
    ]);
  });

  it("filters by minMembers", () => {
    render(
      <ScaffoldGroupsList
        tree={tree}
        colorBins={new Map()}
        minMembers={2}
        selected={null}
        onSelect={() => {}}
      />,
    );
    expect(
      screen.getByTestId("scaffold-group-c1ccccc1"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("scaffold-group-c1ccncc1"),
    ).toBeInTheDocument();
    // c1ccoc1 has count=1, hidden at min=2
    expect(screen.queryByTestId("scaffold-group-c1ccoc1")).toBeNull();
  });

  it("renders empty-state when nothing passes the filter", () => {
    render(
      <ScaffoldGroupsList
        tree={tree}
        colorBins={new Map()}
        minMembers={10}
        selected={null}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText(/no chemotypes shared/i)).toBeInTheDocument();
  });

  it("calls onSelect with the scaffold SMILES on row click", () => {
    const handle = vi.fn();
    render(
      <ScaffoldGroupsList
        tree={tree}
        colorBins={new Map()}
        minMembers={1}
        selected={null}
        onSelect={handle}
      />,
    );
    fireEvent.click(screen.getByTestId("scaffold-group-c1ccncc1"));
    expect(handle).toHaveBeenCalledWith("c1ccncc1");
  });

  it("renders 'no scaffold' label for the sentinel bucket", () => {
    const treeWithBucket: ScaffoldTreeResult = {
      ...tree,
      nodes: [
        ...tree.nodes,
        {
          scaffold_smiles: NO_SCAFFOLD_SENTINEL,
          molecule_ids: ["m7", "m8"],
          molecule_count: 2,
          subtree_molecule_count: 2,
        },
      ],
    };
    render(
      <ScaffoldGroupsList
        tree={treeWithBucket}
        colorBins={new Map()}
        minMembers={1}
        selected={null}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText(/no scaffold/i)).toBeInTheDocument();
  });

  it("shows pluralized mol count: '1 mol' vs '3 mols'", () => {
    render(
      <ScaffoldGroupsList
        tree={tree}
        colorBins={new Map()}
        minMembers={1}
        selected={null}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("mol")).toBeInTheDocument(); // for the singleton row
    expect(screen.getAllByText("mols").length).toBeGreaterThanOrEqual(1);
  });
});
