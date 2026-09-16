import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ShipmentDetail } from "./shipment-detail";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/inventory/shipments/s1",
}));
vi.mock("@/features/attachment", () => ({
  AttachmentList: () => null,
  FileUploadZone: () => null,
}));
const mocked = vi.mocked(customInstance);

const shipment = {
  id: "s1",
  workspace_id: "w",
  destination_org_id: "o1",
  sender_id: "u1",
  direction: "outbound",
  loan_id: "l1",
  tracking_number: "7489",
  carrier: "FedEx",
  shipping_date: null,
  expected_arrival_date: null,
  received_date: null,
  shipping_conditions: null,
  status: "preparing",
  notes: null,
  items: [
    {
      id: "it1",
      item_type: "plate",
      item_id: "p1",
      barcode: "0001",
      label: "SAC1-014-0001",
      amount_value: null,
      amount_unit: null,
    },
    {
      id: "it2",
      item_type: "sample",
      item_id: "smp1",
      barcode: "SMP-1",
      label: "B-001",
      amount_value: 5,
      amount_unit: "mg",
    },
  ],
};
const loan = {
  id: "l1",
  status: "open",
  owner_org_id: "o1",
  borrower_org_id: "o1",
  requested_by: "u1",
  due_date: null,
  notes: null,
  created_at: "2026-08-13T00:00:00Z",
  closed_at: null,
  items: [
    {
      id: "i1",
      plate_id: "p1",
      barcode: "0001",
      plate_label: "P1",
      status: "approved",
      status_changed_at: "2026-08-13T00:00:00Z",
      group_id: null,
      group_name: null,
    },
  ],
};

function setup(overrides: Record<string, unknown> = {}) {
  mocked.mockReset();
  mocked.mockImplementation((opts: { url: string }) => {
    if (opts.url === "/api/v1/shipments/s1") return Promise.resolve({ ...shipment, ...overrides });
    if (opts.url === "/api/v1/organizations") return Promise.resolve([{ id: "o1", name: "WuXi" }]);
    if (opts.url === "/api/v1/plate-loans/l1") return Promise.resolve(loan);
    if (opts.url === "/api/v1/user/workspace-members")
      return Promise.resolve([
        { user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" },
      ]);
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<ShipmentDetail shipmentId="s1" />, { wrapper });
}

describe("ShipmentDetail", () => {
  it("direction badge, counterparty and the 'carries loan' link", async () => {
    setup();
    expect(await screen.findByText("Outbound")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/Shipment to/)).toHaveTextContent("Shipment to WuXi"),
    );
    const link = await screen.findByRole("link", { name: "Maia Young · 1 plate" });
    expect(link).toHaveAttribute("href", "/inventory/loans/l1");
    expect(screen.getByText(/carries loan/)).toBeInTheDocument();
  });
  it("inbound reads 'Shipment from' and carries no loan line without a loan", async () => {
    setup({ direction: "inbound", loan_id: null });
    expect(await screen.findByText("Inbound")).toBeInTheDocument();
    expect(screen.getByText(/Shipment from/)).toBeInTheDocument();
    expect(screen.queryByText(/carries loan/)).not.toBeInTheDocument();
  });
  it("items table: Type · Barcode (linked to the plate / sample) · Label · Amount", async () => {
    setup();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Plate")).toBeInTheDocument();
    expect(within(table).getByText("Sample")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "0001" })).toHaveAttribute(
      "href",
      "/inventory/plates/p1",
    );
    expect(within(table).getByRole("link", { name: "SMP-1" })).toHaveAttribute(
      "href",
      "/inventory/samples/smp1",
    );
    expect(table).toHaveTextContent("SAC1-014-0001");
    expect(table).toHaveTextContent("5 mg");
  });
});
