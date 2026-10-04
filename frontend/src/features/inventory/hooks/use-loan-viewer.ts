"use client";

import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useAuthzHasAction } from "@duar-auth/nextjs";
import { useMemo } from "react";
import { LOAN_APPROVE_ACTION, type LoanViewer } from "../lib/loan-verbs";

/** `/user/me` plus the authz token's loan-approval grant, for the loan verb and
 * inbox helpers. Memoised so it is a stable dependency. */
export function useLoanViewer(): LoanViewer | undefined {
  const { data: me } = useCurrentUser();
  const canApproveLoans = useAuthzHasAction(LOAN_APPROVE_ACTION);
  return useMemo(() => me && { ...me, canApproveLoans }, [me, canApproveLoans]);
}
