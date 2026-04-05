"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ClipboardList, Plus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
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

function statusVariant(
  s: SampleRequestStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (s) {
    case "fulfilled":
      return "default";
    case "approved":
    case "preparing":
      return "secondary";
    case "rejected":
    case "cancelled":
      return "destructive";
    default:
      return "outline";
  }
}

function priorityVariant(
  p: RequestPriority
): "default" | "secondary" | "destructive" | "outline" {
  switch (p) {
    case "critical":
      return "destructive";
    case "urgent":
      return "secondary";
    default:
      return "outline";
  }
}

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
          <Badge variant={priorityVariant(params.value as RequestPriority)}>
            {REQUEST_PRIORITY_LABELS[params.value as RequestPriority] ??
              params.value}
          </Badge>
        ),
      },
      {
        headerName: "Molecule ID",
        field: "molecule_id",
        flex: 1,
        minWidth: 160,
        cellClass: "font-mono text-sm",
        valueFormatter: (p) =>
          p.value ? `${String(p.value).slice(0, 8)}\u2026` : "\u2014",
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
          <Badge variant={statusVariant(params.value as SampleRequestStatus)}>
            {SAMPLE_REQUEST_STATUS_LABELS[
              params.value as SampleRequestStatus
            ] ?? params.value}
          </Badge>
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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Sample Requests</h1>
          <p className="mt-1 text-muted-foreground">
            Track and manage sample requests across the workspace.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Request
        </Button>
      </div>

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
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
            <ClipboardList className="h-12 w-12 text-muted-foreground/40" />
            <h3 className="mt-4 text-lg font-semibold">No sample requests</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              No requests match the current filter.
            </p>
          </div>
        }
      />

      <CreateSampleRequestDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
    </div>
  );
}
