"use client";

import { useMemo, useState } from "react";
import { TestTubes } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useProjects } from "@/features/research-organization/hooks/use-projects";
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

const ALL_PROJECTS = "__all__";

export function ProtocolList({ onSelect }: ProtocolListProps) {
  const [projectFilter, setProjectFilter] = useState<string>(ALL_PROJECTS);
  const { data: projects } = useProjects();
  const { data: protocols, isLoading, error } = useProtocols(
    projectFilter !== ALL_PROJECTS ? projectFilter : undefined
  );

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
      <ErrorState message="Failed to load protocols. Is the backend running?" details={error.message} />
    );
  }

  return (
    <div className="space-y-3">
      {/* Project filter */}
      {projects && projects.length > 0 && (
        <div className="flex items-center gap-3">
          <span className="shrink-0 text-sm text-muted-foreground">
            Project:
          </span>
          <Select value={projectFilter} onValueChange={setProjectFilter}>
            <SelectTrigger className="w-[220px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_PROJECTS}>All projects</SelectItem>
              {projects.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <DataGrid<Protocol>
        rowData={protocols}
        columnDefs={columnDefs}
        loading={isLoading}
        height="400px"
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
    </div>
  );
}
