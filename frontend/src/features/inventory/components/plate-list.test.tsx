import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PlateList } from "./plate-list";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
// AG Grid needs a layout engine to virtualise rows; stub it so column defs and
// row data are observable without a browser.
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: (props: {
    rowData?: unknown[];
    columnDefs: { headerName?: string; hide?: boolean }[];
    selectionToolbar?: (rows: unknown[]) => ReactNode;
    emptyState?: ReactNode;
  }) => (
    <div data-testid="grid">
      <div data-testid="columns">
        {props.columnDefs
          .filter((c) => !c.hide)
          .map((c) => c.headerName)
          .join("|")}
      </div>
      <div data-testid="row-count">{props.rowData?.length ?? 0}</div>
      {props.rowData?.length === 0 ? props.emptyState : null}
      {props.selectionToolbar ? (
        <div data-testid="toolbar">{props.selectionToolbar(props.rowData ?? [])}</div>
      ) : null}
    </div>
  ),
}));
const mocked = vi.mocked(customInstance);

const plates = [
  {
    id: "p1",
    barcode: "0001",
    plate_label: "A",
    format: "384",
    plate_type: "assay",
    status: "stored",
    storage_location_id: "frz",
    owner_org_id: "A",
    group_id: "g1",
  },
  {
    id: "p2",
    barcode: "0002",
    plate_label: "B",
    format: "384",
    plate_type: "assay",
    status: "stored",
    storage_location_id: null,
    owner_org_id: "A",
    group_id: null,
  },
  {
    id: "p3",
    barcode: "0003",
    plate_label: "C",
    format: "96",
    plate_type: "assay",
    status: "depleted",
    storage_location_id: null,
    owner_org_id: "A",
    group_id: null,
  },
];
const loans = [
  {
    id: "l1",
    status: "open",
    owner_org_id: "A",
    borrower_org_id: "A",
    requested_by: "u1",
    due_date: "2000-01-01",
    created_at: "2026-08-01T00:00:00Z",
    items: [
      {
        id: "i1",
        plate_id: "p1",
        barcode: "0001",
        plate_label: "A",
        status: "checked_out",
        status_changed_at: "2026-08-01T00:00:00Z",
      },
    ],
  },
];

function setup(
  me = {
    user_id: "u9",
    email: "",
    name: "",
    org_id: "A",
    org_slug: "tamu",
    is_admin: true,
    workspace_role: "admin",
  },
) {
  mocked.mockReset();
  window.localStorage.clear();
  mocked.mockImplementation((opts: { url: string; params?: Record<string, unknown> }) => {
    if (opts.url === "/api/v1/plates") return Promise.resolve(plates);
    if (opts.url === "/api/v1/plate-loans") return Promise.resolve(loans);
    if (opts.url === "/api/v1/user/me") return Promise.resolve(me);
    if (opts.url === "/api/v1/orgs")
      return Promise.resolve([
        { id: "A", slug: "tamu", name: "TAMU" },
        { id: "B", slug: "b", name: "Sanofi" },
      ]);
    if (opts.url === "/api/v1/user/workspace-members")
      return Promise.resolve([
        { user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" },
      ]);
    if (opts.url === "/api/v1/storage-locations")
      return Promise.resolve([
        { id: "room", name: "Room 1148", parent_id: null, type: "room", workspace_id: "w" },
        { id: "frz", name: "Freezer 3", parent_id: "room", type: "freezer", workspace_id: "w" },
      ]);
    if (opts.url === "/api/v1/plate-groups/tree")
      return Promise.resolve({
        roots: [
          {
            id: "lib",
            name: "SAC1",
            plate_count: 0,
            children: [{ id: "g1", name: "Set 014", plate_count: 1, children: [] }],
          },
        ],
      });
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<PlateList />, { wrapper });
}

describe("PlateList", () => {
  beforeEach(() => setup());
  it("summary + chips reflect the loaded plates; Owner column hidden under a single org", async () => {
    await waitFor(() => expect(screen.getByTestId("row-count")).toHaveTextContent("3"));
    expect(screen.getByText("3 plates")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /on loan\s*1/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /overdue\s*1/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /depleted\s*1/i })).toBeInTheDocument();
    expect(screen.getByTestId("columns")).not.toHaveTextContent("Owner");
  });
  it("a chip filters the rows client-side", async () => {
    await waitFor(() => expect(screen.getByTestId("row-count")).toHaveTextContent("3"));
    fireEvent.click(screen.getByRole("button", { name: /depleted\s*1/i }));
    expect(screen.getByTestId("row-count")).toHaveTextContent("1");
  });
  it("the selection toolbar opens the loan dialog pre-filled with the selected barcodes", async () => {
    await waitFor(() => expect(screen.getByTestId("row-count")).toHaveTextContent("3"));
    fireEvent.click(screen.getByRole("button", { name: /request loan \(3\)/i }));
    const box = (await screen.findByLabelText("Barcodes")) as HTMLTextAreaElement;
    expect(box.value).toBe("0001\n0002\n0003");
  });
});
