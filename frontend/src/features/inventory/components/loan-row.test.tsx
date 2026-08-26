import { customInstance } from "@/shared/lib/api/custom-instance";
import type { MeResponse } from "@/shared/lib/api/model";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PlateLoan } from "../hooks/use-plate-loans";
import { LoanRow } from "./loan-row";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));

const loan = {
  id: "l1",
  status: "open",
  owner_org_id: "A",
  borrower_org_id: "B",
  requested_by: "u1",
  due_date: "2000-01-01",
  notes: "Migrated · requester: Xuelin Bian",
  created_at: "2026-08-01T12:00:00Z",
  items: [
    {
      id: "i1",
      plate_id: "p1",
      barcode: "1",
      plate_label: "P1",
      status: "checked_out",
      status_changed_at: "2026-08-01T00:00:00Z",
      group_id: "g1",
      group_name: "Set 5",
    },
    {
      id: "i2",
      plate_id: "p2",
      barcode: "2",
      plate_label: "P2",
      status: "return_pending",
      status_changed_at: "2026-08-01T00:00:00Z",
      group_id: "g1",
      group_name: "Set 5",
    },
  ],
} as unknown as PlateLoan;
const me = {
  user_id: "u9",
  email: "",
  name: "",
  org_id: "A",
  is_admin: false,
  workspace_role: "editor",
} as MeResponse;
const orgName = (id: string) => ({ A: "TAMU", B: "Sanofi" })[id] ?? id;

describe("LoanRow", () => {
  it("shows requester, sets, plate count, status counts, overdue due and the org line; links to the loan", () => {
    render(<LoanRow loan={loan} me={me} requesterName="Maia Young" orgName={orgName} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/inventory/loans/l1");
    expect(screen.getByText("Maia Young")).toBeInTheDocument();
    expect(screen.getByText("Set 5")).toBeInTheDocument();
    expect(screen.getByText("2 plates")).toBeInTheDocument();
    expect(screen.getByText("1 checked out")).toBeInTheDocument();
    expect(screen.getByText("1 return pending")).toBeInTheDocument();
    expect(screen.getByText(/y overdue$/)).toHaveClass("text-destructive");
    expect(screen.getByText("Lent to Sanofi")).toBeInTheDocument();
    expect(screen.getByText(/requested Aug 1, 2026/)).toBeInTheDocument();
    expect(screen.getByTitle("Migrated · requester: Xuelin Bian")).toBeInTheDocument();
  });
  it("never fetches", () => {
    render(<LoanRow loan={loan} me={me} requesterName="x" orgName={orgName} />);
    expect(vi.mocked(customInstance)).not.toHaveBeenCalled();
  });
});
