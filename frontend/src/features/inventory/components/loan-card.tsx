"use client";

import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { useOrgs } from "@/shared/hooks/use-orgs";
import type { MeResponse } from "@/shared/lib/api/model";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import {
  LOAN_VARIANT,
  LoanItemStatus,
  LoanStatus,
  type LoanVerb,
  type PlateLoan,
} from "../hooks/use-plate-loans";
import { useLoanItemsAction } from "../hooks/use-plate-loans";

/** Item statuses each verb may act on — the single source of truth for which
 * items are "eligible" for a verb, mirrored from the server state machine. */
const VERB_SOURCES: Record<LoanVerb, LoanItemStatus[]> = {
  approve: [LoanItemStatus.requested],
  deny: [LoanItemStatus.requested],
  "confirm-out": [LoanItemStatus.approved],
  "request-return": [LoanItemStatus.checked_out],
  "confirm-in": [LoanItemStatus.return_pending],
  cancel: [LoanItemStatus.requested, LoanItemStatus.approved],
};

const VERB_LABELS: Record<LoanVerb, string> = {
  approve: "Approve",
  deny: "Deny",
  "confirm-out": "Confirm hand-out",
  "request-return": "Request return",
  "confirm-in": "Confirm return",
  cancel: "Cancel",
};

const OWNER_VERBS: LoanVerb[] = ["approve", "deny", "confirm-out", "confirm-in"];
const BORROWER_VERBS: LoanVerb[] = ["request-return", "cancel"];

function todayISO(): string {
  // Local calendar day, not UTC day — past-due calculation must match input dates.
  return new Date().toLocaleDateString("en-CA");
}

export interface LoanCardProps {
  loan: PlateLoan;
  context: "mine" | "approvals" | "all";
  me: MeResponse | undefined;
}

export function LoanCard({ loan, context, me }: LoanCardProps) {
  const { data: orgs } = useOrgs();
  const action = useLoanItemsAction();
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const orgName = (id: string) => orgs?.find((o) => o.id === id)?.name ?? "Unknown org";
  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  // Locked UX: exactly two verb arms — owner verbs on Approvals, borrower
  // verbs on My requests. The All tab is read-only. Server enforces authority;
  // admin visibility gap tracked in docs/backlog/loan-approvals-admin-visibility.md.
  const showOwner = context === "approvals";
  const showBorrower = context === "mine";
  const verbs = [...(showOwner ? OWNER_VERBS : []), ...(showBorrower ? BORROWER_VERBS : [])];

  const overdue = loan.status === LoanStatus.open && !!loan.due_date && loan.due_date < todayISO();

  const runVerb = (verb: LoanVerb) => {
    const eligible = loan.items.filter((i) => VERB_SOURCES[verb].includes(i.status));
    const targets = checked.size ? eligible.filter((i) => checked.has(i.id)) : eligible;
    if (targets.length === 0) return;
    action.mutate(
      { loanId: loan.id, verb, itemIds: targets.map((i) => i.id) },
      { onSuccess: () => setChecked(new Set()) },
    );
  };

  return (
    <div className="rounded-md border bg-card p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="flex items-center gap-1.5 font-medium">
          {orgName(loan.borrower_org_id)}
          <ArrowRight className="h-4 w-4 text-muted-foreground" />
          {orgName(loan.owner_org_id)}
        </span>
        <StatusBadge status={loan.status} variant={LOAN_VARIANT[loan.status]} />
        {loan.due_date ? (
          <span
            className={`text-sm ${overdue ? "font-medium text-destructive" : "text-muted-foreground"}`}
          >
            Due {loan.due_date}
          </span>
        ) : null}
        {loan.requested_by === me?.user_id ? (
          <span className="text-sm text-muted-foreground">Requested by you</span>
        ) : null}
      </div>
      {loan.notes ? <p className="mt-1 text-sm text-muted-foreground">{loan.notes}</p> : null}

      <Table className="mt-3">
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" />
            <TableHead>Barcode</TableHead>
            <TableHead>Plate</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loan.items.map((item) => (
            <TableRow key={item.id}>
              <TableCell>
                <Checkbox
                  checked={checked.has(item.id)}
                  onCheckedChange={() => toggle(item.id)}
                  aria-label={`Select ${item.barcode}`}
                />
              </TableCell>
              <TableCell className="font-mono text-xs">{item.barcode}</TableCell>
              <TableCell>{item.plate_label}</TableCell>
              <TableCell>
                <StatusBadge status={item.status} variant={LOAN_VARIANT[item.status]} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {verbs.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {verbs.map((verb) => {
            const eligible = loan.items.filter((i) => VERB_SOURCES[verb].includes(i.status));
            if (eligible.length === 0) return null;
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
                onClick={() => runVerb(verb)}
              >
                {VERB_LABELS[verb]} ({count})
              </Button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
