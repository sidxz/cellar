import type { MeResponse } from "@/shared/lib/api/model";
import { describe, expect, it } from "vitest";
import type { PlateLoan } from "../hooks/use-plate-loans";
import {
  inboxCounts,
  isOverdue,
  itemStatusCounts,
  loanInboxKeys,
  loanOutcome,
  loanSets,
  loanTitle,
  orgLine,
  setSummary,
  sortOpenLoans,
} from "./loan-summary";

const item = (id: string, status: string, group?: [string, string]) => ({
  id,
  plate_id: `p-${id}`,
  barcode: id,
  plate_label: `P${id}`,
  status,
  status_changed_at: "2026-08-01T00:00:00Z",
  group_id: group?.[0] ?? null,
  group_name: group?.[1] ?? null,
});
const mk = (over: Partial<Omit<PlateLoan, "items">> & { items: unknown[] }) =>
  ({
    id: "l",
    status: "open",
    owner_org_id: "A",
    borrower_org_id: "A",
    requested_by: "u1",
    due_date: null,
    created_at: "2026-08-01T00:00:00Z",
    closed_at: null,
    notes: null,
    workspace_id: "w",
    version: 1,
    ...over,
  }) as unknown as PlateLoan;
const me = (org: string, admin = false, user = "u9") =>
  ({
    user_id: user,
    email: "",
    name: "",
    org_id: org,
    is_admin: admin,
    workspace_role: "editor",
  }) as MeResponse;
const TODAY = "2026-08-25";

describe("sets", () => {
  const loan = mk({
    items: [
      item("1", "checked_out", ["g1", "Set 5"]),
      item("2", "checked_out", ["g1", "Set 5"]),
      item("3", "checked_out", ["g2", "Set 27"]),
      item("4", "checked_out", ["g3", "Set 40"]),
      item("5", "checked_out"),
    ],
  });
  it("loanSets: distinct first-seen, ungrouped last", () => {
    expect(loanSets(loan)).toEqual([
      { id: "g1", name: "Set 5", count: 2 },
      { id: "g2", name: "Set 27", count: 1 },
      { id: "g3", name: "Set 40", count: 1 },
      { id: null, name: "Ungrouped", count: 1 },
    ]);
  });
  it("setSummary: two names then +n; empty when nothing is grouped", () => {
    expect(setSummary(loan)).toBe("Set 5, Set 27 +1");
    expect(setSummary(mk({ items: [item("1", "requested")] }))).toBe("");
  });
  it("loanTitle", () => {
    expect(loanTitle(loan, "Maia Young")).toBe("Maia Young · Set 5, Set 27 +1");
    expect(loanTitle(mk({ items: [item("1", "requested")] }), "")).toBe("1 plate");
  });
});

describe("status counts / overdue / outcome", () => {
  it("itemStatusCounts in pipeline order, non-zero only", () => {
    const loan = mk({
      items: [item("1", "return_pending"), item("2", "checked_out"), item("3", "checked_out")],
    });
    expect(itemStatusCounts(loan)).toEqual([
      { status: "checked_out", count: 2 },
      { status: "return_pending", count: 1 },
    ]);
  });
  it("isOverdue only for open loans with a past due date", () => {
    expect(isOverdue(mk({ items: [], due_date: "2026-08-24" }), TODAY)).toBe(true);
    expect(isOverdue(mk({ items: [], due_date: "2026-08-25" }), TODAY)).toBe(false);
    expect(
      isOverdue(mk({ items: [], due_date: "2026-08-24", status: "closed" } as never), TODAY),
    ).toBe(false);
    expect(isOverdue(mk({ items: [] }), TODAY)).toBe(false);
  });
  it("loanOutcome precedence", () => {
    expect(loanOutcome(mk({ items: [item("1", "requested")] }))).toBe("open");
    expect(
      loanOutcome(
        mk({ status: "closed", items: [item("1", "returned"), item("2", "denied")] } as never),
      ),
    ).toBe("returned");
    expect(
      loanOutcome(
        mk({ status: "closed", items: [item("1", "denied"), item("2", "cancelled")] } as never),
      ),
    ).toBe("denied");
    expect(loanOutcome(mk({ status: "closed", items: [item("1", "cancelled")] } as never))).toBe(
      "cancelled",
    );
  });
});

describe("inbox", () => {
  const loan = mk({
    owner_org_id: "A",
    borrower_org_id: "B",
    requested_by: "u1",
    due_date: "2026-08-01",
    items: [item("1", "requested"), item("2", "approved"), item("3", "return_pending")],
  });
  it("owner side keys, never the borrower-side duplicates", () => {
    expect([...loanInboxKeys(loan, me("A"), TODAY)].sort()).toEqual([
      "approve",
      "check_in",
      "hand_out",
      "overdue",
    ]);
  });
  it("borrower side keys + mine for the requester", () => {
    expect([...loanInboxKeys(loan, me("B", false, "u1"), TODAY)].sort()).toEqual([
      "awaiting_approval",
      "mine",
      "overdue",
      "ready_for_pickup",
    ]);
  });
  it("inboxCounts counts loans per key", () => {
    const other = mk({
      id: "l2",
      owner_org_id: "A",
      borrower_org_id: "B",
      items: [item("9", "checked_out")],
    });
    const counts = inboxCounts([loan, other], me("A"), TODAY);
    expect(counts).toEqual({
      approve: 1,
      hand_out: 1,
      check_in: 1,
      awaiting_approval: 0,
      ready_for_pickup: 0,
      overdue: 1,
      mine: 0,
    });
  });
});

describe("orgLine / sortOpenLoans", () => {
  const name = (id: string) => ({ A: "TAMU", B: "Sanofi" })[id] ?? id;
  it("nothing for self-checkout; Lent to / Borrowed from / A → B by viewpoint", () => {
    expect(orgLine(mk({ items: [] }), me("A"), name)).toBeNull();
    const cross = mk({ owner_org_id: "A", borrower_org_id: "B", items: [] });
    expect(orgLine(cross, me("A"), name)).toBe("Lent to Sanofi");
    expect(orgLine(cross, me("B"), name)).toBe("Borrowed from TAMU");
    expect(orgLine(cross, me("Z", true), name)).toBe("Sanofi → TAMU");
  });
  it("sorts by due date ascending, no due date last, then newest first", () => {
    const a = mk({ id: "a", due_date: "2026-09-01", items: [] });
    const b = mk({ id: "b", due_date: "2026-08-01", items: [] });
    const c = mk({ id: "c", created_at: "2026-08-10T00:00:00Z", items: [] });
    const d = mk({ id: "d", created_at: "2026-08-20T00:00:00Z", items: [] });
    expect(sortOpenLoans([a, c, b, d]).map((l) => l.id)).toEqual(["b", "a", "d", "c"]);
  });
});
