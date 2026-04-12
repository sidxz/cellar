"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FlaskConical } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { StatusBadge } from "@/shared/components/status-badge";
import { EmptyState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useRunsByProtocol } from "../../hooks/use-runs";
import {
  PLATE_FORMAT_LABELS,
  RUN_STATUS_LABELS,
  type PlateFormat,
  type Protocol,
  type Run,
} from "../../types";

interface RunsTabProps {
  protocol: Protocol;
  protocolId: string;
}

function zPrimeBadge(qcMetrics: Record<string, unknown> | null) {
  const zp = qcMetrics?.z_prime as number | undefined;
  if (zp == null) return <span className="text-muted-foreground">&mdash;</span>;
  if (zp >= 0.5)
    return (
      <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
        {zp.toFixed(2)}
      </Badge>
    );
  if (zp >= 0)
    return (
      <Badge variant="outline" className="border-yellow-500/40 text-yellow-400">
        {zp.toFixed(2)}
      </Badge>
    );
  return (
    <Badge variant="outline" className="border-red-500/40 text-red-400">
      {zp.toFixed(2)}
    </Badge>
  );
}

export function RunsTab({ protocol, protocolId }: RunsTabProps) {
  const router = useRouter();
  const { data: runs, isLoading } = useRunsByProtocol(protocolId);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const filteredRuns = useMemo(() => {
    if (!runs) return [];
    if (statusFilter === "all") return runs;
    return runs.filter((r) => r.status === statusFilter);
  }, [runs, statusFilter]);

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
        headerName: "Z\u2032",
        field: "qc_metrics",
        width: 90,
        cellRenderer: (params: ICellRendererParams<Run>) =>
          zPrimeBadge(params.value),
      },
      {
        headerName: "Status",
        field: "status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<Run>) => (
          <StatusBadge status={params.value} />
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            {Object.entries(RUN_STATUS_LABELS).map(([v, l]) => (
              <SelectItem key={v} value={v}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <DataGrid<Run>
        rowData={filteredRuns}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        suppressFilters
        onRowClick={(run) => router.push(`/assays/runs/${run.id}`)}
        emptyState={
          <EmptyState
            icon={FlaskConical}
            title="No runs"
            description="Create a run to start collecting screening data."
          />
        }
      />
    </div>
  );
}
