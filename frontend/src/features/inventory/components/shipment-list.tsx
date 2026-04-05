"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Truck } from "lucide-react";
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
import { useShipments } from "../hooks/use-shipments";
import {
  SHIPMENT_STATUS_LABELS,
  type ShipmentStatus,
  type ShipmentSummary,
} from "../types/shipment";
import { CreateShipmentDialog } from "./create-shipment-dialog";

function statusBadgeVariant(
  status: ShipmentStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "delivered":
      return "default";
    case "shipped":
    case "in_transit":
      return "secondary";
    case "returned":
      return "destructive";
    case "preparing":
    default:
      return "outline";
  }
}

export function ShipmentListPage() {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [createOpen, setCreateOpen] = useState(false);

  const { data: shipments, isLoading } = useShipments(
    statusFilter || undefined
  );

  const columnDefs = useMemo<ColDef<ShipmentSummary>[]>(
    () => [
      {
        headerName: "Destination Org",
        field: "destination_org_id",
        flex: 1,
        minWidth: 160,
        cellClass: "font-mono text-sm",
        valueFormatter: (p) =>
          p.value
            ? `${String(p.value).slice(0, 8)}...`
            : "\u2014",
      },
      {
        headerName: "Carrier",
        field: "carrier",
        width: 130,
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "Tracking #",
        field: "tracking_number",
        width: 160,
        cellClass: "font-mono text-sm",
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "Status",
        field: "status",
        width: 130,
        cellRenderer: (params: ICellRendererParams<ShipmentSummary>) => (
          <Badge variant={statusBadgeVariant(params.value as ShipmentStatus)}>
            {SHIPMENT_STATUS_LABELS[params.value as ShipmentStatus] ??
              params.value}
          </Badge>
        ),
      },
      {
        headerName: "Items",
        field: "item_count",
        width: 80,
        type: "numericColumn",
      },
    ],
    []
  );

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Shipments</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage outbound sample shipments and chain-of-custody.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Truck className="mr-2 h-4 w-4" />
          New Shipment
        </Button>
      </div>

      {/* Status filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">Filter by status:</span>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All statuses</SelectItem>
            {(Object.keys(SHIPMENT_STATUS_LABELS) as ShipmentStatus[]).map(
              (s) => (
                <SelectItem key={s} value={s}>
                  {SHIPMENT_STATUS_LABELS[s]}
                </SelectItem>
              )
            )}
          </SelectContent>
        </Select>
      </div>

      {/* Grid */}
      <DataGrid<ShipmentSummary>
        rowData={shipments}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        onRowClick={(row) => router.push(`/inventory/shipments/${row.id}`)}
        emptyState={
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
            <Truck className="h-12 w-12 text-muted-foreground/40" />
            <h3 className="mt-4 text-lg font-semibold">No shipments</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Create the first shipment to get started.
            </p>
          </div>
        }
      />

      <CreateShipmentDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
