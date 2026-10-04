import { describe, expect, it } from "vitest";
import type { PlateLoan } from "../hooks/use-plate-loans";
import {
  type LoanViewer,
  availableVerbs,
  borrowerAuthority,
  eligibleItems,
  ownerAuthority,
} from "./loan-verbs";

const loan = {
  id: "l1",
  status: "open",
  owner_org_id: "org-A",
  borrower_org_id: "org-B",
  requested_by: "u1",
  items: [
    {
      id: "i1",
      plate_id: "p1",
      barcode: "1",
      plate_label: "P1",
      status: "requested",
      status_changed_at: "2026-08-01T00:00:00Z",
    },
    {
      id: "i2",
      plate_id: "p2",
      barcode: "2",
      plate_label: "P2",
      status: "checked_out",
      status_changed_at: "2026-08-01T00:00:00Z",
    },
  ],
  created_at: "2026-08-01T00:00:00Z",
  workspace_id: "w",
  version: 1,
} as unknown as PlateLoan;
const me = (org: string, admin = false, canApproveLoans = true) =>
  ({
    user_id: "u9",
    email: "",
    name: "",
    org_id: org,
    is_admin: admin,
    workspace_role: admin ? "admin" : "editor",
    canApproveLoans,
  }) as LoanViewer;
const viewer = (org: string) => ({ ...me(org), workspace_role: "viewer" }) as LoanViewer;

describe("authority", () => {
  it("owner org / admin have owner authority; borrower org / admin have borrower authority", () => {
    expect(ownerAuthority(loan, me("org-A"))).toBe(true);
    expect(ownerAuthority(loan, me("org-B"))).toBe(false);
    expect(ownerAuthority(loan, me("org-Z", true))).toBe(true);
    expect(ownerAuthority(loan, undefined)).toBe(false);
    expect(borrowerAuthority(loan, me("org-B"))).toBe(true);
    expect(borrowerAuthority(loan, me("org-A"))).toBe(false);
    expect(borrowerAuthority(loan, me("org-Z", true))).toBe(true);
  });
  it("the owner org also needs the loan-approval grant; admins don't", () => {
    expect(ownerAuthority(loan, me("org-A", false, false))).toBe(false);
    expect(ownerAuthority(loan, me("org-Z", true, false))).toBe(true);
  });
  it("viewers have no authority on either side, even in the right org", () => {
    expect(ownerAuthority(loan, viewer("org-A"))).toBe(false);
    expect(borrowerAuthority(loan, viewer("org-B"))).toBe(false);
  });
});

describe("availableVerbs", () => {
  it("owner sees approve/deny for the requested item only (no approved/return_pending items)", () => {
    expect(availableVerbs(loan, me("org-A"))).toEqual(["approve", "deny"]);
  });
  it("an owner-org editor without the grant gets no owner verbs", () => {
    expect(availableVerbs(loan, me("org-A", false, false))).toEqual([]);
  });
  it("borrower sees request-return (checked_out) and cancel (requested)", () => {
    expect(availableVerbs(loan, me("org-B"))).toEqual(["request-return", "cancel"]);
  });
  it("admin sees both arms, owner verbs first; a stranger sees none", () => {
    expect(availableVerbs(loan, me("org-Z", true))).toEqual([
      "approve",
      "deny",
      "request-return",
      "cancel",
    ]);
    expect(availableVerbs(loan, me("org-Z"))).toEqual([]);
  });
  it("eligibleItems filters by the verb's source statuses", () => {
    expect(eligibleItems(loan, "approve").map((i) => i.id)).toEqual(["i1"]);
    expect(eligibleItems(loan, "confirm-in")).toEqual([]);
  });
});
