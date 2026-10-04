import { canEdit } from "@/shared/hooks/use-current-user";
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

/** Duar action the server's owner-side loan check needs (backend
 * `LOAN_APPROVE_ACTION`); workspace admins don't. */
export const LOAN_APPROVE_ACTION = "cellar:approve_loan";

/** The `/user/me` identity plus whether the authz token grants
 * {@link LOAN_APPROVE_ACTION}. */
export type LoanViewer = MeResponse & { canApproveLoans: boolean };

/** Mirrors `require_loan_authority`: an editor or above who is a workspace
 * admin, or in the owner org and holding the loan-approval action. */
export function ownerAuthority(loan: PlateLoan, me: LoanViewer | undefined): boolean {
  return (
    !!me &&
    canEdit(me) &&
    (me.is_admin === true || (me.org_id === loan.owner_org_id && me.canApproveLoans))
  );
}

/** Mirrors `_require_borrower_authority`: an editor or above who is a
 * workspace admin or in the borrower org. */
export function borrowerAuthority(loan: PlateLoan, me: MeResponse | undefined): boolean {
  return !!me && canEdit(me) && (me.is_admin === true || me.org_id === loan.borrower_org_id);
}

export function eligibleItems(loan: PlateLoan, verb: LoanVerb): PlateLoanItem[] {
  return loan.items.filter((i) => VERB_SOURCES[verb].includes(i.status));
}

/** Verbs the viewer may press that have ≥ 1 eligible item, owner verbs first. */
export function availableVerbs(loan: PlateLoan, me: LoanViewer | undefined): LoanVerb[] {
  const verbs = [
    ...(ownerAuthority(loan, me) ? OWNER_VERBS : []),
    ...(borrowerAuthority(loan, me) ? BORROWER_VERBS : []),
  ];
  return verbs.filter((v) => eligibleItems(loan, v).length > 0);
}
