"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Truck } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { OrgName } from "@/shared/components/entity-name";
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
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [createOpen, setCreateOpen] = useState(false);

  const { data: shipments, isLoading } = useShipments(
    statusFilter !== "all" ? statusFilter : undefined
  );

  const columnDefs = useMemo<ColDef<ShipmentSummary>[]>(
    () => [
      {
        headerName: "Destination",
        field: "destination_org_id",
        flex: 1,
        minWidth: 160,
        cellRenderer: (params: ICellRendererParams<ShipmentSummary>) =>
          params.value ? <OrgName id={params.value as string} /> : "\u2014",
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
      <PageHeader
        title="Shipments"
        subtitle="Manage outbound sample shipments and chain-of-custody."
      >
        <Button onClick={() => setCreateOpen(true)}>
          <Truck className="mr-2 h-4 w-4" />
          New Shipment
        </Button>
      </PageHeader>

      {/* Status filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">Filter by status:</span>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
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
          <EmptyState
            icon={Truck}
            title="No shipments"
            description="Create the first shipment to get started."
          />
        }
      />

      <CreateShipmentDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
