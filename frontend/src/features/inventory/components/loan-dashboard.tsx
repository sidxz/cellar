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
    () => sortOpenLoans(chip ? openLoans.filter((l) => loanInboxKeys(l, me).has(chip)) : openLoans),
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
        headerName: "Search text",
        // quick-filter only: barcodes + notes (migrated loans carry the legacy
        // requester name in notes, so "Maia" still finds her history).
        hide: true,
        valueGetter: (p) =>
          [...(p.data?.items.map((i) => i.barcode) ?? []), p.data?.notes ?? ""].join(" "),
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
            searchPlaceholder="Search requester, set, barcode or notes…"
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
