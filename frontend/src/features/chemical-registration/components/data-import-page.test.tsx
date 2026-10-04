import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DataImportPage } from "./data-import-page";

// One running import in each history, so Force Stop would be offered.
const h = vi.hoisted(() => ({
  admin: false,
  idle: { mutate: () => {}, isPending: false },
  molecule: {
    id: "m1",
    status: "running",
    import_mode: "full",
    submitted_at: "2026-10-01T00:00:00Z",
    workflow_id: null,
    registered_count: 0,
    duplicate_count: 0,
    error_count: 0,
    skipped_count: 0,
    total_count: 10,
  },
  plate: {
    id: "p1",
    status: "running",
    submitted_at: "2026-10-01T00:00:00Z",
    workflow_id: null,
    plates_registered: 0,
    plates_duplicate: 0,
    plates_error: 0,
    wells_mapped: 0,
    total_count: 4,
  },
}));

vi.mock("@duar-auth/nextjs", () => ({ useAuthzHasRole: () => h.admin }));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/data-import/cdd" }));
vi.mock("@/features/screening-assay/hooks/use-cdd-enabled", () => ({
  useCddEnabled: () => ({ enabled: true, loading: false }),
}));
vi.mock("@/features/workspace-config/hooks/use-organizations", () => ({
  useOrganizations: () => ({ data: [] }),
}));
vi.mock("../hooks/use-cdd-molecule-import", () => ({
  useImportHistory: () => ({ data: [h.molecule], refetch: () => {} }),
  useStartCddMoleculeImport: () => h.idle,
  useForceFailImport: () => h.idle,
  useCancelCddMoleculeImport: () => h.idle,
  useCddMoleculeImportStatus: () => ({ data: undefined }),
}));
vi.mock("../hooks/use-cdd-plate-import", () => ({
  usePlateImportHistory: () => ({ data: [h.plate], refetch: () => {} }),
  useStartCddPlateImport: () => h.idle,
  useForceFailPlateImport: () => h.idle,
  useCancelCddPlateImport: () => h.idle,
  useCddPlateImportStatus: () => ({ data: undefined }),
}));

function renderAs(admin: boolean) {
  h.admin = admin;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DataImportPage />
    </QueryClientProvider>,
  );
}

const openTab = (name: string) =>
  fireEvent.mouseDown(screen.getByRole("tab", { name }), { button: 0 });

/** Force Stop buttons in the molecule history, then the plate history. */
function forceStopsPerHistory() {
  openTab("History");
  const molecules = screen.queryAllByRole("button", { name: "Force Stop" }).length;
  openTab("Plates");
  openTab("History");
  const plates = screen.queryAllByRole("button", { name: "Force Stop" }).length;
  return [molecules, plates];
}

describe("DataImportPage: Force Stop is admin-only, like its backend call", () => {
  it("hides Force Stop from editors in both histories", () => {
    renderAs(false);
    expect(forceStopsPerHistory()).toEqual([0, 0]);
  });

  it("offers Force Stop to admins in both histories", () => {
    renderAs(true);
    expect(forceStopsPerHistory()).toEqual([1, 1]);
  });
});
