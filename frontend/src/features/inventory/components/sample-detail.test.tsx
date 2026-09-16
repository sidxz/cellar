import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { SampleDetail } from "./sample-detail";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
// DetailShell reads the pathname for its breadcrumb.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/inventory/samples/smp1",
}));
vi.mock("@/features/attachment", () => ({
  AttachmentList: () => null,
  FileUploadZone: () => null,
}));
const mocked = vi.mocked(customInstance);

const sample = {
  id: "smp1",
  workspace_id: "w",
  barcode: "SMP-1",
  batch_id: "b1",
  container_type: "vial",
  amount_value: 10,
  amount_unit: "mg",
  solvent: null,
  freeze_thaw_count: 0,
  location_id: null,
  status: "available",
  low_stock_threshold: null,
};

function setup(shipments: unknown[] = []) {
  mocked.mockReset();
  mocked.mockImplementation((opts: { url: string }) => {
    if (opts.url === "/api/v1/samples/smp1") return Promise.resolve(sample);
    if (opts.url === "/api/v1/samples/smp1/shipments") return Promise.resolve(shipments);
    if (opts.url === "/api/v1/batches/b1")
      return Promise.resolve({ id: "b1", batch_number: "B-001", molecule_id: "m1" });
    if (opts.url === "/api/v1/organizations") return Promise.resolve([{ id: "o1", name: "WuXi" }]);
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<SampleDetail sampleId="smp1" />, { wrapper });
}

describe("SampleDetail shipments card", () => {
  it("lists the shipments carrying this sample with the shipped amount", async () => {
    setup([
      {
        shipment_id: "s1",
        direction: "outbound",
        status: "delivered",
        destination_org_id: "o1",
        tracking_number: null,
        carrier: null,
        shipping_date: "2026-09-01",
        received_date: "2026-09-04",
        amount_value: 2.5,
        amount_unit: "mg",
        created_at: "2026-08-30T12:00:00Z",
      },
    ]);
    const card = await screen.findByTestId("shipment-links");
    await waitFor(() => expect(card).toHaveTextContent("→ WuXi"));
    expect(card).toHaveTextContent("Delivered");
    expect(card).toHaveTextContent("2.5 mg");
    expect(card.querySelector("a")).toHaveAttribute("href", "/inventory/shipments/s1");
  });
  it("empty copy when the sample was never shipped", async () => {
    setup();
    const card = await screen.findByTestId("shipment-links");
    await waitFor(() => expect(card).toHaveTextContent("Never shipped."));
  });
});
