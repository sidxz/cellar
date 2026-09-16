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
