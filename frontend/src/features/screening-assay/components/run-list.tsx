"use client";

import { useMemo } from "react";
import { FlaskConical } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { EmptyState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useRunsByProtocol } from "../hooks/use-runs";
import {
  PLATE_FORMAT_LABELS,
  type PlateFormat,
  type Run,
  type RunStatus,
} from "../types";

interface RunListProps {
  protocolId: string;
  onSelect?: (runId: string) => void;
}

function statusBadgeVariant(
  status: RunStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "approved":
      return "default";
    case "completed":
    case "in_progress":
      return "secondary";
    case "rejected":
      return "destructive";
    case "draft":
      return "outline";
  }
}

export function RunList({ protocolId, onSelect }: RunListProps) {
  const { data: runs, isLoading } = useRunsByProtocol(protocolId);

  const columnDefs = useMemo<ColDef<Run>[]>(
    () => [
      {
        headerName: "Run Date",
        field: "run_date",
        flex: 1,
        minWidth: 110,
        cellClass: "font-mono text-sm",
      },
      { headerName: "Plates", field: "plate_count", width: 80 },
      {
        headerName: "Format",
        field: "plate_format",
        width: 100,
        valueFormatter: (p) =>
          p.value
            ? PLATE_FORMAT_LABELS[p.value as PlateFormat] ?? p.value
            : "\u2014",
      },
      {
        headerName: "Status",
        field: "status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<Run>) => (
          <Badge variant={statusBadgeVariant(params.value as RunStatus)}>
            {params.value}
          </Badge>
        ),
      },
      {
        headerName: "Lock",
        field: "is_locked",
        width: 100,
        cellRenderer: (params: ICellRendererParams<Run>) => (
          <Badge variant={params.value ? "destructive" : "outline"}>
            {params.value ? "Locked" : "Unlocked"}
          </Badge>
        ),
      },
    ],
    []
  );

  return (
    <DataGrid<Run>
      rowData={runs}
      columnDefs={columnDefs}
      loading={isLoading}
      height="300px"
      suppressFilters
      onRowClick={onSelect ? (run) => onSelect(run.id) : undefined}
      emptyState={
        <EmptyState
          icon={FlaskConical}
          title="No runs"
          description="Create a run to start collecting screening data."
        />
      }
    />
  );
}
