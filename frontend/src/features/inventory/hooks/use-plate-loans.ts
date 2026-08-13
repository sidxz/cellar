"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import {
  type LoanItemResponse,
  LoanItemStatus,
  type LoanResponse,
  LoanStatus,
  type RequestLoanBody,
} from "@/shared/lib/api/model";
import type { BadgeVariant } from "@/shared/lib/status-variants";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LOANS_KEY, PLATES_KEY } from "./query-keys";

export type PlateLoan = LoanResponse;
export type PlateLoanItem = LoanItemResponse;
export { LoanItemStatus, LoanStatus };

export type LoanFilters = {
  status?: string;
  mine?: boolean;
  owner_org_id?: string;
  borrower_org_id?: string;
  plate_id?: string;
  overdue?: boolean;
};

/** List loans visible to the caller. Booleans are only sent when true — the
 * backend defaults `mine`/`overdue` to false, so omitting keeps URLs clean. */
export function useLoans(filters?: LoanFilters, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: [...LOANS_KEY, filters ?? {}],
    queryFn: ({ signal }) => {
      const params: Record<string, string | boolean> = {};
      if (filters?.status) params.status = filters.status;
      if (filters?.owner_org_id) params.owner_org_id = filters.owner_org_id;
      if (filters?.borrower_org_id) params.borrower_org_id = filters.borrower_org_id;
      if (filters?.plate_id) params.plate_id = filters.plate_id;
      if (filters?.mine) params.mine = true;
      if (filters?.overdue) params.overdue = true;
      return customInstance<PlateLoan[]>({
        url: `${API_V1}/plate-loans`,
        method: "GET",
        params,
        signal,
      });
    },
    enabled: opts?.enabled ?? true,
  });
}

export function useLoan(loanId: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: [...LOANS_KEY, loanId],
    queryFn: ({ signal }) =>
      customInstance<PlateLoan>({
        url: `${API_V1}/plate-loans/${loanId}`,
        method: "GET",
        signal,
      }),
    enabled: opts?.enabled ?? true,
  });
}

export function useRequestLoan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RequestLoanBody) =>
      customInstance<PlateLoan>({
        url: `${API_V1}/plate-loans`,
        method: "POST",
        data: body,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: LOANS_KEY });
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess("Loan requested");
    },
  });
}

export type LoanVerb =
  | "approve"
  | "deny"
  | "confirm-out"
  | "request-return"
  | "confirm-in"
  | "cancel";

const LOAN_VERB_MESSAGES: Record<LoanVerb, string> = {
  approve: "Items approved",
  deny: "Items denied",
  "confirm-out": "Hand-out confirmed",
  "request-return": "Return requested",
  "confirm-in": "Return confirmed",
  cancel: "Items cancelled",
};

/** Single mutation covering all six item-transition verbs — callers pass the
 * verb rather than the codebase growing a hook per state-machine edge. */
export function useLoanItemsAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      loanId,
      verb,
      itemIds,
    }: {
      loanId: string;
      verb: LoanVerb;
      itemIds?: string[];
    }) =>
      customInstance<PlateLoan>({
        url: `${API_V1}/plate-loans/${loanId}/items:${verb}`,
        method: "POST",
        data: { item_ids: itemIds ?? null },
      }),
    onSuccess: (_data, { verb }) => {
      qc.invalidateQueries({ queryKey: LOANS_KEY });
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess(LOAN_VERB_MESSAGES[verb]);
    },
  });
}

const ACTIVE_LOAN_ITEM_STATUSES = new Set<LoanItemStatus>([
  LoanItemStatus.requested,
  LoanItemStatus.approved,
  LoanItemStatus.checked_out,
  LoanItemStatus.return_pending,
]);

/** plate_id -> the loan/item holding it in active custody, for surfaces that
 * need to flag "this plate is out on loan" (Task 11). Only OPEN loans count;
 * a closed loan's items are always terminal already, checked explicitly so
 * that invariant isn't silently assumed. Two active items on the same plate
 * shouldn't happen (server-enforced) — last-write-wins if it ever does. */
export function buildCustodyMap(
  loans: PlateLoan[],
): Map<string, { loan: PlateLoan; item: PlateLoanItem }> {
  const map = new Map<string, { loan: PlateLoan; item: PlateLoanItem }>();
  for (const loan of loans) {
    if (loan.status !== LoanStatus.open) continue;
    for (const item of loan.items) {
      if (ACTIVE_LOAN_ITEM_STATUSES.has(item.status)) {
        map.set(item.plate_id, { loan, item });
      }
    }
  }
  return map;
}

/** Loan-domain colours for status words the global map either lacks (open/
 * closed) or owns with a differently-meaning colour (approved=success,
 * returned/cancelled=error). Undefined → StatusBadge falls back to the map.
 * Shared by every loan surface (dashboard cards, plate-detail loan history,
 * plate-list custody chip) so the same status never renders two colours. */
export const LOAN_VARIANT: Record<string, BadgeVariant> = {
  open: "default",
  closed: "outline",
  approved: "default",
  returned: "success",
  cancelled: "outline",
};
