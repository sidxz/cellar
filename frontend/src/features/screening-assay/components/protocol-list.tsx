"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { SearchInput } from "@/shared/components/search-input";
import { StatusBadge } from "@/shared/components/status-badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { TestTubes } from "lucide-react";
import { useMemo, useState } from "react";
import { useProtocols } from "../hooks/use-protocols";
import { PROTOCOL_TYPE_LABELS, type Protocol, type ProtocolType } from "../types";
import { TargetChips } from "./target-chips";

interface ProtocolListProps {
  onSelect?: (protocolId: string) => void;
  /** When provided, locks the list to this project (hides the project filter). */
  projectId?: string;
}

const ALL_PROJECTS = "__all__";

export function ProtocolList({ onSelect, projectId }: ProtocolListProps) {
  const [search, setSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState<string>(ALL_PROJECTS);
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const { data: projects } = useProjects();
  const effectiveProjectId =
    projectId ?? (projectFilter !== ALL_PROJECTS ? projectFilter : undefined);
  const {
    data: protocols,
    isLoading,
    error,
  } = useProtocols(effectiveProjectId, {
    tags: tagFilter.tagIds,
    tagLogic: tagFilter.tagLogic,
  });

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
        // Without this the quick filter indexes the object array as
        // "[object Object]" and target names are unsearchable.
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
    <div className="space-y-3">
      {/* Search + Project filter + Tag filter */}
      <div className="flex items-center gap-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search protocols..."
          className="max-w-sm flex-1"
        />
        <TagFilter value={tagFilter} onChange={setTagFilter} />
        {!projectId && projects && projects.length > 0 && (
          <>
            <span className="shrink-0 text-sm text-muted-foreground">Project:</span>
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
          </>
        )}
      </div>

      <DataGrid<Protocol>
        rowData={protocols}
        columnDefs={columnDefs}
        loading={isLoading}
        // Fill the viewport below the page header, tabs, and filter row.
        height="calc(100vh - 264px)"
        quickFilterText={search}
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
    </div>
  );
}
