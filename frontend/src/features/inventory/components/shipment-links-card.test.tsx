import { customInstance } from "@/shared/lib/api/custom-instance";
import type { ShipmentLinkResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ShipmentLinksCard } from "./shipment-links-card";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
const mocked = vi.mocked(customInstance);

const rows: ShipmentLinkResponse[] = [
  {
    shipment_id: "s1",
    direction: "outbound",
    status: "in_transit",
    destination_org_id: "o1",
    tracking_number: "7489",
    carrier: "FedEx",
    shipping_date: "2026-09-01",
    received_date: null,
    amount_value: 5,
    amount_unit: "mg",
    created_at: "2026-08-30T12:00:00Z",
  },
  {
    shipment_id: "s2",
    direction: "inbound",
    status: "preparing",
    destination_org_id: "o1",
    tracking_number: null,
    carrier: null,
    shipping_date: null,
    received_date: null,
    amount_value: null,
    amount_unit: null,
    // Noon UTC: still Aug 20 in every local timezone the test may run in.
    created_at: "2026-08-20T12:00:00Z",
  },
];

function setup(props: Partial<Parameters<typeof ShipmentLinksCard>[0]> = {}) {
  mocked.mockReset();
  mocked.mockImplementation((opts: { url: string }) =>
    opts.url === "/api/v1/organizations"
      ? Promise.resolve([{ id: "o1", name: "WuXi" }])
      : Promise.resolve([]),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <ShipmentLinksCard title="Shipments" rows={rows} emptyText="Never shipped." {...props} />,
    { wrapper },
  );
}

describe("ShipmentLinksCard", () => {
  it("row: arrow by direction · org · status · carrier + tracking · date · amount, linking to the shipment", async () => {
    setup();
    const card = screen.getByTestId("shipment-links");
    await waitFor(() => expect(card).toHaveTextContent("→ WuXi"));
    expect(card).toHaveTextContent("In Transit");
    expect(card).toHaveTextContent("FedEx 7489");
    expect(card).toHaveTextContent("shipped Sep 1, 2026");
    expect(card).toHaveTextContent("5 mg");
    expect(card).toHaveTextContent("← WuXi");
    expect(card).toHaveTextContent("created Aug 20, 2026");
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/inventory/shipments/s1");
    expect(links[1]).toHaveAttribute("href", "/inventory/shipments/s2");
  });
  it("empty copy when there are no rows", () => {
    setup({ rows: [] });
    expect(screen.getByText("Never shipped.")).toBeInTheDocument();
  });
});
