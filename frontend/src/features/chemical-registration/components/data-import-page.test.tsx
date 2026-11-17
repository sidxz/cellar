import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataImportPage } from "./data-import-page";

// One running import in each history, so Force Stop would be offered.
const h = vi.hoisted(() => ({
  admin: false,
  idle: { mutate: () => {}, isPending: false },
  // The HTTP call behind Start Import. The start hook is the real one, so the tests read the
  // request as it is sent.
  request: vi.fn(),
  check: { mutateAsync: vi.fn(), isPending: false },
  // What the status poll answers once an import has started; undefined is "no answer yet".
  status: undefined as Record<string, unknown> | undefined,
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
  useOrganizations: () => ({
    data: [
      { id: "org-1", name: "Chemistry Core" },
      { id: "org-2", name: "Biology Core" },
    ],
  }),
}));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: h.request,
}));
vi.mock("../hooks/use-cdd-molecule-import", async (importOriginal) => ({
  useStartCddMoleculeImport: (
    await importOriginal<typeof import("../hooks/use-cdd-molecule-import")>()
  ).useStartCddMoleculeImport,
  useImportHistory: () => ({ data: [h.molecule], refetch: () => {} }),
  useCheckCddMoleculeIdentifiers: () => h.check,
  useForceFailImport: () => h.idle,
  useCancelCddMoleculeImport: () => h.idle,
  useCddMoleculeImportStatus: (workflowId: string | null) => ({
    data: workflowId ? h.status : undefined,
  }),
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

const SPECIFIC = "Specific molecules";
const HINT = "One per line, or separated by commas. Repeats are ignored.";
const PASTED = "SACC-0001, SACC-0002\nSACC-0099";

const chooseOrg = (id: string) =>
  fireEvent.change(screen.getByLabelText("Originating Organization"), { target: { value: id } });
const chooseMode = (name: string) => fireEvent.click(screen.getByRole("radio", { name }));
const paste = (text: string) =>
  fireEvent.change(screen.getByLabelText("Identifiers"), { target: { value: text } });
const pressCheck = () => fireEvent.click(screen.getByRole("button", { name: "Check identifiers" }));
const startButton = () => screen.getByRole("button", { name: "Start Import" });
const CHECK_RESULT = "2 of 3 identifiers found in CDD Vault.";

/** The body of the one request Start Import sent. */
async function sentBody() {
  await waitFor(() => expect(h.request).toHaveBeenCalledOnce());
  const [request] = h.request.mock.calls[0];
  expect(request).toMatchObject({ url: "/api/v1/cdd-import/molecules", method: "POST" });
  return request.data;
}

describe("DataImportPage: import modes", () => {
  beforeEach(() => {
    h.status = undefined;
    h.request.mockReset().mockResolvedValue({ workflow_id: "wf-1" });
    h.check.mutateAsync.mockReset().mockResolvedValue({
      found: ["SACC-0001", "SACC-0002"],
      not_found: ["SACC-0099"],
    });
  });

  it("offers specific molecules as a third mode, not as a section of its own", () => {
    renderAs(false);
    expect(screen.getAllByRole("radio").map((radio) => radio.getAttribute("value"))).toEqual([
      "full_vault",
      "sync",
      "filtered",
    ]);
    expect(screen.getByRole("radio", { name: "Full Vault" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Sync (new molecules only)" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: SPECIFIC })).not.toBeChecked();
    expect(screen.queryByText("Import specific molecules")).toBeNull();
    expect(screen.getAllByRole("button", { name: /import/i })).toHaveLength(1);
  });

  it("shows the identifiers only for specific molecules, and Max molecules only for the others", () => {
    renderAs(false);
    const identifiersShown = () =>
      [
        screen.queryByLabelText("Identifiers"),
        screen.queryByText(HINT),
        screen.queryByRole("button", { name: "Check identifiers" }),
      ].map(Boolean);

    for (const mode of ["Full Vault", "Sync (new molecules only)"]) {
      chooseMode(mode);
      expect(screen.getByLabelText(/Max molecules/)).toBeInTheDocument();
      expect(identifiersShown()).toEqual([false, false, false]);
    }

    chooseMode(SPECIFIC);
    expect(screen.queryByLabelText(/Max molecules/)).toBeNull();
    expect(identifiersShown()).toEqual([true, true, true]);

    chooseMode("Full Vault");
    expect(screen.getByLabelText(/Max molecules/)).toBeInTheDocument();
    expect(identifiersShown()).toEqual([false, false, false]);
  });

  it("lays the specific-molecules controls out in the form: list, hint, check, result, then the one button", async () => {
    renderAs(false);
    chooseMode(SPECIFIC);
    paste(PASTED);
    pressCheck();
    const inOrder = [
      screen.getByRole("radio", { name: SPECIFIC }),
      screen.getByLabelText("Identifiers"),
      screen.getByText(HINT),
      screen.getByRole("button", { name: "Check identifiers" }),
      await screen.findByText(CHECK_RESULT),
      screen.getByText("Not found (1)"),
      startButton(),
    ];
    for (let i = 1; i < inOrder.length; i++) {
      expect(
        inOrder[i - 1].compareDocumentPosition(inOrder[i]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });

  it("keeps the pasted list when the mode is switched away and back", () => {
    renderAs(false);
    chooseMode(SPECIFIC);
    paste(PASTED);
    chooseMode("Sync (new molecules only)");
    chooseMode(SPECIFIC);
    expect(screen.getByLabelText("Identifiers")).toHaveValue(PASTED);
  });

  it("describes the chosen mode in the box at the top", () => {
    renderAs(false);
    expect(screen.getByText("Discover all molecules in your CDD Vault")).toBeInTheDocument();

    chooseMode(SPECIFIC);
    expect(screen.queryByText("Discover all molecules in your CDD Vault")).toBeNull();
    expect(screen.queryByText(/For large vaults/)).toBeNull();
    expect(
      screen.getByText("Import only the molecules you list below, and their batches"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Match each one by the name or a synonym it has in CDD Vault"),
    ).toBeInTheDocument();
    expect(screen.getByText("Touch nothing else in the vault")).toBeInTheDocument();

    chooseMode("Sync (new molecules only)");
    expect(screen.getByText("Discover all molecules in your CDD Vault")).toBeInTheDocument();
    expect(screen.getByText(/For large vaults/)).toBeInTheDocument();
  });

  describe("Full Vault and Sync, as before", () => {
    it("can start as soon as an organization is chosen, with no check", () => {
      renderAs(false);
      expect(startButton()).toBeDisabled();
      chooseOrg("org-1");
      expect(startButton()).toBeEnabled();
      chooseMode("Sync (new molecules only)");
      expect(startButton()).toBeEnabled();
      expect(h.request).not.toHaveBeenCalled();
      expect(h.check.mutateAsync).not.toHaveBeenCalled();
    });

    it("Full Vault sends the full_vault mode and no filter", async () => {
      renderAs(false);
      chooseOrg("org-1");
      fireEvent.click(startButton());
      expect(await sentBody()).toEqual({
        originating_org_id: "org-1",
        import_mode: "full_vault",
        filter_criteria: null,
        max_molecules: null,
      });
    });

    it("Sync sends the sync mode, with Max molecules when one is given", async () => {
      renderAs(false);
      chooseOrg("org-2");
      chooseMode("Sync (new molecules only)");
      fireEvent.change(screen.getByLabelText(/Max molecules/), { target: { value: "5" } });
      fireEvent.click(startButton());
      expect(await sentBody()).toEqual({
        originating_org_id: "org-2",
        import_mode: "sync",
        filter_criteria: null,
        max_molecules: 5,
      });
    });

    it("does not send a list checked in the specific mode", async () => {
      renderAs(false);
      chooseOrg("org-1");
      chooseMode(SPECIFIC);
      paste(PASTED);
      pressCheck();
      await screen.findByText(CHECK_RESULT);
      chooseMode("Full Vault");
      fireEvent.click(startButton());
      expect(await sentBody()).toMatchObject({ import_mode: "full_vault", filter_criteria: null });
    });
  });

  describe("Specific molecules", () => {
    it("starts only after a check that found molecules, with the count beside the button", async () => {
      renderAs(false);
      chooseOrg("org-1");
      chooseMode(SPECIFIC);
      expect(startButton()).toBeDisabled();
      paste(PASTED);
      expect(startButton()).toBeDisabled();
      expect(h.check.mutateAsync).not.toHaveBeenCalled();

      pressCheck();
      await screen.findByText(CHECK_RESULT);
      // The server parses the list: it gets the text exactly as pasted.
      expect(h.check.mutateAsync).toHaveBeenCalledExactlyOnceWith(PASTED);
      expect(startButton()).toBeEnabled();
      expect(startButton()).toHaveTextContent(/^Start Import$/);
      expect(screen.getByText("2 found").parentElement).toBe(startButton().parentElement);
      expect(h.request).not.toHaveBeenCalled();
    });

    it("asks for a new check once the list is edited", async () => {
      renderAs(false);
      chooseOrg("org-1");
      chooseMode(SPECIFIC);
      paste(PASTED);
      pressCheck();
      await screen.findByText(CHECK_RESULT);

      paste(`${PASTED}\nSACC-0003`);
      expect(startButton()).toBeDisabled();
      expect(screen.queryByText(CHECK_RESULT)).toBeNull();
      expect(screen.queryByText("2 found")).toBeNull();
    });

    it("asks for a new check once the organization is changed", async () => {
      renderAs(false);
      chooseOrg("org-1");
      chooseMode(SPECIFIC);
      paste(PASTED);
      pressCheck();
      await screen.findByText(CHECK_RESULT);
      expect(startButton()).toBeEnabled();

      chooseOrg("org-2");
      expect(startButton()).toBeDisabled();
      expect(screen.queryByText(CHECK_RESULT)).toBeNull();
    });

    it("keeps a check that still stands when the mode is switched away and back", async () => {
      renderAs(false);
      chooseOrg("org-1");
      chooseMode(SPECIFIC);
      paste(PASTED);
      pressCheck();
      await screen.findByText(CHECK_RESULT);

      chooseMode("Full Vault");
      chooseMode(SPECIFIC);
      expect(screen.getByText(CHECK_RESULT)).toBeInTheDocument();
      expect(startButton()).toBeEnabled();
    });

    it("will not start when nothing was found", async () => {
      h.check.mutateAsync.mockResolvedValue({ found: [], not_found: ["SACC-0099"] });
      renderAs(false);
      chooseOrg("org-1");
      chooseMode(SPECIFIC);
      paste("SACC-0099");
      pressCheck();
      await screen.findByText("0 of 1 identifier found in CDD Vault.");
      expect(startButton()).toBeDisabled();
    });

    it("will not start before an organization is chosen, and says what to do", async () => {
      renderAs(false);
      chooseMode(SPECIFIC);
      paste(PASTED);
      pressCheck();
      await screen.findByText(CHECK_RESULT);
      expect(startButton()).toBeDisabled();
      expect(
        screen.getByText(
          "Select the originating organization above, then check the identifiers again.",
        ),
      ).toBeInTheDocument();
    });

    it("sends the filtered mode with the names the check returned, and never Max molecules", async () => {
      renderAs(false);
      chooseOrg("org-1");
      fireEvent.change(screen.getByLabelText(/Max molecules/), { target: { value: "5" } });
      chooseMode(SPECIFIC);
      paste(PASTED);
      pressCheck();
      await screen.findByText(CHECK_RESULT);

      fireEvent.click(startButton());
      expect(await sentBody()).toEqual({
        originating_org_id: "org-1",
        import_mode: "filtered",
        filter_criteria: { names: ["SACC-0001", "SACC-0002"] },
        max_molecules: null,
      });
      // The running import keeps saying what was left out.
      expect(
        await screen.findByText(/1 identifier was not found in CDD Vault/),
      ).toBeInTheDocument();
      expect(screen.getByText("SACC-0099")).toBeInTheDocument();
    });

    it("comes back with an empty list once the import has run", async () => {
      h.status = {
        status: "completed",
        registered_count: 2,
        duplicate_count: 0,
        error_count: 0,
        skipped_count: 0,
        total_count: 2,
        pages_processed: 1,
      };
      renderAs(false);
      chooseOrg("org-1");
      chooseMode(SPECIFIC);
      paste(PASTED);
      pressCheck();
      await screen.findByText(CHECK_RESULT);
      fireEvent.click(startButton());

      expect(await screen.findByText(/Import completed successfully. 2 molecules/)).toBeVisible();
      expect(screen.getByRole("radio", { name: SPECIFIC })).toBeChecked();
      expect(screen.getByLabelText("Identifiers")).toHaveValue("");
      expect(startButton()).toBeDisabled();
      expect(h.request).toHaveBeenCalledOnce();
    });
  });

  it("labels an import of specific molecules Selected in the history", () => {
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
