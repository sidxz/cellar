"use client";

import { useCallback, useMemo, useRef, type ReactNode } from "react";
import { AgGridReact, type AgGridReactProps } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  type ColDef,
  type RowClickedEvent,
  type GridReadyEvent,
} from "ag-grid-community";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useGridPreferences } from "@/shared/hooks/use-grid-preferences";
import { chemVaultTheme } from "./ag-grid-theme";
import { ExportToolbar } from "./export-toolbar";

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
  /** When provided, renders CSV + Excel export buttons above the grid */
  exportFilename?: string;
  /** When provided, persists column state (width, order, visibility) to localStorage. */
  preferencesKey?: string;
}

export function DataGrid<TData = unknown>({
  rowData,
  columnDefs,
  loading,
  emptyState,
  onRowClick,
  height = "400px",
  suppressFilters = false,
  exportFilename,
  preferencesKey,
  ...rest
}: DataGridProps<TData>) {
  const gridRef = useRef<AgGridReact<TData>>(null);
  const prefs = useGridPreferences(preferencesKey ?? "__unused__");
  const hasPrefs = !!preferencesKey;
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

  const handleGridReady = useCallback(
    (event: GridReadyEvent<TData>) => {
      if (hasPrefs) {
        prefs.applyState(gridRef);
      } else {
        event.api.sizeColumnsToFit();
      }
    },
    [hasPrefs, prefs, gridRef]
  );

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
    <div>
      {exportFilename && rowData?.length ? (
        <div className="mb-2 flex justify-end">
          <ExportToolbar gridRef={gridRef} filename={exportFilename} />
        </div>
      ) : null}
      <div style={{ height, width: "100%" }}>
        <AgGridReact<TData>
          ref={gridRef}
          theme={chemVaultTheme}
          rowData={rowData ?? []}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          onRowClicked={onRowClick ? handleRowClicked : undefined}
          onGridReady={handleGridReady}
          onColumnResized={hasPrefs ? prefs.onColumnChanged(gridRef) : undefined}
          onColumnMoved={hasPrefs ? prefs.onColumnChanged(gridRef) : undefined}
          onColumnVisible={hasPrefs ? prefs.onColumnChanged(gridRef) : undefined}
          rowClass={onRowClick ? "cursor-pointer" : undefined}
          suppressCellFocus
          animateRows={false}
          {...rest}
        />
      </div>
    </div>
  );
}
