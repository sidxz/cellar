"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FlaskRound, Plus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { StatusBadge, PriorityBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { MoleculeName } from "@/shared/components/entity-name";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useSynthesisRequests } from "../hooks/use-synthesis-requests";
import {
  SYNTHESIS_REQUEST_STATUS_LABELS,
  type SynthesisRequestSummary,
  type SynthesisRequestStatus,
} from "../types/synthesis-request";
import { CreateSynthesisRequestDialog } from "./create-synthesis-request-dialog";

export function SynthesisRequestListPage() {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [createOpen, setCreateOpen] = useState(false);

  const { data: requests, isLoading } = useSynthesisRequests(
    statusFilter === "all" ? undefined : { status: statusFilter }
  );

  const columnDefs = useMemo<ColDef<SynthesisRequestSummary>[]>(
    () => [
      {
        headerName: "Priority",
        field: "priority",
        width: 110,
        cellRenderer: (params: ICellRendererParams<SynthesisRequestSummary>) => (
          <PriorityBadge priority={params.value ?? ""} />
        ),
      },
      {
        headerName: "Compound",
        field: "molecule_id",
        flex: 1,
        minWidth: 160,
        cellRenderer: (params: ICellRendererParams<SynthesisRequestSummary>) =>
          params.value ? <MoleculeName id={params.value as string} /> : "\u2014",
      },
      {
        headerName: "Amount",
        width: 120,
        valueGetter: (p) =>
          p.data ? `${p.data.amount_value} ${p.data.amount_unit}` : "",
      },
      {
        headerName: "Purpose",
        field: "purpose",
        flex: 2,
        minWidth: 160,
        cellClass: "text-muted-foreground",
      },
      {
        headerName: "Purity Target",
        field: "target_purity",
        width: 120,
        valueFormatter: (p) =>
          p.value != null ? `${p.value}%` : "\u2014",
      },
      {
        headerName: "Status",
        field: "status",
        width: 160,
        cellRenderer: (
          params: ICellRendererParams<SynthesisRequestSummary>
        ) => (
          <StatusBadge
            status={params.value}
            label={SYNTHESIS_REQUEST_STATUS_LABELS[params.value as SynthesisRequestStatus] ?? params.value}
          />
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Synthesis Requests"
        subtitle="Track and manage synthesis requests across the workspace."
      >
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Request
        </Button>
      </PageHeader>

      {/* Status filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">Filter by status:</span>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            {Object.entries(SYNTHESIS_REQUEST_STATUS_LABELS).map(
              ([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              )
            )}
          </SelectContent>
        </Select>
      </div>

      {/* Grid */}
      <DataGrid<SynthesisRequestSummary>
        rowData={requests}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        onRowClick={(req) =>
          router.push(`/inventory/synthesis-requests/${req.id}`)
        }
        emptyState={
          <EmptyState
            icon={FlaskRound}
            title="No synthesis requests"
            description="No requests match the current filter."
          />
        }
      />

      <CreateSynthesisRequestDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
    </div>
  );
}
