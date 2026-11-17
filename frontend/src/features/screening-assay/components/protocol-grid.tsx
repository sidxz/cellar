"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { StatusBadge } from "@/shared/components/status-badge";
import { formatDate, formatDateTime } from "@/shared/lib/format-date";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { TestTubes } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { compareProtocolDates } from "../lib/protocol-dates";
import { PROTOCOL_TYPE_LABELS, type Protocol, type ProtocolType } from "../types";
import { TargetChips } from "./target-chips";

interface ProtocolGridProps {
  protocols?: Protocol[];
  datesLoading?: boolean;
  datesError?: boolean;
  isLoading?: boolean;
  error?: Error | null;
  /** AG Grid quick-filter text (search box value). */
  quickFilterText?: string;
  isFiltered?: boolean;
  onSelect?: (protocolId: string) => void;
}

export function ProtocolGrid({
  protocols,
  isLoading,
  error,
  quickFilterText,
  onSelect,
  isFiltered = false,
  datesLoading = false,
  datesError = false,
}: ProtocolGridProps) {
  const columnDefs = useMemo<ColDef<Protocol>[]>(
    () => [
      {
        headerName: "Protocol",
        field: "name",
        flex: 2.5,
        minWidth: 300,
        tooltipField: "name",
        getQuickFilterText: (p) =>
          [p.data?.name, p.data?.code, ...(p.data?.aliases ?? []).map((a) => a.label)].join(" "),
        cellRenderer: ({ data }: ICellRendererParams<Protocol>) =>
          data ? (
            <div className="flex h-full min-w-0 flex-col justify-center gap-1 leading-tight">
              <Link
                href={`/assays/protocols/${data.id}`}
                onClick={(event) => event.stopPropagation()}
                className="truncate font-medium text-foreground hover:text-primary hover:underline focus-visible:underline"
              >
                {data.name}
              </Link>
              <span className="text-xs text-muted-foreground">
                <span className="tabular-nums">{data.code ?? "No code"}</span>
                <span className="mx-2">·</span>v{data.protocol_version}
              </span>
            </div>
          ) : null,
      },
      {
        headerName: "Type",
        field: "protocol_type",
        width: 140,
        valueFormatter: (p) => PROTOCOL_TYPE_LABELS[p.value as ProtocolType] ?? p.value,
      },
      {
        headerName: "Readouts",
        flex: 1,
        minWidth: 170,
        valueGetter: (p) =>
          p.data?.readout_definitions
            .map((r) => (r.unit ? `${r.name} (${r.unit})` : r.name))
            .join(", ") || "Not defined",
        tooltipValueGetter: (p) => p.value,
        cellRenderer: ({ value }: ICellRendererParams<Protocol>) => (
          <span className="block truncate text-sm text-foreground/75">{value}</span>
        ),
      },
      {
        headerName: "Targets",
        colId: "targets",
        valueGetter: (p) => p.data?.targets.map((t) => t.name).join(", ") ?? "",
        flex: 1,
        minWidth: 140,
        sortable: true,
        cellRenderer: (params: ICellRendererParams<Protocol>) => (
          <TargetChips targets={params.data?.targets} />
        ),
      },
      {
        headerName: "Created",
        field: "created_at",
        width: 135,
        sortable: true,
        comparator: (a, b, _a, _b, descending) => compareProtocolDates(a, b, descending),
        valueFormatter: (p) => formatDate(p.value) || "Unknown",
        tooltipValueGetter: (p) => formatDateTime(p.value) || "Creation date unavailable",
        cellClass: "text-sm tabular-nums",
      },
      {
        headerName: "Last run",
        field: "last_run_date",
        width: 135,
        sortable: true,
        initialSort: "desc",
        comparator: (a, b, _a, _b, descending) => compareProtocolDates(a, b, descending),
        valueFormatter: (p) =>
          p.value
            ? formatDate(p.value)
            : datesLoading
              ? "Loading…"
              : datesError || p.value === undefined
                ? "Unavailable"
                : "No runs",
        headerTooltip: "Latest recorded run date, across all run statuses",
        cellClass: "text-sm tabular-nums",
      },
      {
        headerName: "Status",
        field: "status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<Protocol>) => (
          <StatusBadge status={params.value} />
        ),
      },
    ],
    [datesLoading, datesError],
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
    <div className="protocol-directory-grid">
      <style>{`
        .protocol-directory-grid .ag-root-wrapper { border: 0; border-radius: 0 0 12px 12px; }
        .protocol-directory-grid .ag-header { background: color-mix(in srgb, var(--primary) 8%, var(--card)); border-top: 1px solid var(--border); border-bottom: 1px solid color-mix(in srgb, var(--primary) 20%, var(--border)); }
        .protocol-directory-grid .ag-header-cell { font-size: 12px; font-weight: 600; color: var(--foreground); }
        .protocol-directory-grid .ag-header-cell::after { display: none; }
        .protocol-directory-grid .ag-header-cell-resize::after { opacity: 0; width: 1px; }
        .protocol-directory-grid .ag-header-cell:hover .ag-header-cell-resize::after,
        .protocol-directory-grid .ag-header-cell:focus-within .ag-header-cell-resize::after { opacity: 1; }
        .protocol-directory-grid .ag-row { border-color: color-mix(in srgb, var(--border) 65%, transparent); }
        .protocol-directory-grid .ag-cell { display: flex; align-items: center; }
        .protocol-directory-grid .ag-cell-wrapper, .protocol-directory-grid .ag-cell-value { min-width: 0; width: 100%; }
      `}</style>
      <DataGrid<Protocol>
        rowData={protocols}
        columnDefs={columnDefs}
        loading={isLoading}
        height="clamp(360px, calc(100dvh - 355px), 900px)"
        rowHeight={66}
        headerHeight={42}
        getRowId={(p) => p.data.id}
        quickFilterText={quickFilterText}
        searchPlaceholder={false}
        suppressFilters
        onRowClick={onSelect ? (protocol) => onSelect(protocol.id) : undefined}
        emptyState={
          <EmptyState
            icon={TestTubes}
            title={isFiltered ? "No matching protocols" : "No protocols yet"}
            description={
              isFiltered
                ? "Try a different search or clear filters to broaden the list."
                : "Create or import a screening protocol to get started."
            }
          />
        }
      />
    </div>
  );
}
