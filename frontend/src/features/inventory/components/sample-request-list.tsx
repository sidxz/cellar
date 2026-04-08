"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ClipboardList, Plus } from "lucide-react";
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
import { useSampleRequests } from "../hooks/use-sample-requests";
import {
  SAMPLE_REQUEST_STATUS_LABELS,
  REQUEST_PRIORITY_LABELS,
  type SampleRequest,
  type SampleRequestStatus,
  type RequestPriority,
} from "../types/sample-request";
import { CreateSampleRequestDialog } from "./create-sample-request-dialog";

export function SampleRequestListPage() {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [createOpen, setCreateOpen] = useState(false);

  const { data: requests, isLoading } = useSampleRequests(
    statusFilter === "all" ? undefined : statusFilter
  );

  const columnDefs = useMemo<ColDef<SampleRequest>[]>(
    () => [
      {
        headerName: "Priority",
        field: "priority",
        width: 110,
        cellRenderer: (params: ICellRendererParams<SampleRequest>) => (
          <PriorityBadge
            priority={params.value}
            label={REQUEST_PRIORITY_LABELS[params.value as RequestPriority] ?? params.value}
          />
        ),
      },
      {
        headerName: "Compound",
        field: "molecule_id",
        flex: 1,
        minWidth: 160,
        cellRenderer: (params: ICellRendererParams<SampleRequest>) =>
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
        headerName: "Status",
        field: "status",
        width: 120,
        cellRenderer: (params: ICellRendererParams<SampleRequest>) => (
          <StatusBadge
            status={params.value}
            label={SAMPLE_REQUEST_STATUS_LABELS[params.value as SampleRequestStatus] ?? params.value}
          />
        ),
      },
      {
        headerName: "Requested",
        field: "id",
        width: 130,
        sortable: false,
        filter: false,
        valueGetter: () => "\u2014",
      },
    ],
    []
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sample Requests"
        subtitle="Track and manage sample requests across the workspace."
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
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            {Object.entries(SAMPLE_REQUEST_STATUS_LABELS).map(
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
      <DataGrid<SampleRequest>
        rowData={requests}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        onRowClick={(req) => router.push(`/inventory/sample-requests/${req.id}`)}
        emptyState={
          <EmptyState
            icon={ClipboardList}
            title="No sample requests"
            description="No requests match the current filter."
          />
        }
      />

      <CreateSampleRequestDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
    </div>
  );
}
