import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UseScaffoldTreeReturn } from "../hooks/use-scaffold-tree";

import { NO_SCAFFOLD_SENTINEL } from "../types/scaffold-tree";
import { SCAFFOLD_TREE_TOAST_ID, ScaffoldTreeView } from "./scaffold-tree-view";

// ---------------------------------------------------------------------------
// customInstance mock — used by useCollectionScaffoldSearch (V4 Path A tests)
// ---------------------------------------------------------------------------
const mockCustomInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (...args: any[]) => mockCustomInstance(...args),
}));

// next/navigation requires the App Router context — stub out for tests.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// react-resizable-panels uses ResizeObserver + layout APIs not in jsdom.
// Mock it so tests focus on selection logic, not panel internals.
vi.mock("@/shared/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: any) => <div data-testid="resizable-group">{children}</div>,
  ResizablePanel: ({ children }: any) => <div data-testid="resizable-panel">{children}</div>,
  ResizableHandle: () => <div data-testid="resizable-handle" />,
}));

// Stable fixture tree — shared by both the existing tests and the new
// toast tests. Defined outside the mock factory so we can reference it
// in rerender calls too.
const fixtureTree = {
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

// The mock is a vi.fn() so the toast-wiring tests can override the return
// value per-test via mockReturnValue(). The default implementation returns
// the stable tree so all existing tests continue to pass unchanged.
//
// Typed explicitly so that mockReturnValue() calls accept nullable tree
// values without TS complaining about the inferred non-nullable type from
// the default literal.
const mockUseScaffoldTree = vi.fn(
  (): UseScaffoldTreeReturn => ({
    tree: fixtureTree,
    jobId: null,
    isStarting: false,
    isPolling: false,
    error: null,
  }),
);

vi.mock("../hooks/use-scaffold-tree", () => ({
  // Ignore the params — the mock controls return value via mockReturnValue().
  // Using a single ignored param avoids the TS2556 "spread must have tuple
  // type" error from (...args: any[]) in vi.mock factory closures.
  useScaffoldTree: (_p: unknown) => mockUseScaffoldTree(),
}));

// Sonner — mock the three methods the component calls.
vi.mock("sonner", () => ({
  toast: {
    loading: vi.fn(),
    success: vi.fn(),
    dismiss: vi.fn(),
  },
}));

// Cancel endpoint — track calls without hitting the network.
const mockCancel = vi.fn();
vi.mock("@/shared/lib/api/scaffold-tree/scaffold-tree", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/shared/lib/api/scaffold-tree/scaffold-tree")>();
  return {
    ...actual,
    cancelScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdCancelPost: (jobId: string) => mockCancel(jobId),
  };
});

// Mock CardGrid — tracks the molecule count passed in
vi.mock("@/features/research-organization/components/results/card-grid", () => ({
  CardGrid: ({ molecules }: any) => <div data-testid="card-grid">{molecules.length} cards</div>,
}));

// Mock StructureThumbnail (RDKit-free shim)
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: any) => <div data-testid={`thumb-${smiles}`} />,
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
    await waitFor(() => expect(screen.getByTestId("scaffold-group-c1ccccc1")).toBeInTheDocument());
    // Both nodes shown as groups (both have molecule_count > 0)
    expect(screen.getByTestId("scaffold-group-c1ccc2ccccc2c1")).toBeInTheDocument();
  });

  it("right pane shows all molecules when no group selected", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    await waitFor(() => expect(screen.getByTestId("card-grid")).toHaveTextContent("3 cards"));
  });

  it("clicking a group filters cards to that group's DIRECT members only", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    // benzene group has molecule_ids = [m1, m2] (direct only — NOT m3 from
    // the naphthalene descendant; that's the hierarchy-mode subtree story)
    fireEvent.click(await screen.findByTestId("scaffold-group-c1ccccc1"));
    await waitFor(() => expect(screen.getByTestId("card-grid")).toHaveTextContent("2 cards"));
  });

  it("min-mols pill hides single-member chemotypes", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    await screen.findByTestId("scaffold-group-c1ccccc1");

    const pill = screen.getByTitle(/cycle minimum members/i);
    fireEvent.click(pill); // 1 → 2
    await waitFor(() => expect(screen.queryByTestId("scaffold-group-c1ccc2ccccc2c1")).toBeNull());
    // benzene still visible (count=2 >= min=2)
    expect(screen.getByTestId("scaffold-group-c1ccccc1")).toBeInTheDocument();
  });
});

describe("ScaffoldTreeView — Hierarchy mode", () => {
  it("renders the tree with first-level nodes after switching", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    switchToHierarchy();
    await waitFor(() => expect(screen.getByTestId("scaffold-node-c1ccccc1")).toBeInTheDocument());
  });

  it("clicking a node filters cards to its full subtree", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    switchToHierarchy();
    fireEvent.click(await screen.findByTestId("scaffold-node-c1ccccc1"));
    // benzene subtree = m1, m2 (benzene direct) + m3 (naphthalene descendant) = 3
    await waitFor(() => expect(screen.getByTestId("card-grid")).toHaveTextContent("3 cards"));
  });

  it("clicking selected node again deselects (back to all)", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, {
      wrapper,
    });
    switchToHierarchy();
    const node = await screen.findByTestId("scaffold-node-c1ccccc1");
    fireEvent.click(node);
    fireEvent.click(node);
    await waitFor(() => expect(screen.getByTestId("card-grid")).toHaveTextContent("3 cards"));
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
    await waitFor(() => expect(screen.queryByTestId("scaffold-node-c1ccccc1")).toBeNull());
    expect(screen.getByText(/no scaffolds match/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Toast wiring tests (Wave 4 / C1)
// ---------------------------------------------------------------------------

/**
 * Render <ScaffoldTreeView> with the hook returning the given values.
 * Returns a rerender helper that accepts the next hook-return override.
 */
function renderWithHookState(initial: UseScaffoldTreeReturn) {
  mockUseScaffoldTree.mockReturnValue(initial);
  const result = render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, { wrapper });
  return {
    rerender: (next: UseScaffoldTreeReturn) => {
      mockUseScaffoldTree.mockReturnValue(next);
      result.rerender(<ScaffoldTreeView molecules={molecules} activityData={{}} />);
    },
  };
}

describe("ScaffoldTreeView — async-compute Sonner toast (Wave 4 / C1)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    (toast.loading as ReturnType<typeof vi.fn>).mockClear();
    (toast.success as ReturnType<typeof vi.fn>).mockClear();
    (toast.dismiss as ReturnType<typeof vi.fn>).mockClear();
    mockCancel.mockClear();
    // Reset hook back to the default stable-tree state between tests.
    mockUseScaffoldTree.mockReturnValue({
      tree: fixtureTree,
      jobId: null,
      isStarting: false,
      isPolling: false,
      error: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a loading toast after 3 s of pending state", () => {
    renderWithHookState({
      isStarting: true,
      isPolling: false,
      tree: null,
      jobId: null,
      error: null,
    });
    // Before 3 s — toast must NOT have fired yet.
    expect(toast.loading).not.toHaveBeenCalled();
    vi.advanceTimersByTime(3000);
    expect(toast.loading).toHaveBeenCalledWith(
      "Computing scaffold tree…",
      expect.objectContaining({
        id: SCAFFOLD_TREE_TOAST_ID,
        duration: Number.POSITIVE_INFINITY,
        action: expect.objectContaining({ label: "Cancel" }),
      }),
    );
  });

  it("does NOT show a toast when compute completes within 3 s", () => {
    const { rerender } = renderWithHookState({
      isStarting: true,
      isPolling: false,
      tree: null,
      jobId: null,
      error: null,
    });
    vi.advanceTimersByTime(2000);
    // Tree arrives before the 3-second threshold fires.
    rerender({
      isStarting: false,
      isPolling: false,
      tree: fixtureTree,
      jobId: null,
      error: null,
    });
    vi.advanceTimersByTime(2000); // would have fired the toast if not cleared
    expect(toast.loading).not.toHaveBeenCalled();
  });

  it("dismisses the toast when the tree arrives after the 3-s mark", () => {
    const { rerender } = renderWithHookState({
      isStarting: true,
      isPolling: false,
      tree: null,
      jobId: null,
      error: null,
    });
    vi.advanceTimersByTime(3000);
    expect(toast.loading).toHaveBeenCalledTimes(1);

    // Tree arrives — component re-renders with isWorking = false.
    rerender({
      isStarting: false,
      isPolling: false,
      tree: fixtureTree,
      jobId: null,
      error: null,
    });
    expect(toast.dismiss).toHaveBeenCalledWith(SCAFFOLD_TREE_TOAST_ID);
  });

  it("Cancel action fires the cancel API call then dismisses and toasts success", () => {
    renderWithHookState({
      isStarting: false,
      isPolling: true,
      tree: null,
      jobId: "job-123",
      error: null,
    });
    vi.advanceTimersByTime(3000);
    expect(toast.loading).toHaveBeenCalledTimes(1);

    // Grab the action handler from the toast.loading call.
    const opts = (toast.loading as ReturnType<typeof vi.fn>).mock.calls[0][1];
    opts.action.onClick();

    expect(mockCancel).toHaveBeenCalledWith("job-123");
    expect(toast.dismiss).toHaveBeenCalledWith(SCAFFOLD_TREE_TOAST_ID);
    expect(toast.success).toHaveBeenCalledWith(
      "Scaffold tree cancelled",
      expect.objectContaining({ id: SCAFFOLD_TREE_TOAST_ID }),
    );
  });
});

// ---------------------------------------------------------------------------
// V4 Path A — server-side scaffold filter tests
// ---------------------------------------------------------------------------
// These tests verify that `useCollectionScaffoldSearch` is invoked (via
// `customInstance`) when `collectionId` is set + a scaffold is selected, and
// is NOT invoked when `collectionId` is absent (ad-hoc result sets).

describe("ScaffoldTreeView — V4 Path A server-side scaffold filter", () => {
  beforeEach(() => {
    // Default: server returns an empty items list (we care about the call,
    // not the rendered cards, in these tests).
    mockCustomInstance.mockReset();
    mockCustomInstance.mockResolvedValue({ items: [] });
    // Reset hook to stable tree state.
    mockUseScaffoldTree.mockReturnValue({
      tree: fixtureTree,
      jobId: null,
      isStarting: false,
      isPolling: false,
      error: null,
    });
  });

  it("invokes customInstance with scaffold exact_match_in body when scaffold selected on a collection page (Groups mode)", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} collectionId="col-abc" />, {
      wrapper,
    });

    // Groups mode is the default. Find the benzene row by its data-testid
    // (set in scaffold-groups-list.tsx: data-testid=`scaffold-group-${smiles}`).
    const benzeneRow = await screen.findByTestId("scaffold-group-c1ccccc1");
    fireEvent.click(benzeneRow);

    await waitFor(() => {
      expect(mockCustomInstance).toHaveBeenCalled();
    });

    const call = mockCustomInstance.mock.calls[0][0];
    expect(call.url).toBe("/api/v1/search/execute");

    // The group criterion wraps collection + scaffold in an AND.
    const groupCrit = call.data.query.criteria[0];
    expect(groupCrit.type).toBe("group");
    expect(groupCrit.logic).toBe("and");

    // One sub-criterion must be the collection criterion.
    expect(groupCrit.criteria).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: "collection",
          collection_id: "col-abc",
        }),
      ]),
    );

    // One sub-criterion must be the scaffold exact_match_in criterion.
    expect(groupCrit.criteria).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: "scaffold",
          mode: "exact_match_in",
          scaffold_smiles_list: ["c1ccccc1"],
        }),
      ]),
    );
  });

  it("does NOT invoke customInstance when collectionId is absent (ad-hoc result set)", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} />, { wrapper });

    // Select the same benzene row.
    const benzeneRow = await screen.findByTestId("scaffold-group-c1ccccc1");
    fireEvent.click(benzeneRow);

    // Wait a tick to ensure no async call was scheduled.
    await new Promise((r) => setTimeout(r, 50));
    expect(mockCustomInstance).not.toHaveBeenCalled();
  });

  it("does NOT invoke customInstance when the NO_SCAFFOLD bucket is selected (acyclic mols use in-memory filter)", async () => {
    // Tree fixture WITH a NO_SCAFFOLD bucket row.
    mockUseScaffoldTree.mockReturnValue({
      tree: {
        nodes: [
          ...fixtureTree.nodes,
          {
            scaffold_smiles: NO_SCAFFOLD_SENTINEL,
            molecule_ids: ["m4", "m5"],
            molecule_count: 2,
            subtree_molecule_count: 2,
          },
        ],
        edges: fixtureTree.edges,
        stats: fixtureTree.stats,
      },
      jobId: null,
      isStarting: false,
      isPolling: false,
      error: null,
    });

    const acyclicMols = [
      ...molecules,
      { id: "m4", bemis_murcko_smiles: "", structure: { smiles: "CCCC" } } as any,
      { id: "m5", bemis_murcko_smiles: "", structure: { smiles: "CCO" } } as any,
    ];

    render(
      <ScaffoldTreeView molecules={acyclicMols} activityData={{}} collectionId="col-acyclic" />,
      { wrapper },
    );

    const bucket = await screen.findByTestId(`scaffold-group-${NO_SCAFFOLD_SENTINEL}`);
    fireEvent.click(bucket);

    // No server call: the sentinel is not a real SMILES; BE `exact_match_in`
    // would silently drop it and return zero rows. The in-memory fallback
    // handles the bucket correctly.
    await new Promise((r) => setTimeout(r, 50));
    expect(mockCustomInstance).not.toHaveBeenCalled();

    // Right pane should show the 2 acyclic cards (m4 + m5), not "0 cards".
    expect(screen.getByTestId("card-grid")).toHaveTextContent("2 cards");
  });

  it("includes all subtree scaffold SMILES in the criterion body for Hierarchy mode", async () => {
    render(<ScaffoldTreeView molecules={molecules} activityData={{}} collectionId="col-xyz" />, {
      wrapper,
    });

    // Switch to Hierarchy mode.
    fireEvent.click(screen.getByRole("button", { name: /hierarchy/i }));

    // Click the benzene root node — its subtree includes itself + naphthalene.
    const benzeneNode = await screen.findByTestId("scaffold-node-c1ccccc1");
    fireEvent.click(benzeneNode);

    await waitFor(() => {
      expect(mockCustomInstance).toHaveBeenCalled();
    });

    const call = mockCustomInstance.mock.calls[0][0];
    const groupCrit = call.data.query.criteria[0];
    const scaffoldCrit = groupCrit.criteria.find((c: any) => c.type === "scaffold");
    // Benzene subtree contains both scaffold SMILES (benzene + naphthalene).
    expect(scaffoldCrit.scaffold_smiles_list).toEqual(
      expect.arrayContaining(["c1ccccc1", "c1ccc2ccccc2c1"]),
    );
    expect(scaffoldCrit.mode).toBe("exact_match_in");
  });
});
