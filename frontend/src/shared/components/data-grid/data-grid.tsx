"use client";

import { useCallback, useMemo, type ReactNode } from "react";
import { AgGridReact, type AgGridReactProps } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  type ColDef,
  type RowClickedEvent,
  type GridReadyEvent,
} from "ag-grid-community";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { chemVaultTheme } from "./ag-grid-theme";

ModuleRegistry.registerModules([AllCommunityModule]);

export interface DataGridProps<TData = unknown>
  extends Omit<AgGridReactProps<TData>, "theme" | "rowData" | "columnDefs"> {
  rowData: TData[] | undefined;
  columnDefs: ColDef<TData>[];
  loading?: boolean;
  /** Rendered when rowData is empty (not loading) */
  emptyState?: ReactNode;
  /** Navigate on row click — receives the row data */
  onRowClick?: (data: TData) => void;
  /** Fixed grid height. Default: "400px" */
  height?: string | number;
  /** Suppress built-in column filters. Default: false */
  suppressFilters?: boolean;
}

export function DataGrid<TData = unknown>({
  rowData,
  columnDefs,
  loading,
  emptyState,
  onRowClick,
  height = "400px",
  suppressFilters = false,
  ...rest
}: DataGridProps<TData>) {
  const defaultColDef = useMemo<ColDef<TData>>(
    () => ({
      sortable: true,
      resizable: true,
      filter: !suppressFilters,
      suppressMovable: true,
      minWidth: 80,
    }),
    [suppressFilters]
  );

  const handleRowClicked = useCallback(
    (event: RowClickedEvent<TData>) => {
      if (!onRowClick || !event.data) return;
      // Don't navigate if clicking on an action button
      const target = event.event?.target as HTMLElement | null;
      if (target?.closest("button, a, [role='button']")) return;
      onRowClick(event.data);
    },
    [onRowClick]
  );

  const handleGridReady = useCallback((event: GridReadyEvent<TData>) => {
    event.api.sizeColumnsToFit();
  }, []);

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (!rowData?.length && emptyState) {
    return <>{emptyState}</>;
  }

  return (
    <div style={{ height, width: "100%" }}>
      <AgGridReact<TData>
        theme={chemVaultTheme}
        rowData={rowData ?? []}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        onRowClicked={onRowClick ? handleRowClicked : undefined}
        onGridReady={handleGridReady}
        rowClass={onRowClick ? "cursor-pointer" : undefined}
        suppressCellFocus
        animateRows={false}
        {...rest}
      />
    </div>
  );
}
