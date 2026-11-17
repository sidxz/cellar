import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataImportPage } from "./data-import-page";

// One running import in each history, so Force Stop would be offered.
const h = vi.hoisted(() => ({
  admin: false,
  idle: { mutate: () => {}, isPending: false },
  start: { mutateAsync: vi.fn(), isPending: false },
  check: { mutateAsync: vi.fn(), isPending: false },
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
  useOrganizations: () => ({ data: [{ id: "org-1", name: "Chemistry Core" }] }),
}));
vi.mock("../hooks/use-cdd-molecule-import", () => ({
  useImportHistory: () => ({ data: [h.molecule], refetch: () => {} }),
  useStartCddMoleculeImport: () => h.start,
  useCheckCddMoleculeIdentifiers: () => h.check,
  useForceFailImport: () => h.idle,
  useCancelCddMoleculeImport: () => h.idle,
  useCddMoleculeImportStatus: () => ({ data: undefined }),
}));
// The page's one select (the organization) as a native control jsdom can drive.
vi.mock("@/shared/components/ui/select", () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value: string;
    onValueChange: (v: string) => void;
    children: ReactNode;
  }) => (
    <select
      aria-label="Originating Organization"
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
    >
      <option value="" />
      {children}
    </select>
  ),
  SelectTrigger: () => null,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children: ReactNode }) => (
    <option value={value}>{children}</option>
  ),
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

describe("DataImportPage: import specific molecules", () => {
  beforeEach(() => {
    h.start.mutateAsync.mockReset().mockResolvedValue({ workflow_id: "wf-1" });
    h.check.mutateAsync.mockReset().mockResolvedValue({
      found: ["SACC-0001", "SACC-0002"],
      not_found: ["SACC-0099"],
    });
  });

  it("checks first, then imports only the found molecules for the chosen organization", async () => {
    renderAs(false);
    fireEvent.change(screen.getByLabelText("Originating Organization"), {
      target: { value: "org-1" },
    });
    fireEvent.change(screen.getByLabelText("Identifiers"), {
      target: { value: "SACC-0001, SACC-0002\nSACC-0099" },
    });
    expect(h.check.mutateAsync).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Check identifiers" }));
    await screen.findByText("2 of 3 identifiers found in CDD Vault.");
    // The server parses the list: it gets the text exactly as pasted.
    expect(h.check.mutateAsync).toHaveBeenCalledExactlyOnceWith("SACC-0001, SACC-0002\nSACC-0099");
    expect(h.start.mutateAsync).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(h.start.mutateAsync).toHaveBeenCalledExactlyOnceWith({
        originatingOrgId: "org-1",
        importMode: "filtered",
        filterCriteria: { names: ["SACC-0001", "SACC-0002"] },
      }),
    );
    // The running import keeps saying what was left out.
    expect(await screen.findByText(/1 identifier was not found in CDD Vault/)).toBeInTheDocument();
    expect(screen.getByText("SACC-0099")).toBeInTheDocument();
  });

  it("labels such an import Selected in the history", () => {
    const mode = h.molecule.import_mode;
    h.molecule.import_mode = "filtered";
    try {
      renderAs(false);
      openTab("History");
      expect(screen.getByText("Selected")).toBeInTheDocument();
    } finally {
      h.molecule.import_mode = mode;
    }
  });
});
