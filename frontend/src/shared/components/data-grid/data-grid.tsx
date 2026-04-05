"use client";

import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { AgGridReact, type AgGridReactProps } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  type ColDef,
  type RowClickedEvent,
  type GridReadyEvent,
  type SelectionChangedEvent,
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
  /** Render prop for selection toolbar. Shown above grid when rows are selected.
   *  Automatically enables rowSelection="multiple" on the grid. */
  selectionToolbar?: (selectedRows: TData[]) => ReactNode;
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
  selectionToolbar,
  ...rest
}: DataGridProps<TData>) {
  const gridRef = useRef<AgGridReact<TData>>(null);
  const [selectedRows, setSelectedRows] = useState<TData[]>([]);
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

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<TData>) => {
      setSelectedRows(event.api.getSelectedRows());
    },
    []
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
      {selectionToolbar && selectedRows.length > 0 ? (
        <div className="mb-2 flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2">
          {selectionToolbar(selectedRows)}
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
          onSelectionChanged={selectionToolbar ? handleSelectionChanged : undefined}
          rowSelection={selectionToolbar ? "multiple" : undefined}
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
