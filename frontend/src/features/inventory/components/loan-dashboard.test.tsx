import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoanDashboard } from "./loan-dashboard";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
const mocked = vi.mocked(customInstance);

const item = (id: string, status: string) => ({
  id,
  plate_id: `p${id}`,
  barcode: id,
  plate_label: `P${id}`,
  status,
  status_changed_at: "2026-08-01T00:00:00Z",
  group_id: null,
  group_name: null,
});
const open = [
  {
    id: "l1",
    status: "open",
    owner_org_id: "A",
    borrower_org_id: "A",
    requested_by: "u1",
    due_date: "2000-01-01",
    notes: null,
    created_at: "2026-08-01T00:00:00Z",
    items: [item("1", "requested")],
  },
  {
    id: "l2",
    status: "open",
    owner_org_id: "A",
    borrower_org_id: "A",
    requested_by: "u2",
    due_date: null,
    notes: null,
    created_at: "2026-08-02T00:00:00Z",
    items: [item("2", "checked_out")],
  },
];
const me = {
  user_id: "u9",
  email: "",
  name: "",
  org_id: "A",
  is_admin: false,
  workspace_role: "editor",
};

function setup() {
  mocked.mockReset();
  window.location.hash = "";
  mocked.mockImplementation((opts: { url: string; params?: Record<string, unknown> }) => {
    if (opts.url === "/api/v1/plate-loans")
      return Promise.resolve(opts.params?.status === "closed" ? [] : open);
    if (opts.url === "/api/v1/user/me") return Promise.resolve(me);
    if (opts.url === "/api/v1/orgs") return Promise.resolve([{ id: "A", slug: "a", name: "TAMU" }]);
    if (opts.url === "/api/v1/user/workspace-members")
      return Promise.resolve([
        { user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" },
        { user_id: "u2", name: "Da Di", email: "", avatar_url: null, role: "editor" },
      ]);
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<LoanDashboard />, { wrapper });
}

describe("LoanDashboard open tab", () => {
  beforeEach(setup);
  it("renders one row per open loan, overdue first, and only non-zero chips", async () => {
    await screen.findByText("Maia Young");
    const rows = screen.getAllByTestId("loan-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Maia Young");
    expect(screen.getByRole("button", { name: /to approve\s*1/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /overdue\s*1/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /to hand out/i })).not.toBeInTheDocument();
    expect(mocked).not.toHaveBeenCalledWith(expect.objectContaining({ url: "/api/v1/comments" }));
  });
  it("a chip filters the list; clicking it again clears", async () => {
    await screen.findByText("Maia Young");
    fireEvent.click(screen.getByRole("button", { name: /to approve\s*1/i }));
    expect(screen.getAllByTestId("loan-row")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /to approve\s*1/i }));
    expect(screen.getAllByTestId("loan-row")).toHaveLength(2);
  });
  it("history fetches closed loans only when the tab is opened", async () => {
    await screen.findByText("Maia Young");
    expect(mocked).not.toHaveBeenCalledWith(
      expect.objectContaining({ params: expect.objectContaining({ status: "closed" }) }),
    );
    // Radix tabs activate on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "History" }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({ params: expect.objectContaining({ status: "closed" }) }),
      ),
    );
  });
});
