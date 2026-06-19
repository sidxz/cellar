"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { StatusBadge } from "@/shared/components/status-badge";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { TestTubes } from "lucide-react";
import { useMemo } from "react";
import { PROTOCOL_TYPE_LABELS, type Protocol, type ProtocolType } from "../types";
import { TargetChips } from "./target-chips";

interface ProtocolGridProps {
  protocols?: Protocol[];
  isLoading?: boolean;
  error?: Error | null;
  /** AG Grid quick-filter text (search box value). */
  quickFilterText?: string;
  onSelect?: (protocolId: string) => void;
}

export function ProtocolGrid({
  protocols,
  isLoading,
  error,
  quickFilterText,
  onSelect,
}: ProtocolGridProps) {
  const columnDefs = useMemo<ColDef<Protocol>[]>(
    () => [
      { headerName: "Name", field: "name", flex: 1, minWidth: 180 },
      {
        headerName: "Type",
        field: "protocol_type",
        width: 140,
        valueFormatter: (p) => PROTOCOL_TYPE_LABELS[p.value as ProtocolType] ?? p.value,
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
        headerName: "Targets",
        field: "targets",
        flex: 1,
        minWidth: 140,
        sortable: false,
        getQuickFilterText: (p) => (p.value ?? []).map((t: { name: string }) => t.name).join(" "),
        cellRenderer: (params: ICellRendererParams<Protocol>) => (
          <TargetChips targets={params.data?.targets} />
        ),
      },
      {
        headerName: "Status",
        field: "status",
        width: 100,
        cellRenderer: (params: ICellRendererParams<Protocol>) => (
          <StatusBadge status={params.value} />
        ),
      },
    ],
    [],
  );

  if (error) {
    return (
      <ErrorState
        message="Failed to load protocols. Is the backend running?"
        details={error.message}
      />
    );
  }

  return (
    <DataGrid<Protocol>
      rowData={protocols}
      columnDefs={columnDefs}
      loading={isLoading}
      height="calc(100vh - 264px)"
      quickFilterText={quickFilterText}
      searchPlaceholder={false}
      suppressFilters
      onRowClick={onSelect ? (protocol) => onSelect(protocol.id) : undefined}
      emptyState={
        <EmptyState
          icon={TestTubes}
          title="No protocols"
          description="Create your first screening protocol to get started."
        />
      }
    />
  );
}
