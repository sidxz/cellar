import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { CreateShipmentDialog } from "./create-shipment-dialog";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
// Compound search has its own data needs — the cascade rows are out of scope here.
vi.mock("./molecule-selector", () => ({ MoleculeSelector: () => null }));
const mocked = vi.mocked(customInstance);

beforeAll(() => {
  // Radix Select/Popover in jsdom (verbatim from request-loan-dialog.test.tsx).
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const resolved = [
  { barcode: "0001", item_type: "plate", item_id: "p1", label: "SAC1-014-0001", error: null },
  { barcode: "SMP-1", item_type: "sample", item_id: "smp1", label: "B-001", error: null },
  { barcode: "nope", item_type: null, item_id: null, label: null, error: "not found" },
];
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

function setup() {
  mocked.mockReset();
  mocked.mockImplementation((opts: { url: string; method: string }) => {
    if (opts.url === "/api/v1/organizations") return Promise.resolve([{ id: "o1", name: "WuXi" }]);
    if (opts.url === "/api/v1/plate-loans") return Promise.resolve([loan]);
    if (opts.url === "/api/v1/user/workspace-members")
      return Promise.resolve([
        { user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" },
      ]);
    if (opts.url === "/api/v1/shipments/resolve-items") return Promise.resolve(resolved);
    if (opts.url === "/api/v1/shipments") return Promise.resolve({ id: "s1" });
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<CreateShipmentDialog open onOpenChange={() => {}} />, { wrapper });
}

async function resolveBarcodes(text: string) {
  fireEvent.change(screen.getByLabelText("Barcodes"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Resolve" }));
  return within(await screen.findByTestId("resolved-items"));
}

describe("CreateShipmentDialog", () => {
  it("direction toggle relabels the organization field", () => {
    setup();
    expect(screen.getByLabelText(/destination organization/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Inbound" }));
    expect(screen.getByLabelText(/from organization/i)).toBeInTheDocument();
  });

  it("resolve: plate row without amount, sample row with amount, unresolved barcodes in red", async () => {
    setup();
    const list = await resolveBarcodes("0001\nSMP-1\nnope");
    expect(list.getByText("Plate")).toBeInTheDocument();
    expect(list.getByText("SAC1-014-0001")).toBeInTheDocument();
    expect(list.getByText("Sample")).toBeInTheDocument();
    expect(list.queryByLabelText("Amount for 0001")).not.toBeInTheDocument();
    expect(list.getByLabelText("Amount for SMP-1")).toBeInTheDocument();
    expect(screen.getByText("nope — not found")).toHaveClass("text-destructive");
  });

  it("submits direction, loan_id and typed items (plates without amount)", async () => {
    setup();
    fireEvent.click(await screen.findByLabelText(/destination organization/i));
    fireEvent.click(await screen.findByRole("option", { name: "WuXi" }));
    fireEvent.click(screen.getByRole("radio", { name: "Inbound" }));
    fireEvent.click(screen.getByText("No loan"));
    fireEvent.click(await screen.findByRole("option", { name: "Maia Young · 1 plate" }));
    const list = await resolveBarcodes("0001\nSMP-1");
    fireEvent.change(list.getByLabelText("Amount for SMP-1"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Shipment" }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/shipments",
          method: "POST",
          data: expect.objectContaining({
            destination_org_id: "o1",
            direction: "inbound",
            loan_id: "l1",
            items: [
              { item_type: "plate", item_id: "p1" },
              { item_type: "sample", item_id: "smp1", amount_value: 2, amount_unit: "mg" },
            ],
          }),
        }),
      ),
    );
  });
});
