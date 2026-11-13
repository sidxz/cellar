"use client";

import { StructureThumbnail } from "@/shared/components/chemistry/structure-thumbnail";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EntityLink } from "@/shared/components/entity-link";
import { Badge } from "@/shared/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { cn } from "@/shared/lib/utils";
import type {
  CellKeyDownEvent,
  ColDef,
  ColGroupDef,
  FullWidthCellKeyDownEvent,
  GridApi,
  ICellRendererParams,
  RowClassParams,
  RowClickedEvent,
} from "ag-grid-community";
import { TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import type { SelectionState } from "../lib/curve-selection";
import {
  type CellStatus,
  type ResultRow,
  STATUS_ORDER,
  type WindowCell,
  shiftDirection,
  worstStatus,
} from "../lib/melt-results";
import { WELL_TYPE_LABELS, type WellType } from "../types";

type Col = ColDef<ResultRow> | ColGroupDef<ResultRow>;
type Params = ICellRendererParams<ResultRow>;

const ROW_HEIGHT = 36;
const GROUP_HEADER_HEIGHT = 32;
const DIFFERS_TEXT = "Step count differs from the reference";
// AG Grid's row colours are unlayered CSS, so row-level utilities need `!`.
const SELECTED_ROW = "bg-primary/10! shadow-[inset_3px_0_0_var(--primary)]";
const MUTED_ROW = "text-muted-foreground!";
const NUMERIC = "text-right tabular-nums";
const SEARCH = "Find sample, position or batch";
// Only the identity columns feed the search box; numbers and status do not.
const NOT_SEARCHED = () => "";

const STATUS: Record<
  CellStatus,
  { label: string; variant: "secondary" | "warning" | "outline" | "ghost"; className?: string }
> = {
  reference: { label: "Reference", variant: "secondary" },
  several_steps: { label: "Several steps", variant: "warning" },
  no_step: { label: "No step", variant: "warning" },
  no_reference: { label: "No reference", variant: "warning" },
  provisional: {
    label: "Provisional",
    variant: "outline",
    className: "border-dashed text-muted-foreground",
  },
  reviewed: { label: "Reviewed", variant: "ghost", className: "px-0 text-muted-foreground" },
};

const fmtTm = (v: number | null | undefined) => (v == null ? "" : v.toFixed(1));

/** `+1.4`, `−8.5` (true minus), `0.0`. */
export function formatDelta(d: number): string {
  const r = Number(d.toFixed(1));
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toFixed(1)}`;
}

/** Blue at or above +threshold (stabilising), red at or below −threshold,
 *  muted inside; the sign says the same without colour. */
function deltaTint(d: number, threshold: number): string {
  const dir = shiftDirection(d, threshold);
  if (dir === "up") return "font-semibold text-blue-700 dark:text-blue-300";
  if (dir === "down") return "font-semibold text-red-700 dark:text-red-300";
  return "text-muted-foreground";
}

function SampleCell({ row }: { row: ResultRow }) {
  const { registrationNumber, moleculeId, batchSuffix, smiles, label } = row.identity;
  if (registrationNumber) {
    const id = moleculeId ? (
      <EntityLink type="compound" id={moleculeId} label={registrationNumber} />
    ) : (
      <span className="font-mono text-sm">{registrationNumber}</span>
    );
    return (
      <span
        className="flex h-full items-center gap-1 truncate"
        title={[registrationNumber, batchSuffix && `·${batchSuffix}`].filter(Boolean).join("")}
      >
        {smiles ? (
          <Tooltip>
            {/* EntityLink takes no trigger props or ref, so a span carries them. */}
            <TooltipTrigger asChild>
              <span className="inline-flex">{id}</span>
            </TooltipTrigger>
            <TooltipContent
              side="right"
              sideOffset={6}
              collisionPadding={12}
              className="border bg-popover p-1.5 text-popover-foreground shadow-lg"
            >
              <div className="rounded-sm bg-white p-1">
                <StructureThumbnail smiles={smiles} size={160} />
              </div>
            </TooltipContent>
          </Tooltip>
        ) : (
          id
        )}
        {batchSuffix && (
          <span className="font-mono text-xs text-muted-foreground">{`·${batchSuffix}`}</span>
        )}
      </span>
    );
  }
  const text = label ?? row.position;
  if (row.isSample) {
    return (
      <span className="block truncate" title={`${text} (unregistered)`}>
        {text}
      </span>
    );
  }
  if (row.wellType === "reference")
    return (
      <span className="truncate" title={text}>
        {text}
      </span>
    );
  return (
    <span className="flex items-baseline gap-1.5 truncate" title={text}>
      <span className="truncate">{text}</span>
      <span className="text-xs">
        {(WELL_TYPE_LABELS[row.wellType as WellType] ?? row.wellType).toLowerCase()}
      </span>
    </span>
  );
}

/** A reference's own step review in the shown windows: provisional if any is. */
function referenceReview(row: ResultRow, windowNames: readonly string[]): string | null {
  const reviews = windowNames.map((n) => row.cells[n]?.review);
  if (reviews.includes("provisional")) return "Provisional";
  return reviews.includes("reviewed") ? "Reviewed" : null;
}

function StatusCell({ row, windowNames }: { row: ResultRow; windowNames: readonly string[] }) {
  const status = worstStatus(row, windowNames);
  const differs = windowNames.some((n) => row.cells[n]?.differs);
  const review = status === "reference" ? referenceReview(row, windowNames) : null;
  return (
    <span className="flex h-full items-center gap-1.5">
      {status && (
        <Badge variant={STATUS[status].variant} className={STATUS[status].className}>
          {review ? `${STATUS[status].label} · ${review}` : STATUS[status].label}
        </Badge>
      )}
      {differs && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span role="img" aria-label={DIFFERS_TEXT} className="inline-flex text-warning">
              <TriangleAlert className="size-3.5" />
            </span>
          </TooltipTrigger>
          <TooltipContent>{DIFFERS_TEXT}</TooltipContent>
        </Tooltip>
      )}
    </span>
  );
}

function windowColumns(name: string, threshold: number, grouped: boolean): ColDef<ResultRow>[] {
  const cell = (r: ResultRow | undefined): WindowCell | undefined => r?.cells[name];
  return [
    {
      colId: `${name}:tm`,
      headerName: "Tm (°C)",
      width: 80,
      headerClass: "ag-right-aligned-header",
      cellClass: NUMERIC,
      getQuickFilterText: NOT_SEARCHED,
      valueGetter: (p) => cell(p.data)?.tm ?? null,
      valueFormatter: (p) => fmtTm(p.value),
    },
    {
      colId: `${name}:delta`,
      headerName: "ΔTm (°C)",
      width: 90,
      headerClass: "ag-right-aligned-header",
      getQuickFilterText: NOT_SEARCHED,
      valueGetter: (p) =>
        p.data?.wellType === "reference" ? null : (cell(p.data)?.deltaTm ?? null),
      valueFormatter: (p) =>
        p.data?.wellType === "reference" ? "—" : p.value == null ? "" : formatDelta(p.value),
      cellClass: (p) =>
        cn(NUMERIC, p.data?.isSample && p.value != null && deltaTint(p.value as number, threshold)),
    },
  ];
}

const statusRank = (s: CellStatus | null) =>
  s === "reference" ? -1 : s === null ? STATUS_ORDER.length : STATUS_ORDER.indexOf(s);

/** Grid height that fits the rows up to 560 px, then scrolls. */
const gridHeight = (rows: number, grouped: boolean) =>
  Math.min(560, 48 + ROW_HEIGHT * rows + (grouped ? GROUP_HEADER_HEIGHT : 0));

/** The results of a run's temperature windows, one row per position: the
 *  references pinned, then samples by largest |ΔTm|, then the rest. Doubles as
 *  the position picker: rows select with click, Shift (range) and Ctrl/Cmd. */
export function MeltResultsGrid({
  rows,
  windowNames,
  threshold,
  doseUnit,
  selection,
  onRowClick,
}: {
  rows: { pinned: ResultRow[]; body: ResultRow[] };
  windowNames: readonly string[];
  threshold: number;
  doseUnit: string;
  selection: SelectionState;
  onRowClick: (
    wellId: string,
    mods: { shift: boolean; toggle: boolean },
    order: readonly string[],
  ) => void;
}) {
  const compare = windowNames.length > 1;
  const columnDefs = useMemo<Col[]>(() => {
    const identity: ColDef<ResultRow>[] = [
      {
        colId: "sample",
        headerName: "Sample",
        flex: 1,
        minWidth: 180,
        valueGetter: (p) => p.data?.sampleText ?? "",
        getQuickFilterText: (p) =>
          p.data
            ? [p.data.sampleText, p.data.identity.label, p.data.identity.batchSuffix]
                .filter(Boolean)
                .join(" ")
            : "",
        cellRenderer: (p: Params) => (p.data ? <SampleCell row={p.data} /> : null),
      },
      {
        colId: "position",
        headerName: "Position",
        width: 110,
        valueGetter: (p) => p.data?.position,
      },
      {
        colId: "conc",
        headerName: `Conc. (${doseUnit})`,
        width: 90,
        headerClass: "ag-right-aligned-header",
        cellClass: NUMERIC,
        getQuickFilterText: NOT_SEARCHED,
        valueGetter: (p) => p.data?.concentration ?? null,
        valueFormatter: (p) => (p.value == null ? "" : String(p.value)),
      },
    ];
    if (windowNames.length === 0) return identity;
    const values: Col[] = compare
      ? windowNames.map((n) => ({
          headerName: n,
          children: windowColumns(n, threshold, true),
        }))
      : windowColumns(windowNames[0], threshold, false);
    return [
      ...identity,
      ...values,
      {
        colId: "status",
        headerName: "Status",
        width: 170,
        getQuickFilterText: NOT_SEARCHED,
        valueGetter: (p) => (p.data ? statusRank(worstStatus(p.data, windowNames)) : null),
        cellRenderer: (p: Params) =>
          p.data ? <StatusCell row={p.data} windowNames={windowNames} /> : null,
      },
    ];
  }, [windowNames, compare, threshold, doseUnit]);

  // Rules, not getRowClass: AG Grid re-applies rules (adding and removing
  // classes) when they change, so the highlight follows the selection.
  const rowClassRules = useMemo(
    () => ({
      [SELECTED_ROW]: (p: RowClassParams<ResultRow>) =>
        !!p.data && selection.selected.has(p.data.wellId),
      [MUTED_ROW]: (p: RowClassParams<ResultRow>) =>
        !!p.data && !p.data.isSample && p.data.wellType !== "reference",
    }),
    [selection.selected],
  );

  const select = (
    api: GridApi<ResultRow>,
    data: ResultRow,
    ev: MouseEvent | KeyboardEvent | null | undefined,
  ) => {
    // Grid order: pinned references, then the body as sorted and filtered on screen.
    const order = rows.pinned.map((r) => r.wellId);
    api.forEachNodeAfterFilterAndSort((n) => {
      if (n.data) order.push(n.data.wellId);
    });
    onRowClick(
      data.wellId,
      { shift: !!ev?.shiftKey, toggle: !!(ev?.ctrlKey || ev?.metaKey) },
      order,
    );
  };
  const handleRowClicked = (e: RowClickedEvent<ResultRow>) => {
    const ev = e.event as MouseEvent | null | undefined;
    if (!e.data || (ev?.target as HTMLElement | null)?.closest("a, button")) return;
    select(e.api, e.data, ev);
  };
  // The keyboard path: Enter or Space on a focused row selects it as a click would.
  const handleCellKeyDown = (
    e: CellKeyDownEvent<ResultRow> | FullWidthCellKeyDownEvent<ResultRow>,
  ) => {
    const ev = e.event as KeyboardEvent | null | undefined;
    if (!e.data || (ev?.key !== "Enter" && ev?.key !== " ")) return;
    ev?.preventDefault();
    select(e.api, e.data, ev);
  };

  return (
    <TooltipProvider delayDuration={200}>
      <DataGrid<ResultRow>
        rowData={rows.body}
        pinnedTopRowData={rows.pinned}
        columnDefs={columnDefs}
        getRowId={(p) => p.data.wellId}
        rowClass="cursor-pointer"
        rowClassRules={rowClassRules}
        onRowClicked={handleRowClicked}
        onCellKeyDown={handleCellKeyDown}
        suppressCellFocus={false}
        rowHeight={ROW_HEIGHT}
        groupHeaderHeight={GROUP_HEADER_HEIGHT}
        height={gridHeight(rows.pinned.length + rows.body.length, compare)}
        suppressFilters
        searchPlaceholder={SEARCH}
      />
    </TooltipProvider>
  );
}
