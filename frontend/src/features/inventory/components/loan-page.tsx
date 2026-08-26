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
