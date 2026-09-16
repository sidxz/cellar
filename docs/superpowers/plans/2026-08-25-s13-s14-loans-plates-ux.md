# Loans & Plates UX Pass (S13–S14) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Loans and Plates pages from a ledger into a work queue — inbox chips, compact loan rows, a loan page, a closed-loan grid, a "which set / where / who has it" plate list and a custody-first plate page.

**Architecture:** Frontend only. Pure helpers (`format-date`, `loan-verbs`, `loan-summary`, `storage-path`, `plate-where`) carry the logic and are unit-tested; components render them. Names resolve client-side (`useMemberNames`, `useGroupIndex`, `useStorageLocations`) over the unpaginated lists that already exist. No backend change.

**Tech Stack:** Next.js 16 / React 19 / TypeScript, TanStack Query v5, shadcn/ui, AG Grid Community (`DataGrid`), vitest + Testing Library, biome.

**Spec:** `docs/superpowers/specs/2026-08-25-loans-plates-ux-pass-spec.md`

## Global Constraints

- Run everything from `frontend/`: tests `pnpm vitest run <path>`, types `pnpm exec tsc --noEmit`, lint `pnpm exec biome check <touched files>` (repo-wide lint is red on main — scope to touched files, judge by exit code).
- Generated API types come from `@/shared/lib/api/model`; never hand-roll a DTO shape. `PlateLoan = LoanResponse`, `PlateLoanItem = LoanItemResponse`, `RegisteredPlate = PlateResponse`, `StorageLocation = StorageLocationResponse`.
- Test mocking convention (copy verbatim): `vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }))`, `vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }))`; wrap renders in a fresh `QueryClientProvider` with `retry: false`. Pages that use `DetailShell`/`useRouter` also mock `next/navigation` (`useRouter: () => ({ push: vi.fn(), replace: vi.fn() })`, `usePathname: () => "..."`).
- Colour only exceptions (spec X2): overdue = `text-destructive`, on loan = `text-warning`, depleted/disposed = `text-muted-foreground`, normal = plain.
- **Do not commit from subagents.** The orchestrator commits with explicit pathspecs (S13 files, then S14 files).
- Delete `loan-card.tsx` and `loan-card.test.tsx` in Task 5 (its behaviour is ported to the loan page).

## File map

| File | Responsibility |
|---|---|
| `shared/lib/format-date.ts` (+test) | `formatDue` |
| `shared/hooks/use-workspace-members.ts` (+test) | `useMemberNames` |
| `features/inventory/lib/loan-verbs.ts` (+test) | verb tables, authority, eligibility (moved out of loan-card) |
| `features/inventory/lib/loan-summary.ts` (+test) | sets, status counts, overdue, outcome, inbox keys/counts, org line, title, sort |
| `features/inventory/components/count-chips.tsx` | toggle chips with counts (loans + plates) |
| `features/inventory/components/loan-row.tsx` (+test) | compact open-loan row |
| `features/inventory/components/loan-page.tsx` (+test), `app/(dashboard)/inventory/loans/[id]/page.tsx` | loan page |
| `features/inventory/components/loan-dashboard.tsx` (+test) | Open (chips + rows) · History (grid) |
| `features/inventory/components/request-loan-dialog.tsx` (+test) | `initialBarcodes`, navigate on success |
| `features/inventory/components/comment-feed.tsx` (+test) | link to the loan page |
| `features/inventory/lib/storage-path.ts` (+test) | location chain → path |
| `features/inventory/lib/plate-where.ts` (+test) | whereabouts precedence, Where text, plate chips |
| `features/inventory/hooks/use-plate-groups.ts` | `useGroupIndex` |
| `features/inventory/components/plate-list.tsx` (+test) | list rewrite |
| `features/inventory/components/plate-detail.tsx` (+test) | page rewrite |

Dependency waves (files never overlap inside a wave): **W1** T1 T2 T3 T7 T8 · **W2** T4 T5 T10 · **W3** T6 T9.

---

### Task 1: `formatDue`

**Files:**
- Modify: `frontend/src/shared/lib/format-date.ts` (append)
- Test: `frontend/src/shared/lib/format-date.test.ts` (append a `describe`)

**Interfaces:**
- Produces: `formatDue(input: string | Date | null | undefined, now?: Date): { label: string; overdue: boolean } | null`

- [ ] **Step 1: Write the failing tests** — append to `format-date.test.ts`:

```ts
import { formatDue } from "./format-date";

describe("formatDue", () => {
  const now = new Date(2026, 7, 25, 12, 0, 0); // Aug 25 2026, local noon
  const due = (iso: string) => formatDue(iso, now);

  it("returns null for no date", () => {
    expect(formatDue(null, now)).toBeNull();
    expect(formatDue(undefined, now)).toBeNull();
  });
  it("today / tomorrow", () => {
    expect(due("2026-08-25")).toEqual({ label: "due today", overdue: false });
    expect(due("2026-08-26")).toEqual({ label: "due tomorrow", overdue: false });
  });
  it("days until 13, weeks from 14, calendar from 60", () => {
    expect(due("2026-09-07")?.label).toBe("due in 13 d");
    expect(due("2026-09-08")?.label).toBe("due in 2 w");
    expect(due("2026-10-23")?.label).toBe("due in 8 w");
    expect(due("2026-10-24")?.label).toMatch(/^due Oct 24$/);
    expect(due("2027-03-01")?.label).toMatch(/^due Mar 1, 2027$/);
  });
  it("overdue buckets: days, weeks, months, years", () => {
    expect(due("2026-08-24")).toEqual({ label: "1 d overdue", overdue: true });
    expect(due("2026-08-12")?.label).toBe("13 d overdue");
    expect(due("2026-08-11")?.label).toBe("2 w overdue");
    expect(due("2026-06-27")?.label).toBe("8 w overdue");
    expect(due("2026-06-26")?.label).toBe("2 mo overdue");
    expect(due("2025-03-13")?.label).toBe("17 mo overdue");
    expect(due("2024-08-25")?.label).toBe("2 y overdue");
  });
});
```

- [ ] **Step 2: Run** `pnpm vitest run src/shared/lib/format-date.test.ts` — expect FAIL (`formatDue` is not exported).

- [ ] **Step 3: Implement** — append to `format-date.ts`:

```ts
/**
 * Day-granular due phrase for a date-only value (local calendar days):
 *   today → "due today" · +1 → "due tomorrow" · 2..13 → "due in N d" ·
 *   14..59 → "due in N w" · ≥60 → "due Sep 30" (year when not current) ·
 *   −1..−13 → "N d overdue" · −14..−59 → "N w overdue" ·
 *   −60..−729 → "N mo overdue" (30-day months) · ≤−730 → "N y overdue".
 * `now` is injectable for tests.
 */
export function formatDue(
  input: string | Date | null | undefined,
  now: Date = new Date(),
): { label: string; overdue: boolean } | null {
  const d = toDate(input);
  if (!d) return null;
  const due = new Date(d);
  due.setHours(0, 0, 0, 0);
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  // round, not floor: a DST change between the two midnights is ±1 h
  const delta = Math.round((due.getTime() - today.getTime()) / 86_400_000);
  if (delta === 0) return { label: "due today", overdue: false };
  if (delta === 1) return { label: "due tomorrow", overdue: false };
  if (delta > 1 && delta < 14) return { label: `due in ${delta} d`, overdue: false };
  if (delta >= 14 && delta < 60) return { label: `due in ${Math.floor(delta / 7)} w`, overdue: false };
  if (delta >= 60) {
    const sameYear = due.getFullYear() === today.getFullYear();
    const text = due.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: sameYear ? undefined : "numeric",
    });
    return { label: `due ${text}`, overdue: false };
  }
  const late = -delta;
  const label =
    late < 14
      ? `${late} d overdue`
      : late < 60
        ? `${Math.floor(late / 7)} w overdue`
        : late < 730
          ? `${Math.floor(late / 30)} mo overdue`
          : `${Math.floor(late / 365)} y overdue`;
  return { label, overdue: true };
}
```

- [ ] **Step 4: Run** the same test file — expect PASS. Then `pnpm exec biome check src/shared/lib/format-date.ts src/shared/lib/format-date.test.ts`.

---

### Task 2: `useMemberNames`

**Files:**
- Modify: `frontend/src/shared/hooks/use-workspace-members.ts` (append)
- Test: create `frontend/src/shared/hooks/use-workspace-members.test.tsx`

**Interfaces:**
- Produces: `useMemberNames(): (userId: string | null | undefined) => string` — `""` for null/undefined, the member's name when known, `"…"` while the list is loading, `"Unknown member"` once loaded and absent.

- [ ] **Step 1: Write the failing test:**

```tsx
import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useMemberNames } from "./use-workspace-members";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
const mocked = vi.mocked(customInstance);

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useMemberNames", () => {
  it("resolves ids to names over the full member list, with fallbacks", async () => {
    mocked.mockResolvedValue([
      { user_id: "u1", name: "Maia Young", email: "m@x", avatar_url: null, role: "editor" },
    ]);
    const { result } = renderHook(() => useMemberNames(), { wrapper });
    expect(result.current("u1")).toBe("…"); // still loading
    await waitFor(() => expect(result.current("u1")).toBe("Maia Young"));
    expect(result.current("nope")).toBe("Unknown member");
    expect(result.current(null)).toBe("");
    expect(result.current(undefined)).toBe("");
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({ url: "/api/v1/user/workspace-members", params: undefined }),
    );
  });
});
```

- [ ] **Step 2: Run** `pnpm vitest run src/shared/hooks/use-workspace-members.test.tsx` — expect FAIL.

- [ ] **Step 3: Implement** — append to `use-workspace-members.ts` (add `import { useCallback, useMemo } from "react";`):

```ts
/** user_id → display name over the full member list. "" for null, "…" while
 * loading, "Unknown member" when the list is loaded but has no such id. */
export function useMemberNames(): (userId: string | null | undefined) => string {
  const { data } = useWorkspaceMembers();
  const byId = useMemo(() => new Map((data ?? []).map((m) => [m.user_id, m.name])), [data]);
  return useCallback(
    (userId) => {
      if (!userId) return "";
      if (!data) return "…";
      return byId.get(userId) ?? "Unknown member";
    },
    [byId, data],
  );
}
```

- [ ] **Step 4: Run** the test — PASS; biome the two files.

---

### Task 3: `loan-verbs.ts` + `loan-summary.ts`

**Files:**
- Create: `frontend/src/features/inventory/lib/loan-verbs.ts`, `frontend/src/features/inventory/lib/loan-summary.ts`
- Test: `frontend/src/features/inventory/lib/loan-verbs.test.ts`, `frontend/src/features/inventory/lib/loan-summary.test.ts`
- Do NOT touch `loan-card.tsx` yet (Task 5 deletes it).

**Interfaces (Produces):**
```ts
// loan-verbs.ts
export const VERB_SOURCES: Record<LoanVerb, LoanItemStatus[]>; export const VERB_LABELS: Record<LoanVerb, string>;
export const OWNER_VERBS: LoanVerb[]; export const BORROWER_VERBS: LoanVerb[];
export function ownerAuthority(loan: PlateLoan, me: MeResponse | undefined): boolean
export function borrowerAuthority(loan: PlateLoan, me: MeResponse | undefined): boolean
export function eligibleItems(loan: PlateLoan, verb: LoanVerb): PlateLoanItem[]
export function availableVerbs(loan: PlateLoan, me: MeResponse | undefined): LoanVerb[]
// loan-summary.ts
export interface LoanSet { id: string | null; name: string; count: number }
export function loanSets(loan: PlateLoan): LoanSet[]
export function setSummary(loan: PlateLoan): string
export const ITEM_STATUS_ORDER: LoanItemStatus[]
export function itemStatusCounts(loan: PlateLoan): { status: LoanItemStatus; count: number }[]
export function todayISO(): string
export function isOverdue(loan: PlateLoan, today?: string): boolean
export type LoanOutcome = "open" | "returned" | "denied" | "cancelled"
export function loanOutcome(loan: PlateLoan): LoanOutcome
export type InboxKey = "approve" | "hand_out" | "check_in" | "awaiting_approval" | "ready_for_pickup" | "overdue" | "mine"
export const INBOX_ORDER: InboxKey[]; export const INBOX_LABELS: Record<InboxKey, string>
export function loanInboxKeys(loan: PlateLoan, me: MeResponse | undefined, today?: string): Set<InboxKey>
export function inboxCounts(loans: PlateLoan[], me: MeResponse | undefined, today?: string): Record<InboxKey, number>
export function orgLine(loan: PlateLoan, me: MeResponse | undefined, orgName: (id: string) => string): string | null
export function loanTitle(loan: PlateLoan, requesterName: string): string
export function sortOpenLoans(loans: PlateLoan[]): PlateLoan[]
```

- [ ] **Step 1: Write `loan-verbs.test.ts`:**

```ts
import type { MeResponse } from "@/shared/lib/api/model";
import { describe, expect, it } from "vitest";
import type { PlateLoan } from "../hooks/use-plate-loans";
import { availableVerbs, borrowerAuthority, eligibleItems, ownerAuthority } from "./loan-verbs";

const loan = {
  id: "l1", status: "open", owner_org_id: "org-A", borrower_org_id: "org-B", requested_by: "u1",
  items: [
    { id: "i1", plate_id: "p1", barcode: "1", plate_label: "P1", status: "requested", status_changed_at: "2026-08-01T00:00:00Z" },
    { id: "i2", plate_id: "p2", barcode: "2", plate_label: "P2", status: "checked_out", status_changed_at: "2026-08-01T00:00:00Z" },
  ],
  created_at: "2026-08-01T00:00:00Z", workspace_id: "w", version: 1,
} as unknown as PlateLoan;
const me = (org: string, admin = false) =>
  ({ user_id: "u9", email: "", name: "", org_id: org, is_admin: admin, workspace_role: admin ? "admin" : "editor" }) as MeResponse;

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
});

describe("availableVerbs", () => {
  it("owner sees approve/deny for the requested item only (no approved/return_pending items)", () => {
    expect(availableVerbs(loan, me("org-A"))).toEqual(["approve", "deny"]);
  });
  it("borrower sees request-return (checked_out) and cancel (requested)", () => {
    expect(availableVerbs(loan, me("org-B"))).toEqual(["request-return", "cancel"]);
  });
  it("admin sees both arms, owner verbs first; a stranger sees none", () => {
    expect(availableVerbs(loan, me("org-Z", true))).toEqual(["approve", "deny", "request-return", "cancel"]);
    expect(availableVerbs(loan, me("org-Z"))).toEqual([]);
  });
  it("eligibleItems filters by the verb's source statuses", () => {
    expect(eligibleItems(loan, "approve").map((i) => i.id)).toEqual(["i1"]);
    expect(eligibleItems(loan, "confirm-in")).toEqual([]);
  });
});
```

- [ ] **Step 2: Write `loan-summary.test.ts`:**

```ts
import type { MeResponse } from "@/shared/lib/api/model";
import { describe, expect, it } from "vitest";
import type { PlateLoan } from "../hooks/use-plate-loans";
import {
  inboxCounts, isOverdue, itemStatusCounts, loanInboxKeys, loanOutcome, loanSets, loanTitle, orgLine,
  setSummary, sortOpenLoans,
} from "./loan-summary";

const item = (id: string, status: string, group?: [string, string]) => ({
  id, plate_id: `p-${id}`, barcode: id, plate_label: `P${id}`, status, status_changed_at: "2026-08-01T00:00:00Z",
  group_id: group?.[0] ?? null, group_name: group?.[1] ?? null,
});
const mk = (over: Partial<PlateLoan> & { items: unknown[] }) =>
  ({ id: "l", status: "open", owner_org_id: "A", borrower_org_id: "A", requested_by: "u1", due_date: null,
     created_at: "2026-08-01T00:00:00Z", closed_at: null, notes: null, workspace_id: "w", version: 1, ...over }) as unknown as PlateLoan;
const me = (org: string, admin = false, user = "u9") =>
  ({ user_id: user, email: "", name: "", org_id: org, is_admin: admin, workspace_role: "editor" }) as MeResponse;
const TODAY = "2026-08-25";

describe("sets", () => {
  const loan = mk({ items: [item("1", "checked_out", ["g1", "Set 5"]), item("2", "checked_out", ["g1", "Set 5"]),
    item("3", "checked_out", ["g2", "Set 27"]), item("4", "checked_out", ["g3", "Set 40"]), item("5", "checked_out")] });
  it("loanSets: distinct first-seen, ungrouped last", () => {
    expect(loanSets(loan)).toEqual([
      { id: "g1", name: "Set 5", count: 2 }, { id: "g2", name: "Set 27", count: 1 },
      { id: "g3", name: "Set 40", count: 1 }, { id: null, name: "Ungrouped", count: 1 },
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
    const loan = mk({ items: [item("1", "return_pending"), item("2", "checked_out"), item("3", "checked_out")] });
    expect(itemStatusCounts(loan)).toEqual([{ status: "checked_out", count: 2 }, { status: "return_pending", count: 1 }]);
  });
  it("isOverdue only for open loans with a past due date", () => {
    expect(isOverdue(mk({ items: [], due_date: "2026-08-24" }), TODAY)).toBe(true);
    expect(isOverdue(mk({ items: [], due_date: "2026-08-25" }), TODAY)).toBe(false);
    expect(isOverdue(mk({ items: [], due_date: "2026-08-24", status: "closed" } as never), TODAY)).toBe(false);
    expect(isOverdue(mk({ items: [] }), TODAY)).toBe(false);
  });
  it("loanOutcome precedence", () => {
    expect(loanOutcome(mk({ items: [item("1", "requested")] }))).toBe("open");
    expect(loanOutcome(mk({ status: "closed", items: [item("1", "returned"), item("2", "denied")] } as never))).toBe("returned");
    expect(loanOutcome(mk({ status: "closed", items: [item("1", "denied"), item("2", "cancelled")] } as never))).toBe("denied");
    expect(loanOutcome(mk({ status: "closed", items: [item("1", "cancelled")] } as never))).toBe("cancelled");
  });
});

describe("inbox", () => {
  const loan = mk({ owner_org_id: "A", borrower_org_id: "B", requested_by: "u1", due_date: "2026-08-01",
    items: [item("1", "requested"), item("2", "approved"), item("3", "return_pending")] });
  it("owner side keys, never the borrower-side duplicates", () => {
    expect([...loanInboxKeys(loan, me("A"), TODAY)].sort()).toEqual(["approve", "check_in", "hand_out", "overdue"]);
  });
  it("borrower side keys + mine for the requester", () => {
    expect([...loanInboxKeys(loan, me("B", false, "u1"), TODAY)].sort()).toEqual(["awaiting_approval", "mine", "overdue", "ready_for_pickup"]);
  });
  it("inboxCounts counts loans per key", () => {
    const other = mk({ id: "l2", owner_org_id: "A", borrower_org_id: "B", items: [item("9", "checked_out")] });
    const counts = inboxCounts([loan, other], me("A"), TODAY);
    expect(counts).toEqual({ approve: 1, hand_out: 1, check_in: 1, awaiting_approval: 0, ready_for_pickup: 0, overdue: 1, mine: 0 });
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
```

- [ ] **Step 3: Run** both test files — expect FAIL (modules missing).

- [ ] **Step 4: Implement `loan-verbs.ts`:**

```ts
import type { MeResponse } from "@/shared/lib/api/model";
import { LoanItemStatus, type LoanVerb, type PlateLoan, type PlateLoanItem } from "../hooks/use-plate-loans";

/** Item statuses each verb may act on — the single source of truth for which
 * items are "eligible" for a verb, mirrored from the server state machine. */
export const VERB_SOURCES: Record<LoanVerb, LoanItemStatus[]> = {
  approve: [LoanItemStatus.requested],
  deny: [LoanItemStatus.requested],
  "confirm-out": [LoanItemStatus.approved],
  "request-return": [LoanItemStatus.checked_out],
  "confirm-in": [LoanItemStatus.return_pending],
  cancel: [LoanItemStatus.requested, LoanItemStatus.approved],
};

export const VERB_LABELS: Record<LoanVerb, string> = {
  approve: "Approve",
  deny: "Deny",
  "confirm-out": "Confirm hand-out",
  "request-return": "Request return",
  "confirm-in": "Confirm return",
  cancel: "Cancel",
};

export const OWNER_VERBS: LoanVerb[] = ["approve", "deny", "confirm-out", "confirm-in"];
export const BORROWER_VERBS: LoanVerb[] = ["request-return", "cancel"];

/** Mirrors the server: workspace admins and the owner org. */
export function ownerAuthority(loan: PlateLoan, me: MeResponse | undefined): boolean {
  return !!me && (me.is_admin === true || me.org_id === loan.owner_org_id);
}

/** Mirrors `_require_borrower_authority`: workspace admins and the borrower org. */
export function borrowerAuthority(loan: PlateLoan, me: MeResponse | undefined): boolean {
  return !!me && (me.is_admin === true || me.org_id === loan.borrower_org_id);
}

export function eligibleItems(loan: PlateLoan, verb: LoanVerb): PlateLoanItem[] {
  return loan.items.filter((i) => VERB_SOURCES[verb].includes(i.status));
}

/** Verbs the viewer may press that have ≥ 1 eligible item, owner verbs first. */
export function availableVerbs(loan: PlateLoan, me: MeResponse | undefined): LoanVerb[] {
  const verbs = [
    ...(ownerAuthority(loan, me) ? OWNER_VERBS : []),
    ...(borrowerAuthority(loan, me) ? BORROWER_VERBS : []),
  ];
  return verbs.filter((v) => eligibleItems(loan, v).length > 0);
}
```

- [ ] **Step 5: Implement `loan-summary.ts`:**

```ts
import type { MeResponse } from "@/shared/lib/api/model";
import { LoanItemStatus, LoanStatus, type PlateLoan } from "../hooks/use-plate-loans";
import { ownerAuthority } from "./loan-verbs";

export interface LoanSet {
  /** null = items with no group. */
  id: string | null;
  name: string;
  count: number;
}

/** Distinct sets among the items, first-seen order; ungrouped items last. */
export function loanSets(loan: PlateLoan): LoanSet[] {
  const byId = new Map<string, LoanSet>();
  let ungrouped = 0;
  for (const item of loan.items) {
    if (!item.group_id) {
      ungrouped += 1;
      continue;
    }
    const existing = byId.get(item.group_id);
    if (existing) existing.count += 1;
    else byId.set(item.group_id, { id: item.group_id, name: item.group_name ?? "Ungrouped", count: 1 });
  }
  const sets = [...byId.values()];
  if (ungrouped > 0) sets.push({ id: null, name: "Ungrouped", count: ungrouped });
  return sets;
}

/** "Set 5, Set 27 +1" — first two grouped set names, then a +n. "" when no item is grouped. */
export function setSummary(loan: PlateLoan): string {
  const names = loanSets(loan).filter((s) => s.id !== null).map((s) => s.name);
  if (names.length === 0) return "";
  const head = names.slice(0, 2).join(", ");
  return names.length > 2 ? `${head} +${names.length - 2}` : head;
}

export const ITEM_STATUS_ORDER: LoanItemStatus[] = [
  LoanItemStatus.requested, LoanItemStatus.approved, LoanItemStatus.checked_out,
  LoanItemStatus.return_pending, LoanItemStatus.returned, LoanItemStatus.denied, LoanItemStatus.cancelled,
];

export function itemStatusCounts(loan: PlateLoan): { status: LoanItemStatus; count: number }[] {
  return ITEM_STATUS_ORDER.map((status) => ({
    status,
    count: loan.items.filter((i) => i.status === status).length,
  })).filter((c) => c.count > 0);
}

/** Local calendar day — past-due must match the date inputs users typed. */
export function todayISO(): string {
  return new Date().toLocaleDateString("en-CA");
}

export function isOverdue(loan: PlateLoan, today: string = todayISO()): boolean {
  return loan.status === LoanStatus.open && !!loan.due_date && loan.due_date < today;
}

export type LoanOutcome = "open" | "returned" | "denied" | "cancelled";

/** closed: any returned → returned; else any denied → denied; else cancelled. */
export function loanOutcome(loan: PlateLoan): LoanOutcome {
  if (loan.status === LoanStatus.open) return "open";
  const statuses = new Set(loan.items.map((i) => i.status));
  if (statuses.has(LoanItemStatus.returned)) return "returned";
  if (statuses.has(LoanItemStatus.denied)) return "denied";
  return "cancelled";
}

export type InboxKey =
  | "approve" | "hand_out" | "check_in" | "awaiting_approval" | "ready_for_pickup" | "overdue" | "mine";

export const INBOX_ORDER: InboxKey[] = [
  "approve", "hand_out", "check_in", "awaiting_approval", "ready_for_pickup", "overdue", "mine",
];

export const INBOX_LABELS: Record<InboxKey, string> = {
  approve: "To approve",
  hand_out: "To hand out",
  check_in: "To check in",
  awaiting_approval: "Awaiting approval",
  ready_for_pickup: "Ready for pickup",
  overdue: "Overdue",
  mine: "Requested by me",
};

/** Which inbox chips this loan belongs to for this viewer. Owner-side keys
 * when the viewer can approve (so a self-checkout never shows both sides). */
export function loanInboxKeys(loan: PlateLoan, me: MeResponse | undefined, today: string = todayISO()): Set<InboxKey> {
  const keys = new Set<InboxKey>();
  const statuses = new Set(loan.items.map((i) => i.status));
  if (ownerAuthority(loan, me)) {
    if (statuses.has(LoanItemStatus.requested)) keys.add("approve");
    if (statuses.has(LoanItemStatus.approved)) keys.add("hand_out");
    if (statuses.has(LoanItemStatus.return_pending)) keys.add("check_in");
  } else {
    if (statuses.has(LoanItemStatus.requested)) keys.add("awaiting_approval");
    if (statuses.has(LoanItemStatus.approved)) keys.add("ready_for_pickup");
  }
  if (isOverdue(loan, today)) keys.add("overdue");
  if (me && loan.requested_by === me.user_id) keys.add("mine");
  return keys;
}

/** Number of LOANS per chip. */
export function inboxCounts(loans: PlateLoan[], me: MeResponse | undefined, today: string = todayISO()): Record<InboxKey, number> {
  const counts = Object.fromEntries(INBOX_ORDER.map((k) => [k, 0])) as Record<InboxKey, number>;
  for (const loan of loans) for (const key of loanInboxKeys(loan, me, today)) counts[key] += 1;
  return counts;
}

/** Cross-org context from the viewer's side; null for a self-checkout. */
export function orgLine(loan: PlateLoan, me: MeResponse | undefined, orgName: (id: string) => string): string | null {
  if (loan.owner_org_id === loan.borrower_org_id) return null;
  if (me?.org_id === loan.owner_org_id) return `Lent to ${orgName(loan.borrower_org_id)}`;
  if (me?.org_id === loan.borrower_org_id) return `Borrowed from ${orgName(loan.owner_org_id)}`;
  return `${orgName(loan.borrower_org_id)} → ${orgName(loan.owner_org_id)}`;
}

export function loanTitle(loan: PlateLoan, requesterName: string): string {
  const n = loan.items.length;
  const what = setSummary(loan) || `${n} plate${n === 1 ? "" : "s"}`;
  return [requesterName, what].filter(Boolean).join(" · ");
}

/** Soonest due first (overdue on top), no due date last, then newest first. */
export function sortOpenLoans(loans: PlateLoan[]): PlateLoan[] {
  return [...loans].sort((a, b) => {
    if (a.due_date && b.due_date && a.due_date !== b.due_date) return a.due_date < b.due_date ? -1 : 1;
    if (a.due_date && !b.due_date) return -1;
    if (!a.due_date && b.due_date) return 1;
    return a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0;
  });
}
```

- [ ] **Step 6: Run** both test files — PASS. Biome the four files. `pnpm exec tsc --noEmit` must stay clean.

---

### Task 4: `CountChips` + `LoanRow`

**Files:**
- Create: `frontend/src/features/inventory/components/count-chips.tsx`, `frontend/src/features/inventory/components/loan-row.tsx`
- Test: `frontend/src/features/inventory/components/loan-row.test.tsx`

**Interfaces:**
- Consumes: Task 1 `formatDue`; Task 3 `itemStatusCounts`, `orgLine`, `setSummary`.
- Produces:
  ```ts
  export interface CountChip { key: string; label: string; count: number; tone?: "destructive" }
  export function CountChips(props: { chips: CountChip[]; active: string | null; onChange: (key: string | null) => void }): JSX.Element | null
  export interface LoanRowProps { loan: PlateLoan; me: MeResponse | undefined; requesterName: string; orgName: (id: string) => string }
  export function LoanRow(props: LoanRowProps): JSX.Element
  ```

- [ ] **Step 1: Write `loan-row.test.tsx`:**

```tsx
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { MeResponse } from "@/shared/lib/api/model";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PlateLoan } from "../hooks/use-plate-loans";
import { LoanRow } from "./loan-row";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));

const loan = {
  id: "l1", status: "open", owner_org_id: "A", borrower_org_id: "B", requested_by: "u1",
  due_date: "2000-01-01", notes: "Migrated · requester: Xuelin Bian", created_at: "2026-08-01T12:00:00Z",
  items: [
    { id: "i1", plate_id: "p1", barcode: "1", plate_label: "P1", status: "checked_out", status_changed_at: "2026-08-01T00:00:00Z", group_id: "g1", group_name: "Set 5" },
    { id: "i2", plate_id: "p2", barcode: "2", plate_label: "P2", status: "return_pending", status_changed_at: "2026-08-01T00:00:00Z", group_id: "g1", group_name: "Set 5" },
  ],
} as unknown as PlateLoan;
const me = { user_id: "u9", email: "", name: "", org_id: "A", is_admin: false, workspace_role: "editor" } as MeResponse;
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
```

- [ ] **Step 2: Run** it — FAIL (module missing).

- [ ] **Step 3: Implement `count-chips.tsx`:**

```tsx
"use client";

import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";

export interface CountChip {
  key: string;
  label: string;
  count: number;
  tone?: "destructive";
}

/** Single-active toggle chips with counts; chips with count 0 are not rendered
 * and the whole strip disappears when nothing is left. */
export function CountChips({
  chips,
  active,
  onChange,
}: {
  chips: CountChip[];
  active: string | null;
  onChange: (key: string | null) => void;
}) {
  const visible = chips.filter((c) => c.count > 0);
  if (visible.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Filter">
      {visible.map((c) => {
        const isActive = active === c.key;
        return (
          <Button
            key={c.key}
            type="button"
            size="sm"
            variant={isActive ? "default" : "outline"}
            aria-pressed={isActive}
            className={cn(
              "h-7 gap-1.5 px-2.5",
              !isActive && c.tone === "destructive" && "border-destructive/40 text-destructive",
            )}
            onClick={() => onChange(isActive ? null : c.key)}
          >
            {c.label}
            <span
              className={cn(
                "rounded-full px-1.5 text-xs tabular-nums",
                isActive ? "bg-primary-foreground/20" : "bg-muted",
              )}
            >
              {c.count}
            </span>
          </Button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Implement `loan-row.tsx`:**

```tsx
"use client";

import { StatusBadge } from "@/shared/components/status-badge";
import type { MeResponse } from "@/shared/lib/api/model";
import { formatDate, formatDue } from "@/shared/lib/format-date";
import { formatStatusLabel } from "@/shared/lib/status-variants";
import { cn } from "@/shared/lib/utils";
import Link from "next/link";
import { LOAN_VARIANT, type PlateLoan } from "../hooks/use-plate-loans";
import { itemStatusCounts, orgLine, setSummary } from "../lib/loan-summary";

export interface LoanRowProps {
  loan: PlateLoan;
  me: MeResponse | undefined;
  requesterName: string;
  orgName: (id: string) => string;
}

/** One open loan as a two-line row. Never fetches — names arrive as props. */
export function LoanRow({ loan, me, requesterName, orgName }: LoanRowProps) {
  const sets = setSummary(loan);
  const due = formatDue(loan.due_date);
  const org = orgLine(loan, me, orgName);
  const n = loan.items.length;
  return (
    <Link
      href={`/inventory/loans/${loan.id}`}
      className="block rounded-md border bg-card px-4 py-3 transition-colors hover:bg-accent"
      data-testid="loan-row"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 text-sm">
          <span className="font-medium">{requesterName}</span>
          {sets ? <span className="text-muted-foreground">{sets}</span> : null}
          <span className="text-muted-foreground">
            {n} plate{n === 1 ? "" : "s"}
          </span>
        </span>
        {due ? (
          <span
            title={`Due ${formatDate(loan.due_date)}`}
            className={cn(
              "shrink-0 text-sm",
              due.overdue ? "font-medium text-destructive" : "text-muted-foreground",
            )}
          >
            {due.label}
          </span>
        ) : null}
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-3">
        <span className="flex flex-wrap items-center gap-1.5">
          {itemStatusCounts(loan).map(({ status, count }) => (
            <StatusBadge
              key={status}
              status={status}
              variant={LOAN_VARIANT[status]}
              label={`${count} ${formatStatusLabel(status).toLowerCase()}`}
            />
          ))}
          {org ? <span className="text-xs text-muted-foreground">{org}</span> : null}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          requested {formatDate(loan.created_at)}
        </span>
      </div>
      {loan.notes ? (
        <p className="mt-1 truncate text-xs text-muted-foreground" title={loan.notes}>
          {loan.notes}
        </p>
      ) : null}
    </Link>
  );
}
```

- [ ] **Step 5: Run** the test — PASS. Biome the three files.

---

### Task 5: Loan page + route; delete `loan-card`

**Files:**
- Create: `frontend/src/features/inventory/components/loan-page.tsx`, `frontend/src/app/(dashboard)/inventory/loans/[id]/page.tsx`
- Delete: `frontend/src/features/inventory/components/loan-card.tsx`, `frontend/src/features/inventory/components/loan-card.test.tsx`
- Test: `frontend/src/features/inventory/components/loan-page.test.tsx`
- Note: `loan-dashboard.tsx` still imports `LoanCard` until Task 6 replaces it — after deleting, leave the dashboard untouched (tsc will be red on that one import until Task 6; that is expected inside wave 2).

**Interfaces:**
- Consumes: Task 1 `formatDue`; Task 2 `useMemberNames`; Task 3 `availableVerbs`, `eligibleItems`, `VERB_LABELS`, `loanSets`, `loanTitle`, `orgLine`; existing `useLoan`, `useLoanItemsAction`, `LOAN_VARIANT`, `CommentFeed`, `RequestReturnDialog`, `DetailShell`.
- Produces: `export function LoanPage({ loanId }: { loanId: string })`.

- [ ] **Step 1: Write `loan-page.test.tsx`:**

```tsx
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { MeResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoanPage } from "./loan-page";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/inventory/loans/l1",
}));
const mocked = vi.mocked(customInstance);

const loan = {
  id: "l1", status: "open", owner_org_id: "org-A", borrower_org_id: "org-B", requested_by: "u1",
  due_date: null, notes: null, created_at: "2026-08-13T00:00:00Z", closed_at: null,
  items: [
    { id: "i1", plate_id: "p1", barcode: "0001", plate_label: "P1", status: "requested", status_changed_at: "2026-08-13T00:00:00Z", group_id: "g1", group_name: "Set 5" },
    { id: "i2", plate_id: "p2", barcode: "0002", plate_label: "P2", status: "checked_out", status_changed_at: "2026-08-14T00:00:00Z", group_id: "g2", group_name: "Set 27" },
  ],
};
const me = (org: string, admin = false): MeResponse =>
  ({ user_id: "u9", email: "", name: "", org_id: org, is_admin: admin, workspace_role: admin ? "admin" : "editor" }) as MeResponse;

function setup(viewer: MeResponse) {
  mocked.mockReset();
  mocked.mockImplementation((opts: { url: string; method: string }) => {
    if (opts.url === "/api/v1/plate-loans/l1") return Promise.resolve(loan);
    if (opts.url === "/api/v1/user/me") return Promise.resolve(viewer);
    if (opts.url === "/api/v1/orgs") return Promise.resolve([{ id: "org-A", slug: "a", name: "TAMU" }, { id: "org-B", slug: "b", name: "Sanofi" }]);
    if (opts.url === "/api/v1/user/workspace-members") return Promise.resolve([{ user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" }]);
    if (opts.url === "/api/v1/comments") return Promise.resolve([]);
    return Promise.resolve(loan); // verb POSTs
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
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
    expect(await screen.findByRole("button", { name: /request return \(1\)/i })).toBeInTheDocument();
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
    expect(screen.getByRole("link", { name: "0001" })).toHaveAttribute("href", "/inventory/plates/p1");
  });
  it("request-return opens the dialog instead of posting immediately", async () => {
    setup(me("org-B"));
    fireEvent.click(await screen.findByRole("button", { name: /request return \(1\)/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(mocked).not.toHaveBeenCalledWith(expect.objectContaining({ url: expect.stringContaining("items:request-return") }));
  });
  it("approve posts the eligible item ids", async () => {
    setup(me("org-A"));
    fireEvent.click(await screen.findByRole("button", { name: /approve \(1\)/i }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({ url: "/api/v1/plate-loans/l1/items:approve", method: "POST", data: { item_ids: ["i1"] } }),
      ),
    );
  });
});
```

- [ ] **Step 2: Run** it — FAIL.

- [ ] **Step 3: Create the route** `app/(dashboard)/inventory/loans/[id]/page.tsx`:

```tsx
"use client";

import { LoanPage } from "@/features/inventory/components/loan-page";
import { use } from "react";

export default function LoanDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <LoanPage loanId={id} />;
}
```

- [ ] **Step 4: Implement `loan-page.tsx`:**

```tsx
"use client";

import { DetailShell } from "@/shared/components/detail-shell";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { canEdit, useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { formatDate, formatDateTime, formatDue } from "@/shared/lib/format-date";
import { cn } from "@/shared/lib/utils";
import Link from "next/link";
import { Fragment, useState } from "react";
import {
  LOAN_VARIANT,
  type LoanVerb,
  type PlateLoan,
  useLoan,
  useLoanItemsAction,
} from "../hooks/use-plate-loans";
import { loanSets, loanTitle, orgLine } from "../lib/loan-summary";
import { VERB_LABELS, availableVerbs, eligibleItems } from "../lib/loan-verbs";
import { CommentFeed } from "./comment-feed";
import { RequestReturnDialog } from "./request-return-dialog";

export interface LoanPageProps {
  loanId: string;
}

export function LoanPage({ loanId }: LoanPageProps) {
  const query = useLoan(loanId);
  const { data: me } = useCurrentUser();
  const { data: orgs } = useOrgs();
  const memberName = useMemberNames();
  const action = useLoanItemsAction();
  const [checked, setChecked] = useState<Set<string>>(new Set());
  // Non-null while the request-return dialog is up; the item ids it was opened for.
  const [returnTargets, setReturnTargets] = useState<string[] | null>(null);
  const orgName = (id: string) => orgs?.find((o) => o.id === id)?.name ?? "Unknown org";

  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const runVerb = (loan: PlateLoan, verb: LoanVerb) => {
    const eligible = eligibleItems(loan, verb);
    const targets = checked.size ? eligible.filter((i) => checked.has(i.id)) : eligible;
    if (targets.length === 0) return;
    if (verb === "request-return") {
      // Comments are mandatory per group — collected in a dialog, not fired straight away.
      setReturnTargets(targets.map((i) => i.id));
      return;
    }
    action.mutate(
      { loanId: loan.id, verb, itemIds: targets.map((i) => i.id) },
      { onSuccess: () => setChecked(new Set()) },
    );
  };

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory/loans"
        backLabel="Back to Loans"
        title={(loan) => loanTitle(loan, memberName(loan.requested_by))}
        notFoundMessage="Loan not found."
        actions={(loan) =>
          availableVerbs(loan, me).map((verb) => {
            const eligible = eligibleItems(loan, verb);
            const count = checked.size
              ? eligible.filter((i) => checked.has(i.id)).length
              : eligible.length;
            return (
              <Button
                key={verb}
                size="sm"
                variant={
                  verb === "approve" ? "default" : verb === "deny" ? "destructive" : "outline"
                }
                disabled={action.isPending || count === 0}
                onClick={() => runVerb(loan, verb)}
              >
                {VERB_LABELS[verb]} ({count})
              </Button>
            );
          })
        }
      >
        {(loan) => {
          const verbs = availableVerbs(loan, me);
          const due = formatDue(loan.due_date);
          const org = orgLine(loan, me, orgName);
          const sets = loanSets(loan);
          const grouped = sets.some((s) => s.id !== null);
          const n = loan.items.length;
          const cols = verbs.length > 0 ? 5 : 4;
          return (
            <>
              <div className="-mt-3 flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                  <StatusBadge status={loan.status} variant={LOAN_VARIANT[loan.status]} />
                  {due ? (
                    <span
                      title={`Due ${formatDate(loan.due_date)}`}
                      className={cn(
                        due.overdue ? "font-medium text-destructive" : "text-muted-foreground",
                      )}
                    >
                      {due.label}
                    </span>
                  ) : null}
                  <span className="text-muted-foreground">
                    requested {formatDate(loan.created_at)}
                  </span>
                  {org ? <span className="text-muted-foreground">{org}</span> : null}
                  <span className="text-muted-foreground">
                    {n} plate{n === 1 ? "" : "s"}
                  </span>
                </div>
                {loan.notes ? <p className="text-sm text-muted-foreground">{loan.notes}</p> : null}
              </div>

              <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Plates ({n})</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          {verbs.length > 0 ? <TableHead className="w-8" /> : null}
                          <TableHead>Barcode</TableHead>
                          <TableHead>Plate</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Since</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sets.map((set) => (
                          <Fragment key={set.id ?? "__ungrouped__"}>
                            {grouped ? (
                              <TableRow className="bg-muted/40 hover:bg-muted/40">
                                <TableCell
                                  colSpan={cols}
                                  className="py-1.5 text-xs font-medium text-muted-foreground"
                                >
                                  {set.name} · {set.count} plate{set.count === 1 ? "" : "s"}
                                </TableCell>
                              </TableRow>
                            ) : null}
                            {loan.items
                              .filter((i) => (i.group_id ?? null) === set.id)
                              .map((item) => (
                                <TableRow key={item.id}>
                                  {verbs.length > 0 ? (
                                    <TableCell>
                                      <Checkbox
                                        checked={checked.has(item.id)}
                                        onCheckedChange={() => toggle(item.id)}
                                        aria-label={`Select ${item.barcode}`}
                                      />
                                    </TableCell>
                                  ) : null}
                                  <TableCell className="font-mono text-xs">
                                    <Link
                                      href={`/inventory/plates/${item.plate_id}`}
                                      className="text-primary hover:underline"
                                    >
                                      {item.barcode}
                                    </Link>
                                  </TableCell>
                                  <TableCell>{item.plate_label}</TableCell>
                                  <TableCell>
                                    <StatusBadge
                                      status={item.status}
                                      variant={LOAN_VARIANT[item.status]}
                                    />
                                  </TableCell>
                                  <TableCell
                                    className="text-muted-foreground"
                                    title={formatDateTime(item.status_changed_at)}
                                  >
                                    {formatDate(item.status_changed_at)}
                                  </TableCell>
                                </TableRow>
                              ))}
                          </Fragment>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Activity</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <CommentFeed
                      scope={{ loanId: loan.id }}
                      composerTarget={{ targetType: "plate_loan", targetId: loan.id }}
                      canWrite={canEdit(me)}
                      emptyText="No activity yet — return notes and comments on this loan appear here."
                    />
                  </CardContent>
                </Card>
              </div>
            </>
          );
        }}
      </DetailShell>

      {query.data ? (
        <RequestReturnDialog
          open={returnTargets !== null}
          onOpenChange={(o) => {
            if (!o) {
              setReturnTargets(null);
              setChecked(new Set());
            }
          }}
          loan={query.data}
          itemIds={returnTargets ?? []}
        />
      ) : null}
    </>
  );
}
```

- [ ] **Step 5:** `git rm -q frontend/src/features/inventory/components/loan-card.tsx frontend/src/features/inventory/components/loan-card.test.tsx` (stage the deletion only — do not commit).

- [ ] **Step 6: Run** `pnpm vitest run src/features/inventory/components/loan-page.test.tsx` — PASS. Biome the new files.

---

### Task 6: Loans dashboard rewrite (Open chips + rows · History grid)

**Files:**
- Rewrite: `frontend/src/features/inventory/components/loan-dashboard.tsx`
- Test: create `frontend/src/features/inventory/components/loan-dashboard.test.tsx`

**Interfaces:**
- Consumes: Task 2 `useMemberNames`; Task 3 `INBOX_ORDER`, `INBOX_LABELS`, `InboxKey`, `inboxCounts`, `loanInboxKeys`, `loanOutcome`, `setSummary`, `sortOpenLoans`; Task 4 `CountChips`, `LoanRow`; existing `useLoans`, `DataGrid`, `RequestLoanDialog`, `useHashTab`.

- [ ] **Step 1: Write `loan-dashboard.test.tsx`:**

```tsx
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
  id, plate_id: `p${id}`, barcode: id, plate_label: `P${id}`, status, status_changed_at: "2026-08-01T00:00:00Z", group_id: null, group_name: null,
});
const open = [
  { id: "l1", status: "open", owner_org_id: "A", borrower_org_id: "A", requested_by: "u1", due_date: "2000-01-01", notes: null, created_at: "2026-08-01T00:00:00Z", items: [item("1", "requested")] },
  { id: "l2", status: "open", owner_org_id: "A", borrower_org_id: "A", requested_by: "u2", due_date: null, notes: null, created_at: "2026-08-02T00:00:00Z", items: [item("2", "checked_out")] },
];
const me = { user_id: "u9", email: "", name: "", org_id: "A", is_admin: false, workspace_role: "editor" };

function setup() {
  mocked.mockReset();
  window.location.hash = "";
  mocked.mockImplementation((opts: { url: string; params?: Record<string, unknown> }) => {
    if (opts.url === "/api/v1/plate-loans") return Promise.resolve(opts.params?.status === "closed" ? [] : open);
    if (opts.url === "/api/v1/user/me") return Promise.resolve(me);
    if (opts.url === "/api/v1/orgs") return Promise.resolve([{ id: "A", slug: "a", name: "TAMU" }]);
    if (opts.url === "/api/v1/user/workspace-members")
      return Promise.resolve([{ user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" }, { user_id: "u2", name: "Da Di", email: "", avatar_url: null, role: "editor" }]);
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
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
    expect(mocked).not.toHaveBeenCalledWith(expect.objectContaining({ params: expect.objectContaining({ status: "closed" }) }));
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(expect.objectContaining({ params: expect.objectContaining({ status: "closed" }) })),
    );
  });
});
```

- [ ] **Step 2: Run** it — FAIL (old dashboard).

- [ ] **Step 3: Rewrite `loan-dashboard.tsx`:**

```tsx
"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { PageHeader } from "@/shared/components/page-header";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useHashTab } from "@/shared/hooks/use-hash-tab";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { formatDate } from "@/shared/lib/format-date";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { LOAN_VARIANT, type PlateLoan, useLoans } from "../hooks/use-plate-loans";
import {
  INBOX_LABELS,
  INBOX_ORDER,
  type InboxKey,
  inboxCounts,
  loanInboxKeys,
  loanOutcome,
  setSummary,
  sortOpenLoans,
} from "../lib/loan-summary";
import { CountChips } from "./count-chips";
import { LoanRow } from "./loan-row";
import { RequestLoanDialog } from "./request-loan-dialog";

export function LoanDashboard() {
  const router = useRouter();
  const { data: me } = useCurrentUser();
  const { data: orgs } = useOrgs();
  const memberName = useMemberNames();
  const [tab, setTab] = useHashTab("open");
  const [chip, setChip] = useState<InboxKey | null>(null);
  const [requestOpen, setRequestOpen] = useState(false);
  const orgName = (id: string) => orgs?.find((o) => o.id === id)?.name ?? "Unknown org";

  // Visibility already scopes this to loans I own or borrow.
  const open = useLoans({ status: "open" });
  const closed = useLoans({ status: "closed" }, { enabled: tab === "history" });

  const openLoans = open.data ?? [];
  const counts = useMemo(() => inboxCounts(openLoans, me), [openLoans, me]);
  const visible = useMemo(
    () =>
      sortOpenLoans(chip ? openLoans.filter((l) => loanInboxKeys(l, me).has(chip)) : openLoans),
    [openLoans, chip, me],
  );
  const chips = INBOX_ORDER.map((key) => ({
    key,
    label: INBOX_LABELS[key],
    count: counts[key],
    tone: key === "overdue" ? ("destructive" as const) : undefined,
  }));

  const historyCols = useMemo<ColDef<PlateLoan>[]>(
    () => [
      {
        headerName: "Requester",
        valueGetter: (p) => (p.data ? memberName(p.data.requested_by) : ""),
        flex: 1,
        minWidth: 160,
      },
      {
        headerName: "Sets",
        valueGetter: (p) => (p.data ? setSummary(p.data) : ""),
        flex: 1.5,
        minWidth: 200,
      },
      { headerName: "Plates", valueGetter: (p) => p.data?.items.length ?? 0, width: 90 },
      {
        headerName: "Requested",
        field: "created_at",
        width: 130,
        valueFormatter: (p) => formatDate(p.value),
      },
      {
        headerName: "Closed",
        field: "closed_at",
        width: 130,
        sort: "desc",
        valueFormatter: (p) => formatDate(p.value),
      },
      {
        headerName: "Outcome",
        width: 120,
        valueGetter: (p) => (p.data ? loanOutcome(p.data) : ""),
        cellRenderer: (p: ICellRendererParams<PlateLoan, string>) =>
          p.value ? <StatusBadge status={p.value} variant={LOAN_VARIANT[p.value]} /> : null,
      },
      {
        headerName: "Barcodes",
        hide: true, // quick-filter only
        valueGetter: (p) => p.data?.items.map((i) => i.barcode).join(" ") ?? "",
      },
    ],
    [memberName],
  );

  return (
    <div className="flex flex-col gap-4 p-6">
      <PageHeader title="Loans" subtitle="Plate checkouts — who has what, and what's due back.">
        <Button onClick={() => setRequestOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Request loan
        </Button>
      </PageHeader>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="open">Open</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="open" className="mt-4 flex flex-col gap-3">
          <CountChips chips={chips} active={chip} onChange={(k) => setChip(k as InboxKey | null)} />
          {open.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : open.error ? (
            <p className="text-sm text-destructive">
              {open.error instanceof Error ? open.error.message : "Failed to load loans"}
            </p>
          ) : visible.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {chip ? `Nothing matches "${INBOX_LABELS[chip]}".` : "No open loans."}
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {visible.map((loan) => (
                <LoanRow
                  key={loan.id}
                  loan={loan}
                  me={me}
                  requesterName={memberName(loan.requested_by)}
                  orgName={orgName}
                />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <DataGrid<PlateLoan>
            rowData={closed.data}
            columnDefs={historyCols}
            loading={closed.isLoading || !closed.data}
            height="600px"
            suppressFilters
            preferencesKey="loans-history"
            searchPlaceholder="Search requester, set or barcode…"
            includeHiddenColumnsInQuickFilter
            onRowClick={(loan) => router.push(`/inventory/loans/${loan.id}`)}
            emptyState={<p className="p-6 text-sm text-muted-foreground">No closed loans yet.</p>}
          />
        </TabsContent>
      </Tabs>

      <RequestLoanDialog
        open={requestOpen}
        onOpenChange={setRequestOpen}
        orgId={me?.org_id ?? undefined}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run** the test — PASS. Then `pnpm exec tsc --noEmit` (must be clean now that `LoanCard` is gone) and biome the two files.

---

### Task 7: Request-loan dialog (`initialBarcodes`, navigate) + comment-feed link

**Files:**
- Modify: `frontend/src/features/inventory/components/request-loan-dialog.tsx`, `frontend/src/features/inventory/components/comment-feed.tsx`
- Test: `frontend/src/features/inventory/components/request-loan-dialog.test.tsx`, `frontend/src/features/inventory/components/comment-feed.test.tsx`

**Interfaces:**
- Produces: `RequestLoanDialogProps.initialBarcodes?: string[]` — when non-empty on open, mode `paste` with the textarea pre-filled one per line. On success the dialog closes and `router.push("/inventory/loans/{id}")`.

- [ ] **Step 1: Tests.** In `request-loan-dialog.test.tsx` add `vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }))` with `const pushMock = vi.fn();` declared above (use `vi.hoisted` so the mock factory can see it: `const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));`). Add:

```tsx
  it("initialBarcodes opens in paste mode pre-filled, and success navigates to the loan", async () => {
    setup({ initialBarcodes: ["005131", "005132"] });
    const box = screen.getByLabelText("Barcodes") as HTMLTextAreaElement;
    expect(box.value).toBe("005131\n005132");
    fireEvent.click(screen.getByRole("button", { name: "Request loan" }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({ method: "POST", data: { barcodes: ["005131", "005132"] } }),
      ),
    );
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/inventory/loans/loan1"));
  });
```

In `comment-feed.test.tsx` change the I2 test: link name `"view loan"`, href `"/inventory/loans/loan-1"`; the "hides the link" test queries `{ name: "view loan" }`.

- [ ] **Step 2: Run** both files — FAIL.

- [ ] **Step 3: Implement.** `request-loan-dialog.tsx`: add `import { useRouter } from "next/navigation";`, prop `initialBarcodes?: string[]`, `const router = useRouter();`. In the reset effect:

```ts
  useEffect(() => {
    if (!open) return;
    const preset = initialBarcodes ?? [];
    setMode(preset.length > 0 ? "paste" : "group");
    setGroupId(initialGroupId ?? "");
    setPaste(preset.join("\n"));
    setCsvBarcodes([]);
    setCsvName("");
    setBorrowerOrgId(MY_ORG);
    setDueDate("");
    setNotes("");
  }, [open, initialGroupId, initialBarcodes]);
```

and in `handleSubmit`: `request.mutate(body, { onSuccess: (loan) => { onOpenChange(false); router.push(`/inventory/loans/${loan.id}`); } });`.

`comment-feed.tsx`: the link becomes `<Link href={`/inventory/loans/${c.loan_id}`} className="text-xs text-primary hover:underline">view loan</Link>`.

Callers must pass a **stable** `initialBarcodes` (memoized or state) — an inline array literal would re-run the reset effect every render.

- [ ] **Step 4: Run** both test files — PASS. Biome the four files.

---

### Task 8: `storage-path.ts`, `plate-where.ts`, `useGroupIndex`

**Files:**
- Create: `frontend/src/features/inventory/lib/storage-path.ts`, `frontend/src/features/inventory/lib/plate-where.ts`
- Modify: `frontend/src/features/inventory/hooks/use-plate-groups.ts` (append `useGroupIndex`)
- Test: `frontend/src/features/inventory/lib/storage-path.test.ts`, `frontend/src/features/inventory/lib/plate-where.test.ts`

**Interfaces:**
- Consumes: Task 1 `formatDue`; Task 3 `isOverdue`; existing `buildCustodyMap` output shape `{ loan: PlateLoan; item: PlateLoanItem }`, `StorageLocation` from `../types`, `RegisteredPlate` from `../types/plates`, `formatStatusLabel`/`formatDate`.
- Produces:
  ```ts
  // storage-path.ts
  export function storageChain(locations: StorageLocation[] | undefined, id: string | null | undefined): string[]
  export function storagePath(locations, id, depth = 2): string      // last `depth` names joined " › "
  export function storageFullPath(locations, id): string
  // plate-where.ts
  export type Whereabouts =
    | { kind: "custody"; loan: PlateLoan; item: PlateLoanItem; overdue: boolean }
    | { kind: "terminal"; status: "depleted" | "disposed" }
    | { kind: "location"; path: string; fullPath: string }
    | { kind: "status"; status: PlateStatus }
  export function plateWhereabouts(plate: RegisteredPlate, custody: { loan: PlateLoan; item: PlateLoanItem } | undefined, locations: StorageLocation[] | undefined): Whereabouts
  export type WhereTone = "overdue" | "loan" | "muted" | "normal"
  export function whereText(w: Whereabouts, requesterName: (id: string) => string): { text: string; tone: WhereTone; title?: string }
  export type PlateChipKey = "on_loan" | "overdue" | "depleted"
  export const PLATE_CHIP_ORDER: PlateChipKey[]; export const PLATE_CHIP_LABELS: Record<PlateChipKey, string>  // On loan · Overdue · Depleted
  export function plateChipKeys(plate: RegisteredPlate, w: Whereabouts): Set<PlateChipKey>
  // use-plate-groups.ts
  export interface GroupRef { name: string; path: string }
  export function useGroupIndex(orgIds: string[]): Map<string, GroupRef>   // "SAC1 › Set 014"
  ```

- [ ] **Step 1: Write `storage-path.test.ts`:**

```ts
import { describe, expect, it } from "vitest";
import type { StorageLocation } from "../types";
import { storageChain, storageFullPath, storagePath } from "./storage-path";

const loc = (id: string, name: string, parent_id: string | null): StorageLocation =>
  ({ id, name, parent_id, type: "x", workspace_id: "w" }) as unknown as StorageLocation;
const locations = [loc("site", "TAMU", null), loc("bld", "ILSB", "site"), loc("room", "Room 1148", "bld"), loc("frz", "Freezer 3", "room")];

describe("storage path", () => {
  it("walks the parent chain root-first", () => {
    expect(storageChain(locations, "frz")).toEqual(["TAMU", "ILSB", "Room 1148", "Freezer 3"]);
  });
  it("storagePath keeps the last `depth` names; full path keeps all", () => {
    expect(storagePath(locations, "frz")).toBe("Room 1148 › Freezer 3");
    expect(storagePath(locations, "frz", 3)).toBe("ILSB › Room 1148 › Freezer 3");
    expect(storageFullPath(locations, "frz")).toBe("TAMU › ILSB › Room 1148 › Freezer 3");
  });
  it("unknown id / no id / no locations → empty", () => {
    expect(storagePath(locations, "nope")).toBe("");
    expect(storagePath(locations, null)).toBe("");
    expect(storagePath(undefined, "frz")).toBe("");
  });
  it("survives a parent cycle", () => {
    const cyclic = [loc("a", "A", "b"), loc("b", "B", "a")];
    expect(storageChain(cyclic, "a")).toEqual(["B", "A"]);
  });
});
```

- [ ] **Step 2: Write `plate-where.test.ts`:**

```ts
import { describe, expect, it } from "vitest";
import type { PlateLoan, PlateLoanItem } from "../hooks/use-plate-loans";
import type { StorageLocation } from "../types";
import type { RegisteredPlate } from "../types/plates";
import { plateChipKeys, plateWhereabouts, whereText } from "./plate-where";

const plate = (over: Partial<RegisteredPlate> = {}): RegisteredPlate =>
  ({ id: "p1", barcode: "0001", plate_label: "P1", format: "384", plate_type: "assay", status: "stored",
     storage_location_id: "frz", workspace_id: "w", registered_by: "u", ...over }) as unknown as RegisteredPlate;
const locations = [
  { id: "room", name: "Room 1148", parent_id: null }, { id: "frz", name: "Freezer 3", parent_id: "room" },
] as unknown as StorageLocation[];
const custody = (itemStatus: string, due: string | null) => ({
  loan: { id: "l1", status: "open", requested_by: "u1", due_date: due, items: [] } as unknown as PlateLoan,
  item: { id: "i1", plate_id: "p1", status: itemStatus } as unknown as PlateLoanItem,
});
const name = () => "Maia Young";

describe("plateWhereabouts precedence", () => {
  it("custody beats everything", () => {
    const w = plateWhereabouts(plate({ status: "depleted" }), custody("checked_out", "2000-01-01"), locations);
    expect(w.kind).toBe("custody");
    expect(w.kind === "custody" && w.overdue).toBe(true);
  });
  it("terminal status beats location", () => {
    expect(plateWhereabouts(plate({ status: "disposed" }), undefined, locations)).toEqual({ kind: "terminal", status: "disposed" });
  });
  it("location, else status", () => {
    expect(plateWhereabouts(plate(), undefined, locations)).toEqual({ kind: "location", path: "Room 1148 › Freezer 3", fullPath: "Room 1148 › Freezer 3" });
    expect(plateWhereabouts(plate({ storage_location_id: null }), undefined, locations)).toEqual({ kind: "status", status: "stored" });
  });
});

describe("whereText", () => {
  it("checked out with a due date → name · due phrase, overdue tone", () => {
    const t = whereText(plateWhereabouts(plate(), custody("checked_out", "2000-01-01"), locations), name);
    expect(t.text).toMatch(/^Maia Young · \d+ y overdue$/);
    expect(t.tone).toBe("overdue");
  });
  it("other custody statuses → name · status word, loan tone", () => {
    const t = whereText(plateWhereabouts(plate(), custody("requested", null), locations), name);
    expect(t).toEqual({ text: "Maia Young · requested", tone: "loan", title: undefined });
  });
  it("terminal muted; location normal with full-path title; status muted", () => {
    expect(whereText({ kind: "terminal", status: "depleted" }, name)).toEqual({ text: "Depleted", tone: "muted" });
    expect(whereText({ kind: "location", path: "Freezer 3", fullPath: "Room › Freezer 3" }, name)).toEqual({ text: "Freezer 3", tone: "normal", title: "Room › Freezer 3" });
    expect(whereText({ kind: "status", status: "registered" }, name)).toEqual({ text: "Registered", tone: "muted" });
  });
});

describe("plateChipKeys", () => {
  it("on_loan (+overdue) for custody; depleted for depleted plates", () => {
    const w = plateWhereabouts(plate(), custody("checked_out", "2000-01-01"), locations);
    expect([...plateChipKeys(plate(), w)].sort()).toEqual(["on_loan", "overdue"]);
    expect([...plateChipKeys(plate({ status: "depleted" }), { kind: "terminal", status: "depleted" })]).toEqual(["depleted"]);
    expect(plateChipKeys(plate(), { kind: "status", status: "stored" }).size).toBe(0);
  });
});
```

- [ ] **Step 3: Run** both — FAIL.

- [ ] **Step 4: Implement `storage-path.ts`:**

```ts
import type { StorageLocation } from "../types";

/** Names from the root down to `id`; [] when unknown. Cycle-guarded. */
export function storageChain(
  locations: StorageLocation[] | undefined,
  id: string | null | undefined,
): string[] {
  if (!locations || !id) return [];
  const byId = new Map(locations.map((l) => [l.id, l]));
  const names: string[] = [];
  const seen = new Set<string>();
  let cur = byId.get(id);
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id);
    names.unshift(cur.name);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return names;
}

/** "Room 1148 › Freezer 3" — the last `depth` levels; "" when unknown. */
export function storagePath(
  locations: StorageLocation[] | undefined,
  id: string | null | undefined,
  depth = 2,
): string {
  return storageChain(locations, id).slice(-depth).join(" › ");
}

export function storageFullPath(
  locations: StorageLocation[] | undefined,
  id: string | null | undefined,
): string {
  return storageChain(locations, id).join(" › ");
}
```

- [ ] **Step 5: Implement `plate-where.ts`:**

```ts
import { formatDate, formatDue } from "@/shared/lib/format-date";
import { formatStatusLabel } from "@/shared/lib/status-variants";
import { LoanItemStatus, type PlateLoan, type PlateLoanItem } from "../hooks/use-plate-loans";
import type { StorageLocation } from "../types";
import type { PlateStatus, RegisteredPlate } from "../types/plates";
import { isOverdue } from "./loan-summary";
import { storageFullPath, storagePath } from "./storage-path";

export type Whereabouts =
  | { kind: "custody"; loan: PlateLoan; item: PlateLoanItem; overdue: boolean }
  | { kind: "terminal"; status: "depleted" | "disposed" }
  | { kind: "location"; path: string; fullPath: string }
  | { kind: "status"; status: PlateStatus };

/** Where a plate is, one answer: on loan > depleted/disposed > storage location > status. */
export function plateWhereabouts(
  plate: RegisteredPlate,
  custody: { loan: PlateLoan; item: PlateLoanItem } | undefined,
  locations: StorageLocation[] | undefined,
): Whereabouts {
  if (custody) {
    return { kind: "custody", loan: custody.loan, item: custody.item, overdue: isOverdue(custody.loan) };
  }
  if (plate.status === "depleted" || plate.status === "disposed") {
    return { kind: "terminal", status: plate.status };
  }
  const path = storagePath(locations, plate.storage_location_id);
  if (path) {
    return { kind: "location", path, fullPath: storageFullPath(locations, plate.storage_location_id) };
  }
  return { kind: "status", status: plate.status };
}

export type WhereTone = "overdue" | "loan" | "muted" | "normal";

/** One-line text for the plate list's Where column. */
export function whereText(
  w: Whereabouts,
  requesterName: (id: string) => string,
): { text: string; tone: WhereTone; title?: string } {
  switch (w.kind) {
    case "custody": {
      const due = w.item.status === LoanItemStatus.checked_out ? formatDue(w.loan.due_date) : null;
      const phrase = due ? due.label : formatStatusLabel(w.item.status).toLowerCase();
      return {
        text: `${requesterName(w.loan.requested_by)} · ${phrase}`,
        tone: w.overdue ? "overdue" : "loan",
        title: w.loan.due_date ? `Due ${formatDate(w.loan.due_date)}` : undefined,
      };
    }
    case "terminal":
      return { text: formatStatusLabel(w.status), tone: "muted" };
    case "location":
      return { text: w.path, tone: "normal", title: w.fullPath };
    case "status":
      return { text: formatStatusLabel(w.status), tone: "muted" };
  }
}

export type PlateChipKey = "on_loan" | "overdue" | "depleted";
export const PLATE_CHIP_ORDER: PlateChipKey[] = ["on_loan", "overdue", "depleted"];
export const PLATE_CHIP_LABELS: Record<PlateChipKey, string> = {
  on_loan: "On loan",
  overdue: "Overdue",
  depleted: "Depleted",
};

export function plateChipKeys(plate: RegisteredPlate, w: Whereabouts): Set<PlateChipKey> {
  const keys = new Set<PlateChipKey>();
  if (w.kind === "custody") {
    keys.add("on_loan");
    if (w.overdue) keys.add("overdue");
  }
  if (plate.status === "depleted") keys.add("depleted");
  return keys;
}
```

- [ ] **Step 6: Append `useGroupIndex` to `use-plate-groups.ts`** (add `useQueries` to the tanstack import and `useMemo` from react):

```ts
export interface GroupRef {
  name: string;
  /** Ancestry path, "SAC1 › Set 014". */
  path: string;
}

const combineTrees = (results: { data?: PlateGroupTree }[]) => results.map((r) => r.data);

/** group id → { name, path } over the trees of the given orgs. Shares the
 * `usePlateGroupTree` cache key, so the Plate Groups page and this index
 * never fetch the same tree twice. */
export function useGroupIndex(orgIds: string[]): Map<string, GroupRef> {
  const trees = useQueries({
    queries: orgIds.map((orgId) => ({
      queryKey: [...PLATE_GROUPS_KEY, "tree", orgId],
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        customInstance<PlateGroupTree>({
          url: `${API_V1}/plate-groups/tree`,
          method: "GET",
          params: { org_id: orgId },
          signal,
        }),
    })),
    combine: combineTrees,
  });
  return useMemo(() => {
    const index = new Map<string, GroupRef>();
    const walk = (nodes: PlateGroupNode[], prefix: string) => {
      for (const n of nodes) {
        const path = prefix ? `${prefix} › ${n.name}` : n.name;
        index.set(n.id, { name: n.name, path });
        walk(n.children ?? [], path);
      }
    };
    for (const tree of trees) if (tree) walk(tree.roots, "");
    return index;
  }, [trees]);
}
```

- [ ] **Step 7: Run** both test files — PASS. Biome the five files; `pnpm exec tsc --noEmit` clean (if `combine`'s typing complains, type `results` as `UseQueryResult<PlateGroupTree>[]` from `@tanstack/react-query`).

---

### Task 9: Plates list rewrite

**Files:**
- Rewrite: `frontend/src/features/inventory/components/plate-list.tsx`
- Test: create `frontend/src/features/inventory/components/plate-list.test.tsx`

**Interfaces:**
- Consumes: Task 2 `useMemberNames`; Task 4 `CountChips`; Task 7 `RequestLoanDialog.initialBarcodes`; Task 8 `plateWhereabouts`, `whereText`, `plateChipKeys`, `PLATE_CHIP_ORDER`, `PLATE_CHIP_LABELS`, `PlateChipKey`, `Whereabouts`, `useGroupIndex`; existing `usePlates`, `useLoans`, `buildCustodyMap`, `useStorageLocations`, `useOrgs`, `useCurrentUser`, `DataGrid` (`selectionToolbar`, `preferencesKey`), `TagFilter`, `OrgPlatePolicyDialog`, `RegisterPlateDialog`.
- Produces: `export const TONE_CLASS: Record<WhereTone, string>` (reused by Task 10 via import from `./plate-list`? No — put it in `lib/plate-where.ts` is cleaner; but Task 8 is already dispatched, so define it here and let Task 10 import `TONE_CLASS` from `./plate-list`).

- [ ] **Step 1: Write `plate-list.test.tsx`** (AG Grid renders rows in jsdom only with a fixed height; assert on the data that reaches the grid via `screen` text where it renders, and on the chips + toolbar):

```tsx
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
      <div data-testid="columns">{props.columnDefs.filter((c) => !c.hide).map((c) => c.headerName).join("|")}</div>
      <div data-testid="row-count">{props.rowData?.length ?? 0}</div>
      {props.rowData?.length === 0 ? props.emptyState : null}
      {props.selectionToolbar ? <div data-testid="toolbar">{props.selectionToolbar(props.rowData ?? [])}</div> : null}
    </div>
  ),
}));
const mocked = vi.mocked(customInstance);

const plates = [
  { id: "p1", barcode: "0001", plate_label: "A", format: "384", plate_type: "assay", status: "stored", storage_location_id: "frz", owner_org_id: "A", group_id: "g1" },
  { id: "p2", barcode: "0002", plate_label: "B", format: "384", plate_type: "assay", status: "stored", storage_location_id: null, owner_org_id: "A", group_id: null },
  { id: "p3", barcode: "0003", plate_label: "C", format: "96", plate_type: "assay", status: "depleted", storage_location_id: null, owner_org_id: "A", group_id: null },
];
const loans = [
  { id: "l1", status: "open", owner_org_id: "A", borrower_org_id: "A", requested_by: "u1", due_date: "2000-01-01", created_at: "2026-08-01T00:00:00Z",
    items: [{ id: "i1", plate_id: "p1", barcode: "0001", plate_label: "A", status: "checked_out", status_changed_at: "2026-08-01T00:00:00Z" }] },
];

function setup(me = { user_id: "u9", email: "", name: "", org_id: "A", org_slug: "tamu", is_admin: true, workspace_role: "admin" }) {
  mocked.mockReset();
  window.localStorage.clear();
  mocked.mockImplementation((opts: { url: string; params?: Record<string, unknown> }) => {
    if (opts.url === "/api/v1/plates") return Promise.resolve(plates);
    if (opts.url === "/api/v1/plate-loans") return Promise.resolve(loans);
    if (opts.url === "/api/v1/user/me") return Promise.resolve(me);
    if (opts.url === "/api/v1/orgs") return Promise.resolve([{ id: "A", slug: "tamu", name: "TAMU" }, { id: "B", slug: "b", name: "Sanofi" }]);
    if (opts.url === "/api/v1/user/workspace-members") return Promise.resolve([{ user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" }]);
    if (opts.url === "/api/v1/storage-locations") return Promise.resolve([{ id: "room", name: "Room 1148", parent_id: null, type: "room", workspace_id: "w" }, { id: "frz", name: "Freezer 3", parent_id: "room", type: "freezer", workspace_id: "w" }]);
    if (opts.url === "/api/v1/plate-groups/tree") return Promise.resolve({ roots: [{ id: "lib", name: "SAC1", plate_count: 0, children: [{ id: "g1", name: "Set 014", plate_count: 1, children: [] }] }] });
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
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
    expect(screen.getByTestId("columns")).toHaveTextContent("Barcode|Name|Set|Format|Where");
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
```

- [ ] **Step 2: Run** it — FAIL.

- [ ] **Step 3: Rewrite `plate-list.tsx`:**

```tsx
"use client";

import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { showError } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import type { ColDef } from "ag-grid-community";
import { FileUp, FlaskConical, Plus, Settings } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useGroupIndex } from "../hooks/use-plate-groups";
import { buildCustodyMap, useLoans } from "../hooks/use-plate-loans";
import { usePlates } from "../hooks/use-plates";
import { useStorageLocations } from "../hooks/use-storage-locations";
import {
  PLATE_CHIP_LABELS,
  PLATE_CHIP_ORDER,
  type PlateChipKey,
  type WhereTone,
  type Whereabouts,
  plateChipKeys,
  plateWhereabouts,
  whereText,
} from "../lib/plate-where";
import type { PlateStatus, PlateType, RegisteredPlate } from "../types/plates";
import { plateStatusLabels, plateTypeLabels } from "../types/plates";
import { CountChips } from "./count-chips";
import { OrgPlatePolicyDialog } from "./org-plate-policy-dialog";
import { RegisterPlateDialog } from "./register-plate-dialog";
import { RequestLoanDialog } from "./request-loan-dialog";

/** Filter sentinel: scope the plate list to the current user's own org. */
const MY_ORG = "__mine__";
/** Filter sentinel: no org scoping — show plates from every org (admin-only selector). */
const ALL_ORGS = "__all__";
/** Admin's last org choice survives navigation (P5). */
const ORG_STORAGE_KEY = "plates.org";

const PLATE_FORMATS = ["6", "12", "24", "48", "96", "384", "1536"] as const;

/** Spec X2: colour only exceptions. */
export const TONE_CLASS: Record<WhereTone, string> = {
  overdue: "font-medium text-destructive",
  loan: "text-warning",
  muted: "text-muted-foreground",
  normal: "",
};

interface PlateRow {
  plate: RegisteredPlate;
  where: Whereabouts;
  chips: Set<PlateChipKey>;
}

export function PlateList() {
  const router = useRouter();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [policyOpen, setPolicyOpen] = useState(false);
  const [loanBarcodes, setLoanBarcodes] = useState<string[] | null>(null);
  const [filterType, setFilterType] = useState<string>("__all__");
  const [filterStatus, setFilterStatus] = useState<string>("__all__");
  const [filterFormat, setFilterFormat] = useState<string>("__all__");
  const [filterOrg, setFilterOrg] = useState<string>(MY_ORG);
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const [chip, setChip] = useState<PlateChipKey | null>(null);

  const { data: me, isError: meFailed } = useCurrentUser();
  const isAdmin = me?.is_admin === true;
  const { data: orgs } = useOrgs();
  const memberName = useMemberNames();
  const { data: locations } = useStorageLocations();
  const orgNameById = useMemo(() => new Map((orgs ?? []).map((o) => [o.id, o.name])), [orgs]);
  // Open loans → plate_id custody lookup, for the Where column and the chips.
  const { data: openLoans } = useLoans({ status: "open" });
  const custodyByPlate = useMemo(() => buildCustodyMap(openLoans ?? []), [openLoans]);

  // Admins: restore the remembered org once we know they're an admin.
  useEffect(() => {
    if (!isAdmin) return;
    try {
      const stored = window.localStorage.getItem(ORG_STORAGE_KEY);
      if (stored) setFilterOrg(stored);
    } catch {
      /* storage unavailable */
    }
  }, [isAdmin]);
  const selectOrg = (v: string) => {
    setFilterOrg(v);
    try {
      window.localStorage.setItem(ORG_STORAGE_KEY, v);
    } catch {
      /* storage unavailable */
    }
  };

  // "My org" needs /me. If /me failed, fall back to un-filtered (All orgs)
  // rather than gating the list forever behind a query that will never run.
  const ownerOrgId =
    filterOrg === MY_ORG
      ? meFailed
        ? undefined
        : (me?.org_id ?? undefined)
      : filterOrg === ALL_ORGS
        ? undefined
        : filterOrg;
  const allOrgs = filterOrg === ALL_ORGS;
  const groupOrgIds = useMemo(
    () => (allOrgs ? (orgs ?? []).map((o) => o.id) : ownerOrgId ? [ownerOrgId] : []),
    [allOrgs, orgs, ownerOrgId],
  );
  const groupIndex = useGroupIndex(groupOrgIds);

  const {
    data: plates,
    isLoading,
    error,
  } = usePlates(
    {
      plate_type: filterType === "__all__" ? undefined : filterType,
      status: filterStatus === "__all__" ? undefined : filterStatus,
      format: filterFormat === "__all__" ? undefined : filterFormat,
      owner_org_id: ownerOrgId,
      tags: tagFilter.tagIds,
      tagLogic: tagFilter.tagLogic,
    },
    // Hold the fetch until /me resolves while "My org" is active — otherwise
    // the grid flashes all-orgs data during the identity load.
    { enabled: filterOrg !== MY_ORG || me !== undefined || meFailed },
  );

  useEffect(() => {
    if (meFailed && filterOrg === MY_ORG) {
      showError("Could not resolve your organization — showing all orgs");
    }
  }, [meFailed, filterOrg]);

  const rows = useMemo<PlateRow[] | undefined>(
    () =>
      plates?.map((plate) => {
        const where = plateWhereabouts(plate, custodyByPlate.get(plate.id), locations);
        return { plate, where, chips: plateChipKeys(plate, where) };
      }),
    [plates, custodyByPlate, locations],
  );
  const chipCounts = useMemo(() => {
    const counts = Object.fromEntries(PLATE_CHIP_ORDER.map((k) => [k, 0])) as Record<PlateChipKey, number>;
    for (const r of rows ?? []) for (const k of r.chips) counts[k] += 1;
    return counts;
  }, [rows]);
  const visibleRows = useMemo(
    () => (chip ? rows?.filter((r) => r.chips.has(chip)) : rows),
    [rows, chip],
  );

  const columnDefs = useMemo<ColDef<PlateRow>[]>(
    () => [
      {
        headerName: "Barcode",
        field: "plate.barcode",
        flex: 1,
        minWidth: 140,
        cellRenderer: ({ data }: { data: PlateRow | undefined }) =>
          data ? (
            <button
              type="button"
              className="font-mono text-sm text-primary hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                router.push(`/inventory/plates/${data.plate.id}`);
              }}
            >
              {data.plate.barcode}
            </button>
          ) : null,
      },
      { headerName: "Name", field: "plate.plate_label", flex: 1, minWidth: 160 },
      {
        headerName: "Set",
        flex: 1.2,
        minWidth: 160,
        valueGetter: (p) =>
          p.data?.plate.group_id ? (groupIndex.get(p.data.plate.group_id)?.path ?? "…") : "—",
      },
      { headerName: "Format", field: "plate.format", width: 90 },
      {
        headerName: "Where",
        flex: 1.4,
        minWidth: 220,
        valueGetter: (p) => (p.data ? whereText(p.data.where, memberName).text : ""),
        cellRenderer: ({ data }: { data: PlateRow | undefined }) => {
          if (!data) return null;
          const t = whereText(data.where, memberName);
          return (
            <span title={t.title} className={cn(TONE_CLASS[t.tone])}>
              {t.text}
            </span>
          );
        },
      },
      {
        headerName: "Owner",
        hide: !allOrgs,
        width: 160,
        valueGetter: (p) =>
          p.data?.plate.owner_org_id
            ? (orgNameById.get(p.data.plate.owner_org_id) ?? (orgs ? "Unknown org" : "—"))
            : "—",
      },
    ],
    [router, orgNameById, orgs, allOrgs, groupIndex, memberName],
  );

  const header = (
    <PageHeader title="Plates" subtitle="Which set, where it is, who has it.">
      {isAdmin ? (
        <Button variant="outline" onClick={() => setPolicyOpen(true)}>
          <Settings className="mr-2 h-4 w-4" />
          Org Policies
        </Button>
      ) : null}
      <Button variant="outline" onClick={() => router.push("/inventory/plates/import")}>
        <FileUp className="mr-2 h-4 w-4" />
        Import Data
      </Button>
      <Button onClick={() => setRegisterOpen(true)}>
        <Plus className="mr-2 h-4 w-4" />
        Register Plate
      </Button>
    </PageHeader>
  );

  if (error) {
    return (
      <div>
        {header}
        <ErrorState
          message="Failed to load plates. Is the backend running?"
          details={error.message}
        />
      </div>
    );
  }

  const filtered =
    chip !== null ||
    filterType !== "__all__" ||
    filterStatus !== "__all__" ||
    filterFormat !== "__all__" ||
    tagFilter.tagIds.length > 0;
  const total = rows?.length ?? 0;

  return (
    <div>
      {header}

      {/* Filter bar */}
      <div className="mb-3 flex flex-wrap gap-2">
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger className="w-[170px]">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All types</SelectItem>
            {(Object.keys(plateTypeLabels) as PlateType[]).map((t) => (
              <SelectItem key={t} value={t}>
                {plateTypeLabels[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All statuses</SelectItem>
            {(Object.keys(plateStatusLabels) as PlateStatus[]).map((s) => (
              <SelectItem key={s} value={s}>
                {plateStatusLabels[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterFormat} onValueChange={setFilterFormat}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="All formats" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All formats</SelectItem>
            {PLATE_FORMATS.map((f) => (
              <SelectItem key={f} value={f}>
                {f}-well
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {isAdmin ? (
          <Select value={filterOrg} onValueChange={selectOrg}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="My org" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={MY_ORG}>
                {me?.org_slug ? `My org (${me.org_slug})` : "My org"}
              </SelectItem>
              <SelectItem value={ALL_ORGS}>All orgs</SelectItem>
              {orgs?.map((o) => (
                <SelectItem key={o.id} value={o.id}>
                  {o.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}

        <TagFilter value={tagFilter} onChange={setTagFilter} />
      </div>

      {/* Summary strip */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {total.toLocaleString("en-US")} plate{total === 1 ? "" : "s"}
        </span>
        <CountChips
          chips={PLATE_CHIP_ORDER.map((key) => ({
            key,
            label: PLATE_CHIP_LABELS[key],
            count: chipCounts[key],
            tone: key === "overdue" ? ("destructive" as const) : undefined,
          }))}
          active={chip}
          onChange={(k) => setChip(k as PlateChipKey | null)}
        />
      </div>

      <DataGrid<PlateRow>
        rowData={visibleRows}
        columnDefs={columnDefs}
        loading={isLoading || !plates}
        height="calc(100vh - 20rem)"
        suppressFilters
        preferencesKey="plates"
        getRowId={(p) => p.data.plate.id}
        onRowClick={(row) => router.push(`/inventory/plates/${row.plate.id}`)}
        selectionToolbar={(selected) => (
          <>
            <span className="text-sm text-muted-foreground">{selected.length} selected</span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setLoanBarcodes(selected.map((r) => r.plate.barcode))}
            >
              Request loan ({selected.length})
            </Button>
          </>
        )}
        emptyState={
          filtered ? (
            <p className="p-6 text-sm text-muted-foreground">No plates match the current filters.</p>
          ) : (
            <EmptyState
              icon={FlaskConical}
              title="No plates"
              description="Register a plate to start tracking compound locations."
              action={{ label: "Register Plate", onClick: () => setRegisterOpen(true), icon: Plus }}
            />
          )
        }
      />

      <RegisterPlateDialog open={registerOpen} onOpenChange={setRegisterOpen} />
      <OrgPlatePolicyDialog open={policyOpen} onOpenChange={setPolicyOpen} />
      <RequestLoanDialog
        open={loanBarcodes !== null}
        onOpenChange={(o) => {
          if (!o) setLoanBarcodes(null);
        }}
        orgId={me?.org_id ?? undefined}
        initialBarcodes={loanBarcodes ?? undefined}
      />
    </div>
  );
}
```

Notes for the implementer: `field: "plate.barcode"` dot-paths work in AG Grid for nested data; `getRowId` keeps selection stable across chip toggles. The old `ConfirmDeleteDialog` / `useDeletePlate` imports are gone on purpose (P3).

- [ ] **Step 4: Run** the test — PASS. Biome the two files; `pnpm exec tsc --noEmit` clean.

---

### Task 10: Plate page rewrite

**Files:**
- Rewrite: `frontend/src/features/inventory/components/plate-detail.tsx` (keep `WellMapVisualization`, `MetaRow`, `ResolvedProject`, `ResolvedTemplate`, `ResolvedParentPlate`, `DerivePlateDialog` exactly as they are; delete `ResolvedStorageLocation` and `LoanHistoryCard`; rewrite `PlateDetail`)
- Test: create `frontend/src/features/inventory/components/plate-detail.test.tsx`

**Interfaces:**
- Consumes: Task 2 `useMemberNames`; Task 7 `RequestLoanDialog.initialBarcodes`; Task 8 `plateWhereabouts`, `Whereabouts`; existing `usePlate`, `usePlateChildren`, `useChangeStatus`, `useDeletePlate`, `useLoans`, `buildCustodyMap`, `LOAN_VARIANT`, `useStorageLocations`, `usePlateGroup`, `useOrgs`, `DetailShell`, `ConfirmDeleteDialog`, `DropdownMenu*` (`DropdownMenuItem` supports `variant="destructive"`), `CommentFeed`, `TagTable`, `AttachmentList`/`FileUploadZone`, `WellMappingDialog`, `downloadPlateLayout`.

- [ ] **Step 1: Write `plate-detail.test.tsx`:**

```tsx
import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { PlateDetail } from "./plate-detail";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
  usePathname: () => "/inventory/plates/p1",
}));
vi.mock("@duar-auth/nextjs", () => ({ useAuthzHasRole: () => true }));
// Side panels with their own data needs — out of scope for these assertions.
vi.mock("@/features/tagging/components/tag-table", () => ({ TagTable: () => null }));
vi.mock("@/features/attachment", () => ({ AttachmentList: () => null, FileUploadZone: () => null }));
const mocked = vi.mocked(customInstance);

beforeAll(() => {
  // Radix menus/dialogs in jsdom (verbatim from request-loan-dialog.test.tsx).
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const basePlate = {
  id: "p1", barcode: "0001", plate_label: "SAC1-014-0001", format: "384", plate_type: "assay", status: "stored",
  storage_location_id: "frz", owner_org_id: "A", group_id: "g1", registered_by: "u1", well_map: null, notes: null,
  project_id: null, template_id: null, parent_plate_id: null, workspace_id: "w",
};
const openLoan = {
  id: "l1", status: "open", owner_org_id: "A", borrower_org_id: "A", requested_by: "u1", due_date: "2000-01-01",
  created_at: "2026-08-01T00:00:00Z", closed_at: null, notes: null,
  items: [{ id: "i1", plate_id: "p1", barcode: "0001", plate_label: "x", status: "checked_out", status_changed_at: "2026-08-01T00:00:00Z" }],
};

function setup(plate = basePlate, loans: unknown[] = []) {
  mocked.mockReset();
  pushMock.mockReset();
  mocked.mockImplementation((opts: { url: string; method: string }) => {
    if (opts.url === "/api/v1/plates/p1" && opts.method === "DELETE") return Promise.resolve(undefined);
    if (opts.url === "/api/v1/plates/p1") return Promise.resolve(plate);
    if (opts.url === "/api/v1/plates/p1/children") return Promise.resolve([]);
    if (opts.url === "/api/v1/plate-loans") return Promise.resolve(loans);
    if (opts.url === "/api/v1/storage-locations")
      return Promise.resolve([{ id: "room", name: "Room 1148", parent_id: null, type: "room", workspace_id: "w" }, { id: "frz", name: "Freezer 3", parent_id: "room", type: "freezer", workspace_id: "w" }]);
    if (opts.url === "/api/v1/orgs") return Promise.resolve([{ id: "A", slug: "tamu", name: "TAMU" }]);
    if (opts.url === "/api/v1/user/workspace-members") return Promise.resolve([{ user_id: "u1", name: "Maia Young", email: "", avatar_url: null, role: "editor" }]);
    if (opts.url === "/api/v1/plate-groups/g1")
      return Promise.resolve({ group: { id: "g1", name: "Set 014", owner_org_id: "A" }, ancestors: [{ id: "lib", name: "SAC1" }], children: [], plate_count: 1, subtree_plate_count: 1 });
    if (opts.url === "/api/v1/comments") return Promise.resolve([]);
    if (opts.url === "/api/v1/plate-groups/tree") return Promise.resolve({ roots: [] });
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  return render(<PlateDetail plateId="p1" />, { wrapper });
}

describe("PlateDetail hero", () => {
  it("on loan: status · requester · since · due, link to the loan, no Request loan action", async () => {
    setup(basePlate, [openLoan]);
    const hero = await screen.findByTestId("plate-hero");
    await waitFor(() => expect(hero).toHaveTextContent("Maia Young"));
    expect(hero).toHaveTextContent("Checked Out");
    expect(hero).toHaveTextContent(/since Aug 1, 2026/);
    expect(hero).toHaveTextContent(/y overdue/);
    expect(screen.getByRole("link", { name: /view loan/i })).toHaveAttribute("href", "/inventory/loans/l1");
    expect(screen.queryByRole("button", { name: "Request loan" })).not.toBeInTheDocument();
  });
  it("in storage: full path; Request loan opens the dialog pre-filled with this barcode", async () => {
    setup();
    const hero = await screen.findByTestId("plate-hero");
    await waitFor(() => expect(hero).toHaveTextContent("In storage · Room 1148 › Freezer 3"));
    fireEvent.click(screen.getByRole("button", { name: "Request loan" }));
    const box = (await screen.findByLabelText("Barcodes")) as HTMLTextAreaElement;
    expect(box.value).toBe("0001");
  });
  it("depleted: muted terminal line, no Request loan", async () => {
    setup({ ...basePlate, status: "depleted" });
    const hero = await screen.findByTestId("plate-hero");
    expect(hero).toHaveTextContent("Depleted");
    expect(screen.queryByRole("button", { name: "Request loan" })).not.toBeInTheDocument();
  });
});

describe("PlateDetail body", () => {
  it("identity row links the set path; no Well Map card without wells; history lists loans", async () => {
    setup(basePlate, [openLoan]);
    expect(await screen.findByRole("link", { name: "SAC1 › Set 014" })).toHaveAttribute("href", "/inventory/plate-groups/g1");
    expect(screen.queryByText(/^Well Map/)).not.toBeInTheDocument();
    const history = await screen.findByTestId("loan-history");
    await waitFor(() => expect(history).toHaveTextContent("Maia Young"));
    expect(history.querySelector("a")).toHaveAttribute("href", "/inventory/loans/l1");
  });
  it("More → Delete → confirm deletes and returns to the list", async () => {
    setup();
    await screen.findByTestId("plate-hero");
    fireEvent.pointerDown(screen.getByRole("button", { name: /more/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /delete plate/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(mocked).toHaveBeenCalledWith(expect.objectContaining({ url: "/api/v1/plates/p1", method: "DELETE" })));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/inventory/plates"));
  });
});
```

If `fireEvent.pointerDown` does not open the Radix menu in your jsdom, copy the trigger pattern that already works in `src/shared/components/layout/header.test.tsx`. If the `ConfirmDeleteDialog` confirm button has a different accessible name, read `confirm-delete-dialog.tsx` and match it.

- [ ] **Step 2: Run** it — FAIL.

- [ ] **Step 3: Rewrite the `PlateDetail` component** (everything below the kept helpers). New imports beyond the current ones: `ConfirmDeleteDialog` from `@/shared/components/confirm-delete-dialog`, `DropdownMenuSeparator`, `useMemberNames` from `@/shared/hooks/use-workspace-members`, `formatDue`, `formatStatusLabel` from `@/shared/lib/status-variants`, `buildCustodyMap`, `useDeletePlate`, `usePlateGroup` from `../hooks/use-plate-groups`, `type Whereabouts, plateWhereabouts` from `../lib/plate-where`, `RequestLoanDialog`, `useMemo`, and lucide `ArrowLeftRight, Archive, MapPin, MoreHorizontal, Snowflake`. Remove imports that become unused (biome will list them).

```tsx
// ---------------------------------------------------------------------------
// Whereabouts hero — the one line a chemist came for
// ---------------------------------------------------------------------------

function WhereaboutsHero({
  where,
  memberName,
}: {
  where: Whereabouts;
  memberName: (id: string) => string;
}) {
  if (where.kind === "custody") {
    const due = formatDue(where.loan.due_date);
    return (
      <div
        data-testid="plate-hero"
        className={cn(
          "flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-sm",
          where.overdue ? "border-destructive/40 bg-destructive/5" : "border-warning/40 bg-warning/10",
        )}
      >
        <ArrowLeftRight className="h-4 w-4 shrink-0" />
        <span className="font-medium">{formatStatusLabel(where.item.status)}</span>
        <span>· {memberName(where.loan.requested_by)}</span>
        <span className="text-muted-foreground">
          · since {formatDate(where.item.status_changed_at)}
        </span>
        {due ? (
          <span
            title={`Due ${formatDate(where.loan.due_date)}`}
            className={cn(where.overdue ? "font-medium text-destructive" : "text-muted-foreground")}
          >
            · {due.label}
          </span>
        ) : null}
        <Link
          href={`/inventory/loans/${where.loan.id}`}
          className="ml-auto text-primary hover:underline"
        >
          View loan →
        </Link>
      </div>
    );
  }
  if (where.kind === "terminal") {
    return (
      <div data-testid="plate-hero" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Archive className="h-4 w-4 shrink-0" />
        {formatStatusLabel(where.status)}
      </div>
    );
  }
  if (where.kind === "location") {
    return (
      <div data-testid="plate-hero" className="flex items-center gap-2 text-sm">
        <Snowflake className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span>In storage · {where.fullPath}</span>
      </div>
    );
  }
  return (
    <div data-testid="plate-hero" className="flex items-center gap-2 text-sm text-muted-foreground">
      <MapPin className="h-4 w-4 shrink-0" />
      {formatStatusLabel(where.status)} · no storage location
    </div>
  );
}

// ---------------------------------------------------------------------------
// PlateDetail
// ---------------------------------------------------------------------------

interface PlateDetailProps {
  plateId: string;
}

export function PlateDetail({ plateId }: PlateDetailProps) {
  const router = useRouter();
  const query = usePlate(plateId);
  const plate = query.data;
  const { data: children } = usePlateChildren(plateId);
  // Every loan this plate appeared in (API orders desc): custody + history from one fetch.
  const { data: loans } = useLoans({ plate_id: plateId });
  const { data: locations } = useStorageLocations();
  const { data: orgs } = useOrgs();
  const groupQuery = usePlateGroup(plate?.group_id ?? undefined);
  const memberName = useMemberNames();
  const [wellMapOpen, setWellMapOpen] = useState(false);
  const [deriveOpen, setDeriveOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [loanBarcodes, setLoanBarcodes] = useState<string[] | null>(null);
  const changeStatus = useChangeStatus(plateId);
  const deletePlate = useDeletePlate();
  const canEditTags = useAuthzHasRole("editor");

  const custody = useMemo(() => buildCustodyMap(loans ?? []).get(plateId), [loans, plateId]);
  const where = useMemo(
    () => (plate ? plateWhereabouts(plate, custody, locations) : null),
    [plate, custody, locations],
  );
  const groupPath = groupQuery.data
    ? [...groupQuery.data.ancestors.map((a) => a.name), groupQuery.data.group.name].join(" › ")
    : null;
  const ownerName = plate?.owner_org_id
    ? orgs?.find((o) => o.id === plate.owner_org_id)?.name
    : undefined;

  const handleExport = async (id: string, format: "csv" | "xlsx") => {
    try {
      await downloadPlateLayout(id, format);
    } catch (e) {
      showError(e instanceof Error ? e.message : "Export failed");
    }
  };

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory/plates"
        backLabel="Back to Plates"
        title={(p) => p.barcode || "Plate"}
        notFoundMessage="Plate not found."
        actions={(p) => {
          const canLoan =
            where?.kind !== "custody" && p.status !== "depleted" && p.status !== "disposed";
          return (
            <>
              {canLoan ? (
                <Button size="sm" onClick={() => setLoanBarcodes([p.barcode])}>
                  Request loan
                </Button>
              ) : null}
              <Select
                value="__current__"
                onValueChange={(v) => {
                  if (v !== "__current__") changeStatus.mutate(v);
                }}
              >
                <SelectTrigger className="h-8 w-[150px] text-xs">
                  <SelectValue>Change Status</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__current__" disabled>
                    Change Status
                  </SelectItem>
                  {p.status === "registered" && (
                    <>
                      <SelectItem value="stored">Store</SelectItem>
                      <SelectItem value="in_use">Check Out</SelectItem>
                      <SelectItem value="disposed">Dispose</SelectItem>
                    </>
                  )}
                  {p.status === "in_use" && (
                    <>
                      <SelectItem value="stored">Return to Storage</SelectItem>
                      <SelectItem value="depleted">Mark Depleted</SelectItem>
                    </>
                  )}
                  {p.status === "stored" && (
                    <>
                      <SelectItem value="in_use">Check Out</SelectItem>
                      <SelectItem value="depleted">Mark Depleted</SelectItem>
                      <SelectItem value="disposed">Dispose</SelectItem>
                    </>
                  )}
                  {p.status === "depleted" && <SelectItem value="disposed">Dispose</SelectItem>}
                </SelectContent>
              </Select>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" aria-label="More actions">
                    <MoreHorizontal className="mr-1.5 h-3.5 w-3.5" />
                    More
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={() => setWellMapOpen(true)}
                    disabled={p.status === "disposed"}
                  >
                    Map wells
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push("/inventory/plates/import")}>
                    Import data
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport(p.id, "csv")}>
                    Export CSV — round-trippable
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport(p.id, "xlsx")}>
                    Export Excel (.xlsx)
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => setDeriveOpen(true)}
                    disabled={p.status === "disposed"}
                  >
                    Derive daughter plate
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onClick={() => setDeleteOpen(true)}>
                    Delete plate
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          );
        }}
      >
        {(p) => {
          const wellCount = p.well_map ? Object.keys(p.well_map).length : 0;
          return (
            <>
              <div className="-mt-3 flex flex-col gap-3">
                {where ? <WhereaboutsHero where={where} memberName={memberName} /> : null}
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  {p.group_id && !groupQuery.isError ? (
                    <Link
                      href={`/inventory/plate-groups/${p.group_id}`}
                      className="text-primary hover:underline"
                    >
                      {groupPath ?? "…"}
                    </Link>
                  ) : null}
                  <span className="text-muted-foreground">{p.format}-well</span>
                  <Badge variant="outline">
                    {plateTypeLabels[p.plate_type as PlateType] ?? p.plate_type}
                  </Badge>
                  {ownerName ? <span className="text-muted-foreground">{ownerName}</span> : null}
                  {p.plate_label ? (
                    <span className="text-muted-foreground">{p.plate_label}</span>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
                <div className="flex flex-col gap-6">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Details</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <MetaRow label="Project">
                        <ResolvedProject id={p.project_id ?? null} />
                      </MetaRow>
                      <MetaRow label="Template">
                        <ResolvedTemplate id={p.template_id ?? null} />
                      </MetaRow>
                      <MetaRow label="Parent Plate">
                        <ResolvedParentPlate id={p.parent_plate_id ?? null} />
                      </MetaRow>
                      <MetaRow label="Registered by">{memberName(p.registered_by)}</MetaRow>
                      {p.notes && (
                        <MetaRow label="Notes">
                          <span className="text-muted-foreground">{p.notes}</span>
                        </MetaRow>
                      )}
                    </CardContent>
                  </Card>

                  <TagTable entity="plates" entityId={plateId} canEdit={canEditTags} />

                  {children && children.length > 0 && (
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base">
                          Daughter Plates ({children.length})
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ul className="space-y-2">
                          {children.map((child) => (
                            <li key={child.id} className="flex items-center gap-3">
                              <Link
                                href={`/inventory/plates/${child.id}`}
                                className="font-mono text-sm text-primary hover:underline"
                              >
                                {child.barcode}
                              </Link>
                              <span className="text-sm text-muted-foreground">
                                {child.plate_label}
                              </span>
                              <StatusBadge status={child.status} className="ml-auto" />
                            </li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  )}

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Files</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <FileUploadZone entityType="plate" entityId={plateId} />
                      <AttachmentList entityType="plate" entityId={plateId} />
                    </CardContent>
                  </Card>
                </div>

                <div className="flex flex-col gap-6">
                  {wellCount > 0 && p.well_map ? (
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base">
                          Well Map{" "}
                          <span className="ml-1 text-sm font-normal text-muted-foreground">
                            ({wellCount} wells occupied)
                          </span>
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="overflow-auto">
                          <WellMapVisualization wellMap={p.well_map} format={p.format} />
                          <p className="mt-3 text-xs text-muted-foreground">
                            Colored wells have compound batches mapped. Hover a well for details.
                          </p>
                        </div>
                      </CardContent>
                    </Card>
                  ) : null}

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">History</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {loans && loans.length > 0 ? (
                        <ul className="divide-y rounded-md border" data-testid="loan-history">
                          {loans.map((loan) => {
                            const item = loan.items.find((i) => i.plate_id === plateId);
                            return (
                              <li key={loan.id}>
                                <Link
                                  href={`/inventory/loans/${loan.id}`}
                                  className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm hover:bg-accent"
                                >
                                  <span className="font-medium">
                                    {memberName(loan.requested_by)}
                                  </span>
                                  {item ? (
                                    <StatusBadge
                                      status={item.status}
                                      variant={LOAN_VARIANT[item.status]}
                                    />
                                  ) : null}
                                  <span className="text-muted-foreground">
                                    {formatDate(loan.created_at)}
                                    {loan.closed_at ? ` → ${formatDate(loan.closed_at)}` : ""}
                                  </span>
                                </Link>
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        <p className="text-sm text-muted-foreground">Never loaned.</p>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Comments</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <CommentFeed
                        scope={{ targetType: "plate", targetId: plateId }}
                        canWrite={canEditTags}
                      />
                    </CardContent>
                  </Card>
                </div>
              </div>
            </>
          );
        }}
      </DetailShell>

      {query.data && (
        <WellMappingDialog
          open={wellMapOpen}
          onOpenChange={setWellMapOpen}
          plateId={plateId}
          format={query.data.format}
          initialWellMap={query.data.well_map ?? null}
        />
      )}
      <DerivePlateDialog parentPlateId={plateId} open={deriveOpen} onOpenChange={setDeriveOpen} />
      <RequestLoanDialog
        open={loanBarcodes !== null}
        onOpenChange={(o) => {
          if (!o) setLoanBarcodes(null);
        }}
        orgId={plate?.owner_org_id ?? undefined}
        initialBarcodes={loanBarcodes ?? undefined}
      />
      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete plate?"
        description={`This will permanently delete plate "${plate?.barcode ?? ""}" (${plate?.plate_label ?? ""}). Well mappings will be lost.`}
        isPending={deletePlate.isPending}
        onConfirm={() =>
          deletePlate.mutate(plateId, { onSuccess: () => router.push("/inventory/plates") })
        }
      />
    </>
  );
}
```

- [ ] **Step 4: Run** the test — PASS. Biome the two files; `pnpm exec tsc --noEmit` clean.

---

## Wrap-up (orchestrator)

1. `pnpm vitest run` (whole suite), `pnpm exec tsc --noEmit`, `pnpm exec biome check` on every touched file.
2. Commit **S13** with an explicit pathspec: `format-date.*`, `use-workspace-members.*`, `lib/loan-verbs.*`, `lib/loan-summary.*`, `count-chips.tsx`, `loan-row.*`, `loan-page.*`, `app/(dashboard)/inventory/loans/[id]/page.tsx`, `loan-dashboard.*`, the `loan-card.*` deletions, `request-loan-dialog.*`, `comment-feed.*`.
3. Commit **S14**: `lib/storage-path.*`, `lib/plate-where.*`, `use-plate-groups.ts`, `plate-list.*`, `plate-detail.*`.
4. Browser verification against saclab-dev (loans open/history, a loan page with verbs, plates list with TAMU selected, a plate page on loan and one in storage), then one whole-branch review; spec sync note.
