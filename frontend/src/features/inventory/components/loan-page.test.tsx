import { customInstance } from "@/shared/lib/api/custom-instance";
import type { MeResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { LoanPage } from "./loan-page";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/inventory/loans/l1",
}));
const mocked = vi.mocked(customInstance);

const loan = {
  id: "l1",
  status: "open",
  owner_org_id: "org-A",
  borrower_org_id: "org-B",
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
      status: "requested",
      status_changed_at: "2026-08-13T00:00:00Z",
      group_id: "g1",
      group_name: "Set 5",
    },
    {
      id: "i2",
      plate_id: "p2",
      barcode: "0002",
      plate_label: "P2",
      status: "checked_out",
      status_changed_at: "2026-08-14T00:00:00Z",
      group_id: "g2",
      group_name: "Set 27",
    },
  ],
};
const me = (org: string, admin = false): MeResponse =>
  ({
    user_id: "u9",
    email: "",
    name: "",
    org_id: org,
    is_admin: admin,
    workspace_role: admin ? "admin" : "editor",
  }) as MeResponse;

function setup(viewer: MeResponse) {
  mocked.mockReset();
  mocked.mockImplementation((opts: { url: string; method: string }) => {
    if (opts.url === "/api/v1/plate-loans/l1") return Promise.resolve(loan);
    if (opts.url === "/api/v1/user/me") return Promise.resolve(viewer);
    if (opts.url === "/api/v1/orgs")
      return Promise.resolve([
        { id: "org-A", slug: "a", name: "TAMU" },
        { id: "org-B", slug: "b", name: "Sanofi" },
      ]);
    if (opts.url === "/api/v1/user/workspace-members")
      return Promise.resolve([
        { user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" },
      ]);
    if (opts.url === "/api/v1/comments") return Promise.resolve([]);
    return Promise.resolve(loan); // verb POSTs
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<LoanPage loanId="l1" />, { wrapper });
}

describe("LoanPage verbs by authority", () => {
  it("owner-org member sees approve/deny (requested item) and no borrower verbs", async () => {
    setup(me("org-A"));
    expect(await screen.findByRole("button", { name: /approve \(1\)/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /deny \(1\)/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /request return/i })).not.toBeInTheDocument();
  });
  it("foreign-org workspace admin sees owner verbs", async () => {
    setup(me("org-Z", true));
    expect(await screen.findByRole("button", { name: /approve \(1\)/i })).toBeInTheDocument();
  });
  it("foreign-org non-admin sees no verbs and no checkboxes", async () => {
    setup(me("org-Z"));
    await screen.findByText("0001");
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
  it("borrower-org member sees request-return and cancel", async () => {
    setup(me("org-B"));
    expect(
      await screen.findByRole("button", { name: /request return \(1\)/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel \(1\)/i })).toBeInTheDocument();
  });
});

describe("LoanPage content", () => {
  it("title carries requester and sets; items are grouped under set subheaders; org line shown", async () => {
    setup(me("org-A"));
    expect(await screen.findByText("Maia Young · Set 5, Set 27")).toBeInTheDocument();
    expect(screen.getByText("Set 5 · 1 plate")).toBeInTheDocument();
    expect(screen.getByText("Set 27 · 1 plate")).toBeInTheDocument();
    expect(screen.getByText("Lent to Sanofi")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "0001" })).toHaveAttribute(
      "href",
      "/inventory/plates/p1",
    );
  });
  it("request-return opens the dialog instead of posting immediately", async () => {
    setup(me("org-B"));
    fireEvent.click(await screen.findByRole("button", { name: /request return \(1\)/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(mocked).not.toHaveBeenCalledWith(
      expect.objectContaining({ url: expect.stringContaining("items:request-return") }),
    );
  });
  it("approve posts the eligible item ids", async () => {
    setup(me("org-A"));
    fireEvent.click(await screen.findByRole("button", { name: /approve \(1\)/i }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/plate-loans/l1/items:approve",
          method: "POST",
          data: { item_ids: ["i1"] },
        }),
      ),
    );
  });
});
