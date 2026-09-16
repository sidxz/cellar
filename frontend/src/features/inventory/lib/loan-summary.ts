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
    else
      byId.set(item.group_id, {
        id: item.group_id,
        name: item.group_name ?? "Ungrouped",
        count: 1,
      });
  }
  const sets = [...byId.values()];
  if (ungrouped > 0) sets.push({ id: null, name: "Ungrouped", count: ungrouped });
  return sets;
}

/** "Set 5, Set 27 +1" — first two grouped set names, then a +n. "" when no item is grouped. */
export function setSummary(loan: PlateLoan): string {
  const names = loanSets(loan)
    .filter((s) => s.id !== null)
    .map((s) => s.name);
  if (names.length === 0) return "";
  const head = names.slice(0, 2).join(", ");
  return names.length > 2 ? `${head} +${names.length - 2}` : head;
}

export const ITEM_STATUS_ORDER: LoanItemStatus[] = [
  LoanItemStatus.requested,
  LoanItemStatus.approved,
  LoanItemStatus.checked_out,
  LoanItemStatus.return_pending,
  LoanItemStatus.returned,
  LoanItemStatus.denied,
  LoanItemStatus.cancelled,
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
  | "approve"
  | "hand_out"
  | "check_in"
  | "awaiting_approval"
  | "ready_for_pickup"
  | "overdue"
  | "mine";

export const INBOX_ORDER: InboxKey[] = [
  "approve",
  "hand_out",
  "check_in",
  "awaiting_approval",
  "ready_for_pickup",
  "overdue",
  "mine",
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
export function loanInboxKeys(
  loan: PlateLoan,
  me: MeResponse | undefined,
  today: string = todayISO(),
): Set<InboxKey> {
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
export function inboxCounts(
  loans: PlateLoan[],
  me: MeResponse | undefined,
  today: string = todayISO(),
): Record<InboxKey, number> {
  const counts = Object.fromEntries(INBOX_ORDER.map((k) => [k, 0])) as Record<InboxKey, number>;
  for (const loan of loans) for (const key of loanInboxKeys(loan, me, today)) counts[key] += 1;
  return counts;
}

/** Cross-org context from the viewer's side; null for a self-checkout. */
export function orgLine(
  loan: PlateLoan,
  me: MeResponse | undefined,
  orgName: (id: string) => string,
): string | null {
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
    if (a.due_date && b.due_date && a.due_date !== b.due_date)
      return a.due_date < b.due_date ? -1 : 1;
    if (a.due_date && !b.due_date) return -1;
    if (!a.due_date && b.due_date) return 1;
    return a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0;
  });
}
