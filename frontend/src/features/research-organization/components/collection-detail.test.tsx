import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CollectionDetail } from "./collection-detail";

// Stub Next.js + Duar + every downstream hook so we exercise ONLY the
// frozen-button gating logic in CollectionDetail itself.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/collections/c1",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@duar-auth/nextjs", () => ({
  useAuthzHasRole: () => false,
}));

const mockUseCollection = vi.fn();
const mockUseCollectionSearch = vi.fn();
vi.mock("../hooks/use-collections", () => ({
  useCollection: (...args: unknown[]) => mockUseCollection(...args),
  useDeleteCollection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../hooks/use-collection-search", () => ({
  useCollectionSearch: (...args: unknown[]) => mockUseCollectionSearch(...args),
}));
vi.mock("../hooks/use-collection-molecules", () => ({
  useRemoveMolecules: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("../hooks/use-projects", () => ({
  useProject: () => ({ data: null }),
  useProjects: () => ({ data: [] }),
}));
vi.mock("../hooks/use-protocol-test-counts", () => ({
  useProtocolTestCounts: () => ({ data: {} }),
}));
vi.mock("@/features/chemical-registration/hooks/use-sdf-export", () => ({
  useSdfExport: () => ({ exportSdf: vi.fn() }),
}));

// Stub the heavy children so we don't pull AG Grid / RDKit.js etc. into jsdom.
vi.mock("./create-collection-dialog", () => ({ CreateCollectionDialog: () => null }));
vi.mock("./add-molecules-dialog", () => ({ AddMoleculesDialog: () => null }));
vi.mock("./collection/collection-header", () => ({
  CollectionHeader: ({ rightSlot }: { rightSlot?: React.ReactNode }) => <div>{rightSlot}</div>,
}));
vi.mock("./results/results-surface", () => ({
  ResultsSurface: ({
    onSelectChange,
  }: {
    onSelectChange: (id: string, selected: boolean) => void;
  }) => (
    <button type="button" onClick={() => onSelectChange("m1", true)} data-testid="mock-select-m1">
      select m1
    </button>
  ),
}));
vi.mock("./results/view-mode-toggle", () => ({ ViewModeToggle: () => <div /> }));
vi.mock("./collection-plate-groups-card", () => ({ CollectionPlateGroupsCard: () => null }));
vi.mock("@/shared/components/detail-shell", () => ({
  DetailShell: ({
    query,
    actions,
    children,
  }: {
    query: { data: unknown };
    actions: () => React.ReactNode;
    children: (c: unknown) => React.ReactNode;
  }) => (
    <div>
      <div>{actions()}</div>
      <div>{children(query.data)}</div>
    </div>
  ),
}));
vi.mock("@/shared/components/admin-delete-button", () => ({
  AdminDeleteButton: () => null,
}));
vi.mock("@/shared/components/confirm-delete-dialog", () => ({
  ConfirmDeleteDialog: () => null,
}));

const baseCollection = {
  id: "c1",
  name: "Frozen Set",
  description: null,
  project_id: null,
  owned_by_org_id: null,
  created_by: "u1",
  visibility: "private" as const,
  molecule_count: 5,
  is_frozen: false,
  derived_from_campaign_id: null,
};

function renderWith(collection: typeof baseCollection) {
  mockUseCollection.mockReturnValue({ data: collection, isLoading: false });
  mockUseCollectionSearch.mockReturnValue({
    data: { items: [{ id: "m1" }, { id: "m2" }] },
    isLoading: false,
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CollectionDetail collectionId="c1" />
    </QueryClientProvider>,
  );
}

describe("CollectionDetail frozen-collection gating", () => {
  it("enables Add Molecules when not frozen", () => {
    renderWith({ ...baseCollection, is_frozen: false });
    const btn = screen.getByRole("button", { name: /add molecules/i });
    expect(btn).not.toBeDisabled();
  });

  it("disables Add Molecules when frozen, with a tooltip-style title", () => {
    renderWith({ ...baseCollection, is_frozen: true });
    const btn = screen.getByRole("button", { name: /add molecules/i });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "Frozen collection — unfreeze to modify.");
  });

  it("enables Remove when not frozen and a molecule is selected", () => {
    renderWith({ ...baseCollection, is_frozen: false });
    fireEvent.click(screen.getByTestId("mock-select-m1"));
    const btn = screen.getByRole("button", { name: /^remove$/i });
    expect(btn).not.toBeDisabled();
  });

  it("disables Remove when frozen and a molecule is selected, with the tooltip", () => {
    renderWith({ ...baseCollection, is_frozen: true });
    fireEvent.click(screen.getByTestId("mock-select-m1"));
    const btn = screen.getByRole("button", { name: /^remove$/i });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "Frozen collection — unfreeze to modify.");
  });
});
