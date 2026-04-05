"use client";

import { useMemo } from "react";
import { TestTubes } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useProtocols } from "../hooks/use-protocols";
import {
  PROTOCOL_TYPE_LABELS,
  type Protocol,
  type ProtocolStatus,
  type ProtocolType,
} from "../types";

interface ProtocolListProps {
  onSelect?: (protocolId: string) => void;
}

function statusBadgeVariant(
  status: ProtocolStatus
): "default" | "outline" | "destructive" {
  switch (status) {
    case "active":
      return "default";
    case "draft":
      return "outline";
    case "retired":
      return "destructive";
  }
}

export function ProtocolList({ onSelect }: ProtocolListProps) {
  const { data: protocols, isLoading, error } = useProtocols();

  const columnDefs = useMemo<ColDef<Protocol>[]>(
    () => [
      { headerName: "Name", field: "name", flex: 1, minWidth: 180 },
      {
        headerName: "Type",
        field: "protocol_type",
        width: 140,
        valueFormatter: (p) =>
          PROTOCOL_TYPE_LABELS[p.value as ProtocolType] ?? p.value,
      },
      {
        headerName: "Version",
        field: "protocol_version",
        width: 90,
        cellClass: "font-mono text-sm",
        valueFormatter: (p) => `v${p.value}`,
      },
      {
        headerName: "Readouts",
        width: 100,
        valueGetter: (p) => p.data?.readout_definitions.length ?? 0,
      },
      {
        headerName: "Status",
        field: "status",
        width: 100,
        cellRenderer: (params: ICellRendererParams<Protocol>) => (
          <Badge variant={statusBadgeVariant(params.value as ProtocolStatus)}>
            {params.value}
          </Badge>
        ),
      },
    ],
    []
  );

  if (error) {
    return (
      <div className="rounded-lg border border-dashed border-destructive/50 p-8 text-center">
        <p className="text-sm text-destructive">
          Failed to load protocols. Is the backend running?
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
      </div>
    );
  }

  return (
    <DataGrid<Protocol>
      rowData={protocols}
      columnDefs={columnDefs}
      loading={isLoading}
      height="400px"
      suppressFilters
      onRowClick={onSelect ? (protocol) => onSelect(protocol.id) : undefined}
      emptyState={
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <TestTubes className="h-12 w-12 text-muted-foreground/40" />
          <h3 className="mt-4 text-lg font-semibold">No protocols</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Create your first screening protocol to get started.
          </p>
        </div>
      }
    />
  );
}
