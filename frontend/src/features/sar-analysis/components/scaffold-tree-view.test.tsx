import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { ScaffoldTreeView } from "./scaffold-tree-view";

// next/navigation requires the App Router context — stub out for tests.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// react-resizable-panels uses ResizeObserver + layout APIs not in jsdom.
// Mock it so tests focus on selection logic, not panel internals.
vi.mock("@/shared/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: any) => (
    <div data-testid="resizable-group">{children}</div>
  ),
  ResizablePanel: ({ children }: any) => (
    <div data-testid="resizable-panel">{children}</div>
  ),
  ResizableHandle: () => <div data-testid="resizable-handle" />,
}));

// Mock the hook so we don't hit network.
// The tree object is defined INSIDE the factory so it is stable across renders
// (same reference returned by every useScaffoldTree() call). If a new literal
// were returned each call the useEffect([tree]) in the component would fire on
// every render → infinite setState → OOM.
vi.mock("../hooks/use-scaffold-tree", () => {
  const stableTree = {
    nodes: [
      {
        scaffold_smiles: "c1ccccc1",
        molecule_ids: ["m1", "m2"],
        molecule_count: 2,
        subtree_molecule_count: 3,
      },
      {
        scaffold_smiles: "c1ccc2ccccc2c1",
        molecule_ids: ["m3"],
        molecule_count: 1,
        subtree_molecule_count: 1,
      },
    ],
    edges: [{ parent_smiles: "c1ccccc1", child_smiles: "c1ccc2ccccc2c1" }],
    stats: { node_count: 2, elapsed_ms: 5, cache_hit: false },
  };
  return {
    useScaffoldTree: () => ({
      tree: stableTree,
      jobId: null,
      isStarting: false,
      isPolling: false,
      error: null,
    }),
  };
});

// Mock CardGrid — tracks the molecule count passed in
vi.mock(
  "@/features/research-organization/components/results/card-grid",
  () => ({
    CardGrid: ({ molecules }: any) => (
      <div data-testid="card-grid">{molecules.length} cards</div>
    ),
  }),
);

// Mock StructureThumbnail (RDKit-free shim)
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: any) => (
    <div data-testid={`thumb-${smiles}`} />
  ),
}));

// ScaffoldColorPicker uses Radix Select which triggers a ref-update loop in
// jsdom. Mock it so the scaffold-tree-view tests focus on tree + panel logic.
vi.mock("./scaffold-color-picker", () => ({
  ScaffoldColorPicker: ({ value, onChange }: any) => (
    <div data-testid="color-picker" data-value={value ?? "none"} />
  ),
}));

const wrapper = ({ children }: any) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const molecules = [
  {
    id: "m1",
    bemis_murcko_smiles: "c1ccccc1",
    structure: { smiles: "..." },
  } as any,
  {
    id: "m2",
    bemis_murcko_smiles: "c1ccccc1",
    structure: { smiles: "..." },
  } as any,
  {
    id: "m3",
    bemis_murcko_smiles: "c1ccc2ccccc2c1",
    structure: { smiles: "..." },
  } as any,
];

function switchToHierarchy() {
  fireEvent.click(screen.getByRole("button", { name: /hierarchy/i }));
}

describe("ScaffoldTreeView — Groups mode (default)", () => {
  it("renders distinct chemotypes sorted by molecule_count desc", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    await waitFor(() =>
      expect(
        screen.getByTestId("scaffold-group-c1ccccc1"),
      ).toBeInTheDocument(),
    );
    // Both nodes shown as groups (both have molecule_count > 0)
    expect(
      screen.getByTestId("scaffold-group-c1ccc2ccccc2c1"),
    ).toBeInTheDocument();
  });

  it("right pane shows all molecules when no group selected", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    await waitFor(() =>
      expect(screen.getByTestId("card-grid")).toHaveTextContent("3 cards"),
    );
  });

  it("clicking a group filters cards to that group's DIRECT members only", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    // benzene group has molecule_ids = [m1, m2] (direct only — NOT m3 from
    // the naphthalene descendant; that's the hierarchy-mode subtree story)
    fireEvent.click(
      await screen.findByTestId("scaffold-group-c1ccccc1"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("card-grid")).toHaveTextContent("2 cards"),
    );
  });

  it("min-mols pill hides single-member chemotypes", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    await screen.findByTestId("scaffold-group-c1ccccc1");

    const pill = screen.getByTitle(/cycle minimum members/i);
    fireEvent.click(pill); // 1 → 2
    await waitFor(() =>
      expect(
        screen.queryByTestId("scaffold-group-c1ccc2ccccc2c1"),
      ).toBeNull(),
    );
    // benzene still visible (count=2 >= min=2)
    expect(
      screen.getByTestId("scaffold-group-c1ccccc1"),
    ).toBeInTheDocument();
  });
});

describe("ScaffoldTreeView — Hierarchy mode", () => {
  it("renders the tree with first-level nodes after switching", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    switchToHierarchy();
    await waitFor(() =>
      expect(
        screen.getByTestId("scaffold-node-c1ccccc1"),
      ).toBeInTheDocument(),
    );
  });

  it("clicking a node filters cards to its full subtree", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    switchToHierarchy();
    fireEvent.click(await screen.findByTestId("scaffold-node-c1ccccc1"));
    // benzene subtree = m1, m2 (benzene direct) + m3 (naphthalene descendant) = 3
    await waitFor(() =>
      expect(screen.getByTestId("card-grid")).toHaveTextContent("3 cards"),
    );
  });

  it("clicking selected node again deselects (back to all)", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    switchToHierarchy();
    const node = await screen.findByTestId("scaffold-node-c1ccccc1");
    fireEvent.click(node);
    fireEvent.click(node);
    await waitFor(() =>
      expect(screen.getByTestId("card-grid")).toHaveTextContent("3 cards"),
    );
  });

  it("min-mols pill hides root nodes below the threshold", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    switchToHierarchy();
    await screen.findByTestId("scaffold-node-c1ccccc1");

    // Click the pill three times: 1 → 2 → 3 → 5. At 5, benzene (subtree=3) is hidden.
    const pill = screen.getByTitle(/cycle minimum members/i);
    fireEvent.click(pill); // 2
    fireEvent.click(pill); // 3
    fireEvent.click(pill); // 5
    await waitFor(() =>
      expect(screen.queryByTestId("scaffold-node-c1ccccc1")).toBeNull(),
    );
    expect(screen.getByText(/no scaffolds match/i)).toBeInTheDocument();
  });
});
