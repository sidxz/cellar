"use client";

import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useHashTab } from "@/shared/hooks/use-hash-tab";
import type { MeResponse } from "@/shared/lib/api/model";
import { showError } from "@/shared/lib/toast";
import type { UseQueryResult } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { LoanStatus, type PlateLoan, useLoans } from "../hooks/use-plate-loans";
import { LoanCard } from "./loan-card";
import { RequestLoanDialog } from "./request-loan-dialog";

function LoanList({
  query,
  context,
  me,
}: {
  query: UseQueryResult<PlateLoan[]>;
  context: "mine" | "approvals" | "all";
  me: MeResponse | undefined;
}) {
  if (query.isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (query.error)
    return (
      <p className="text-sm text-destructive">
        {query.error instanceof Error ? query.error.message : "Failed to load loans"}
      </p>
    );
  const loans = query.data ?? [];
  if (loans.length === 0) return <p className="text-sm text-muted-foreground">No loans.</p>;
  return (
    <div className="flex flex-col gap-3">
      {loans.map((loan) => (
        <LoanCard key={loan.id} loan={loan} context={context} me={me} />
      ))}
    </div>
  );
}

export function LoanDashboard() {
  const { data: me, isError: meFailed } = useCurrentUser();
  const isAdmin = me?.is_admin === true;
  const orgId = me?.org_id ?? undefined;
  const showApprovals = isAdmin || !!orgId;
  const [tab, setTab] = useHashTab("mine");
  const [overdue, setOverdue] = useState(false);
  const [requestOpen, setRequestOpen] = useState(false);

  useEffect(() => {
    if (meFailed) showError("Could not load your identity — the Approvals tab is unavailable.");
  }, [meFailed]);

  const mine = useLoans({ mine: true });
  const approvals = useLoans(
    { status: LoanStatus.open, owner_org_id: isAdmin ? undefined : orgId },
    { enabled: showApprovals },
  );
  const all = useLoans({ overdue: overdue || undefined });

  return (
    <div className="flex flex-col gap-4 p-6">
      <PageHeader title="Loans" subtitle="Plate checkout requests and approvals">
        <Button onClick={() => setRequestOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Request loan
        </Button>
      </PageHeader>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="mine">My requests</TabsTrigger>
          {showApprovals ? <TabsTrigger value="approvals">Approvals</TabsTrigger> : null}
          <TabsTrigger value="all">All</TabsTrigger>
        </TabsList>

        <TabsContent value="mine" className="mt-4">
          <LoanList query={mine} context="mine" me={me} />
        </TabsContent>

        {showApprovals ? (
          <TabsContent value="approvals" className="mt-4">
            <LoanList query={approvals} context="approvals" me={me} />
          </TabsContent>
        ) : null}

        <TabsContent value="all" className="mt-4">
          <div className="mb-3 flex items-center gap-2">
            <Switch id="overdue-only" checked={overdue} onCheckedChange={setOverdue} />
            <Label htmlFor="overdue-only">Overdue only</Label>
          </div>
          <LoanList query={all} context="all" me={me} />
        </TabsContent>
      </Tabs>

      <RequestLoanDialog open={requestOpen} onOpenChange={setRequestOpen} orgId={orgId} />
    </div>
  );
}
