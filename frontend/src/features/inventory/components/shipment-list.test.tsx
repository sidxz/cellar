import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ShipmentListPage } from "./shipment-list";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
// AG Grid needs a layout engine; stub it so column defs and row data are observable
// (verbatim from plate-list.test.tsx).
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: (props: { rowData?: unknown[]; columnDefs: { headerName?: string }[] }) => (
    <div data-testid="grid">
      <div data-testid="columns">{props.columnDefs.map((c) => c.headerName).join("|")}</div>
      <div data-testid="row-count">{props.rowData?.length ?? 0}</div>
    </div>
  ),
}));
const mocked = vi.mocked(customInstance);

function setup() {
  mocked.mockReset();
  mocked.mockImplementation((opts: { url: string }) =>
    opts.url === "/api/v1/shipments"
      ? Promise.resolve([
          {
            id: "s1",
            workspace_id: "w",
            destination_org_id: "o1",
            direction: "inbound",
            loan_id: null,
            tracking_number: null,
            carrier: null,
            status: "preparing",
            item_count: 3,
          },
        ])
      : Promise.resolve([]),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<ShipmentListPage />, { wrapper });
}

describe("ShipmentListPage", () => {
  it("grid carries Direction and Items columns and one row per shipment", async () => {
    setup();
    expect(screen.getByTestId("columns")).toHaveTextContent("Direction");
    expect(screen.getByTestId("columns")).toHaveTextContent("Items");
    await waitFor(() => expect(screen.getByTestId("row-count")).toHaveTextContent("1"));
  });
});
