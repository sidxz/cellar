import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const customInstance = vi.fn(async (_args: unknown) => []);
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import type { MeResponse } from "@/shared/lib/api/model";
import type { PlateLoan } from "../hooks/use-plate-loans";
import { LoanCard } from "./loan-card";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const baseLoan = {
  id: "l1",
  status: "open",
  owner_org_id: "org-A",
  borrower_org_id: "org-B",
  requested_by: "u1",
  due_date: null,
  notes: null,
  items: [
    { id: "i1", plate_id: "p1", status: "requested", status_changed_at: "2026-08-13T00:00:00Z" },
  ],
  plates: {},
  created_at: "2026-08-13T00:00:00Z",
} as unknown as PlateLoan;

describe("LoanCard admin visibility (approvals tab owner verbs)", () => {
  it("shows owner verbs to a foreign-org workspace admin on the approvals tab", () => {
    render(
      <LoanCard
        loan={baseLoan}
        context="approvals"
        me={
          {
            user_id: "u9",
            email: "",
            name: "",
            org_id: "org-Z",
            is_admin: true,
            workspace_role: "admin",
          } as MeResponse
        }
      />,
      { wrapper },
    );
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
  });

  it("hides owner verbs from a foreign-org non-admin", () => {
    render(
      <LoanCard
        loan={baseLoan}
        context="approvals"
        me={
          {
            user_id: "u9",
            email: "",
            name: "",
            org_id: "org-Z",
            is_admin: false,
            workspace_role: "editor",
          } as MeResponse
        }
      />,
      { wrapper },
    );
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });

  it("shows owner verbs to an owner-org member", () => {
    render(
      <LoanCard
        loan={baseLoan}
        context="approvals"
        me={
          {
            user_id: "u9",
            email: "",
            name: "",
            org_id: "org-A",
            is_admin: false,
            workspace_role: "editor",
          } as MeResponse
        }
      />,
      { wrapper },
    );
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
  });
});

describe("LoanCard borrower request-return flow", () => {
  it("opens the RequestReturnDialog instead of posting immediately", () => {
    const loan = {
      ...baseLoan,
      items: [
        {
          id: "i1",
          plate_id: "p1",
          barcode: "BC-1",
          plate_label: "Plate 1",
          status: "checked_out",
          status_changed_at: "2026-08-13T00:00:00Z",
          group_id: "g1",
          group_name: "Vendor A",
        },
      ],
    } as unknown as PlateLoan;

    render(
      <LoanCard
        loan={loan}
        context="mine"
        me={
          {
            user_id: "u1",
            email: "",
            name: "",
            org_id: "org-B",
            is_admin: false,
            workspace_role: "editor",
          } as MeResponse
        }
      />,
      { wrapper },
    );

    fireEvent.click(screen.getByRole("button", { name: /request return \(1\)/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/vendor a \(bc-1\)/i)).toBeInTheDocument();
    expect(customInstance).not.toHaveBeenCalledWith(
      expect.objectContaining({ url: expect.stringMatching(/items:request-return$/) }),
    );
  });
});
