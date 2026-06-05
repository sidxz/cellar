"use client";

import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState } from "@/shared/components/empty-state";
import { StatusBadge } from "@/shared/components/status-badge";
import { Badge } from "@/shared/components/ui/badge";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { FlaskConical } from "lucide-react";
import { useMemo, useState } from "react";
import { useRunsByProtocol } from "../hooks/use-runs";
import { PLATE_FORMAT_LABELS, type PlateFormat, type Run } from "../types";

interface RunListProps {
  protocolId: string;
  onSelect?: (runId: string) => void;
}

export function RunList({ protocolId, onSelect }: RunListProps) {
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const { data: runs, isLoading } = useRunsByProtocol(protocolId, {
    tags: tagFilter.tagIds,
    tagLogic: tagFilter.tagLogic,
  });

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
          p.value ? (PLATE_FORMAT_LABELS[p.value as PlateFormat] ?? p.value) : "\u2014",
      },
      {
        headerName: "Status",
        field: "status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<Run>) => <StatusBadge status={params.value} />,
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
    [],
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <TagFilter value={tagFilter} onChange={setTagFilter} />
      </div>
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
    </div>
  );
}
