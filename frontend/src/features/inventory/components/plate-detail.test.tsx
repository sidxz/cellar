import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { PlateDetail } from "./plate-detail";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
  usePathname: () => "/inventory/plates/p1",
}));
vi.mock("@duar-auth/nextjs", () => ({ useAuthzHasRole: () => true }));
// Side panels with their own data needs — out of scope for these assertions.
vi.mock("@/features/tagging/components/tag-table", () => ({ TagTable: () => null }));
vi.mock("@/features/attachment", () => ({
  AttachmentList: () => null,
  FileUploadZone: () => null,
}));
const mocked = vi.mocked(customInstance);

beforeAll(() => {
  // Radix menus/dialogs in jsdom (verbatim from request-loan-dialog.test.tsx).
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const basePlate = {
  id: "p1",
  barcode: "0001",
  plate_label: "SAC1-014-0001",
  format: "384",
  plate_type: "assay",
  status: "stored",
  storage_location_id: "frz",
  owner_org_id: "A",
  group_id: "g1",
  registered_by: "u1",
  well_map: null,
  notes: null,
  project_id: null,
  template_id: null,
  parent_plate_id: null,
  workspace_id: "w",
};
const openLoan = {
  id: "l1",
  status: "open",
  owner_org_id: "A",
  borrower_org_id: "A",
  requested_by: "u1",
  due_date: "2000-01-01",
  // Noon UTC: still Aug 1 in every local timezone the test may run in.
  created_at: "2026-08-01T12:00:00Z",
  closed_at: null,
  notes: null,
  items: [
    {
      id: "i1",
      plate_id: "p1",
      barcode: "0001",
      plate_label: "x",
      status: "checked_out",
      status_changed_at: "2026-08-01T12:00:00Z",
    },
  ],
};

function setup(
  plate = basePlate,
  loans: unknown[] = [],
  runs: unknown[] = [],
  shipments: unknown[] = [],
) {
  mocked.mockReset();
  pushMock.mockReset();
  mocked.mockImplementation((opts: { url: string; method: string }) => {
    if (opts.url === "/api/v1/plates/p1" && opts.method === "DELETE")
      return Promise.resolve(undefined);
    if (opts.url === "/api/v1/plates/p1") return Promise.resolve(plate);
    if (opts.url === "/api/v1/plates/p1/children") return Promise.resolve([]);
    if (opts.url === "/api/v1/plates/p1/runs") return Promise.resolve(runs);
    if (opts.url === "/api/v1/plates/p1/shipments") return Promise.resolve(shipments);
    if (opts.url === "/api/v1/plate-loans") return Promise.resolve(loans);
    if (opts.url === "/api/v1/storage-locations")
      return Promise.resolve([
        { id: "site", name: "TAMU", parent_id: null, type: "site", workspace_id: "w" },
        { id: "bld", name: "ILSB", parent_id: "site", type: "building", workspace_id: "w" },
        { id: "room", name: "Room 1148", parent_id: "bld", type: "room", workspace_id: "w" },
        { id: "frz", name: "Freezer 3", parent_id: "room", type: "freezer", workspace_id: "w" },
      ]);
    if (opts.url === "/api/v1/orgs")
      return Promise.resolve([{ id: "A", slug: "tamu", name: "TAMU" }]);
    if (opts.url === "/api/v1/organizations") return Promise.resolve([{ id: "A", name: "TAMU" }]);
    if (opts.url === "/api/v1/user/workspace-members")
      return Promise.resolve([
        { user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" },
      ]);
    if (opts.url === "/api/v1/plate-groups/g1")
      return Promise.resolve({
        group: { id: "g1", name: "Set 014", owner_org_id: "A" },
        ancestors: [{ id: "lib", name: "SAC1" }],
        children: [],
        plate_count: 1,
        subtree_plate_count: 1,
      });
    if (opts.url === "/api/v1/comments") return Promise.resolve([]);
    if (opts.url === "/api/v1/plate-groups/tree") return Promise.resolve({ roots: [] });
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<PlateDetail plateId="p1" />, { wrapper });
}

describe("PlateDetail hero", () => {
  it("on loan: status · requester · since · due, link to the loan, no Request loan action", async () => {
    setup(basePlate, [openLoan]);
    const hero = await screen.findByTestId("plate-hero");
    await waitFor(() => expect(hero).toHaveTextContent("Maia Young"));
    expect(hero).toHaveTextContent("Checked Out");
    expect(hero).toHaveTextContent(/since Aug 1, 2026/);
    expect(hero).toHaveTextContent(/y overdue/);
    expect(screen.getByRole("link", { name: /view loan/i })).toHaveAttribute(
      "href",
      "/inventory/loans/l1",
    );
    expect(screen.queryByRole("button", { name: "Request loan" })).not.toBeInTheDocument();
  });
  it("in storage: full path; Request loan opens the dialog pre-filled with this barcode", async () => {
    setup();
    const hero = await screen.findByTestId("plate-hero");
    await waitFor(() =>
      expect(hero).toHaveTextContent("In storage · ILSB › Room 1148 › Freezer 3"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Request loan" }));
    const box = (await screen.findByLabelText("Barcodes")) as HTMLTextAreaElement;
    expect(box.value).toBe("0001");
  });
  it("depleted: muted terminal line, no Request loan", async () => {
    setup({ ...basePlate, status: "depleted" });
    const hero = await screen.findByTestId("plate-hero");
    expect(hero).toHaveTextContent("Depleted");
    expect(screen.queryByRole("button", { name: "Request loan" })).not.toBeInTheDocument();
  });
});

describe("PlateDetail body", () => {
  it("identity row links the set path; no Well Map card without wells; history lists loans", async () => {
    setup(basePlate, [openLoan]);
    expect(await screen.findByRole("link", { name: "SAC1 › Set 014" })).toHaveAttribute(
      "href",
      "/inventory/plate-groups/g1",
    );
    expect(screen.queryByText(/^Well Map/)).not.toBeInTheDocument();
    const history = await screen.findByTestId("loan-history");
    await waitFor(() => expect(history).toHaveTextContent("Maia Young"));
    expect(history.querySelector("a")).toHaveAttribute("href", "/inventory/loans/l1");
  });
  it("Used in runs lists protocol · Run date · plate number · status and links to the run", async () => {
    setup(
      basePlate,
      [],
      [
        {
          run_id: "r1",
          run_date: "2026-08-20",
          run_status: "completed",
          protocol_id: "pr1",
          protocol_name: "Mtb MABA",
          plate_number: 2,
          created_at: "2026-08-20T12:00:00Z",
        },
      ],
    );
    const card = await screen.findByTestId("plate-runs");
    await waitFor(() => expect(card).toHaveTextContent("Mtb MABA"));
    expect(card).toHaveTextContent("Run Aug 20, 2026");
    expect(card).toHaveTextContent("Plate 2");
    expect(card).toHaveTextContent("Completed");
    expect(card.querySelector("a")).toHaveAttribute("href", "/assays/runs/r1");
  });
  it("Used in runs: empty copy when the plate was never run", async () => {
    setup();
    const card = await screen.findByTestId("plate-runs");
    await waitFor(() => expect(card).toHaveTextContent("Not used in any run yet."));
  });
  it("Shipments card: arrow · org · status, linking to the shipment", async () => {
    setup(
      basePlate,
      [],
      [],
      [
        {
          shipment_id: "s1",
          direction: "outbound",
          status: "shipped",
          destination_org_id: "A",
          tracking_number: "7489",
          carrier: "FedEx",
          shipping_date: "2026-09-01",
          received_date: null,
          amount_value: null,
          amount_unit: null,
          created_at: "2026-08-30T12:00:00Z",
        },
      ],
    );
    const card = await screen.findByTestId("shipment-links");
    await waitFor(() => expect(card).toHaveTextContent("→ TAMU"));
    expect(card).toHaveTextContent("Shipped");
    expect(card).toHaveTextContent("shipped Sep 1, 2026");
    expect(card.querySelector("a")).toHaveAttribute("href", "/inventory/shipments/s1");
  });
  it("Shipments card: empty copy when the plate was never shipped", async () => {
    setup();
    const card = await screen.findByTestId("shipment-links");
    await waitFor(() => expect(card).toHaveTextContent("Never shipped."));
  });
  it("More → Delete → confirm deletes and returns to the list", async () => {
    setup();
    await screen.findByTestId("plate-hero");
    // Radix menus open on keyboard in jsdom (pattern from shared/components/layout/header.test.tsx).
    fireEvent.keyDown(screen.getByRole("button", { name: /more/i }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: /delete plate/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({ url: "/api/v1/plates/p1", method: "DELETE" }),
      ),
    );
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/inventory/plates"));
  });
});
