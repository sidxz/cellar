import type { MeResponse } from "@/shared/lib/api/model";
import {
  LoanItemStatus,
  type LoanVerb,
  type PlateLoan,
  type PlateLoanItem,
} from "../hooks/use-plate-loans";

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
