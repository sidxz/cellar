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
import { Search } from "lucide-react";
import { Input } from "@/shared/components/ui/input";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useGridPreferences } from "@/shared/hooks/use-grid-preferences";
import { chemVaultTheme } from "./ag-grid-theme";
import { ExportToolbar, type ExcelEnhancer } from "./export-toolbar";

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
  /** Optional enhancer for Excel exports — adds images, extra sheets, etc. */
  excelEnhancer?: ExcelEnhancer;
  /** When provided, persists column state (width, order, visibility) to localStorage. */
  preferencesKey?: string;
  /** Render prop for selection toolbar. Shown above grid when rows are selected.
   *  Automatically enables rowSelection="multiple" on the grid. */
  selectionToolbar?: (selectedRows: TData[]) => ReactNode;
  /** Enable multi-row selection without rendering a built-in toolbar.
   *  When true, prepends the checkbox column and sets rowSelection="multiple".
   *  Consumers track selection via onSelectionChanged. */
  enableMultiSelect?: boolean;
  /** When true, multi-select is enabled (rowSelection="multiple") but the
   *  auto-prepended checkbox column is not rendered. Use when you want to
   *  host the checkbox inside an existing column via
   *  `checkboxSelection: true` / `headerCheckboxSelection: true`. */
  suppressSelectColumn?: boolean;
  /** Placeholder for the quick-filter search bar. Set to false to hide. */
  searchPlaceholder?: string | false;
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
  excelEnhancer,
  preferencesKey,
  selectionToolbar,
  enableMultiSelect,
  suppressSelectColumn,
  searchPlaceholder = "Filter...",
  ...rest
}: DataGridProps<TData>) {
  const selectionEnabled = !!selectionToolbar || !!enableMultiSelect;
  const {
    onSelectionChanged: consumerOnSelectionChanged,
    rowSelection: _rowSelectionFromRest,
    ...restWithoutSelection
  } = rest;
  void _rowSelectionFromRest;
  const gridRef = useRef<AgGridReact<TData>>(null);
  const [quickFilter, setQuickFilter] = useState("");
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

  // Inject header tooltips (so clipped headers show full name on hover) and
  // prepend the selection checkbox column when a selection toolbar is wired.
  const finalColumnDefs = useMemo<ColDef<TData>[]>(() => {
    const withTooltips = columnDefs.map((c) =>
      c.headerTooltip == null && typeof c.headerName === "string"
        ? { ...c, headerTooltip: c.headerName }
        : c
    );
    if (!selectionEnabled || suppressSelectColumn) return withTooltips;
    const selectCol: ColDef<TData> = {
      colId: "__select__",
      pinned: "left",
      lockPosition: "left",
      lockPinned: true,
      width: 45,
      maxWidth: 45,
      minWidth: 45,
      resizable: false,
      sortable: false,
      filter: false,
      suppressMovable: true,
      headerCheckboxSelection: true,
      checkboxSelection: true,
    };
    return [selectCol, ...withTooltips];
  }, [columnDefs, selectionEnabled, suppressSelectColumn]);

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
      consumerOnSelectionChanged?.(event);
    },
    [consumerOnSelectionChanged]
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
      {(searchPlaceholder !== false || (exportFilename && rowData?.length)) ? (
        <div className="mb-2 flex items-center gap-2">
          {searchPlaceholder !== false && (
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={searchPlaceholder}
                value={quickFilter}
                onChange={(e) => setQuickFilter(e.target.value)}
                className="h-9 pl-8"
              />
            </div>
          )}
          <div className="ml-auto">
            {exportFilename && rowData?.length ? (
              <ExportToolbar gridRef={gridRef} filename={exportFilename} excelEnhancer={excelEnhancer} />
            ) : null}
          </div>
        </div>
      ) : null}
      {selectionToolbar && !enableMultiSelect && selectedRows.length > 0 ? (
        <div className="mb-2 flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2">
          {selectionToolbar(selectedRows)}
        </div>
      ) : null}
      <div style={{ height, width: "100%" }}>
        <AgGridReact<TData>
          ref={gridRef}
          theme={chemVaultTheme}
          rowData={rowData ?? []}
          columnDefs={finalColumnDefs}
          defaultColDef={defaultColDef}
          onRowClicked={onRowClick ? handleRowClicked : undefined}
          onGridReady={handleGridReady}
          onSelectionChanged={selectionEnabled ? handleSelectionChanged : consumerOnSelectionChanged}
          rowSelection={selectionEnabled ? "multiple" : undefined}
          suppressRowClickSelection={selectionEnabled ? true : undefined}
          tooltipShowDelay={300}
          onColumnResized={hasPrefs ? prefs.onColumnChanged(gridRef) : undefined}
          onColumnMoved={hasPrefs ? prefs.onColumnChanged(gridRef) : undefined}
          onColumnVisible={hasPrefs ? prefs.onColumnChanged(gridRef) : undefined}
          rowClass={onRowClick ? "cursor-pointer" : undefined}
          quickFilterText={quickFilter || undefined}
          suppressCellFocus
          animateRows={false}
          {...restWithoutSelection}
        />
      </div>
    </div>
  );
}
