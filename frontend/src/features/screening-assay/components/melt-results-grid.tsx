"use client";

import { StructureThumbnail } from "@/shared/components/chemistry/structure-thumbnail";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EntityLink } from "@/shared/components/entity-link";
import { MemberName } from "@/shared/components/entity-name";
import { Badge } from "@/shared/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { formatDateTime } from "@/shared/lib/format-date";
import { cn } from "@/shared/lib/utils";
import type {
  CellKeyDownEvent,
  ColDef,
  ColGroupDef,
  FullWidthCellKeyDownEvent,
  GridApi,
  ICellRendererParams,
  OverlayType,
  RowClassParams,
  RowClickedEvent,
} from "ag-grid-community";
import { Pin, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import type { SelectionState } from "../lib/curve-selection";
import { type ApplicableRule, limitsFor } from "../lib/melt-hits";
import {
  type CellStatus,
  type ResultRow,
  STATUS_ORDER,
  type WindowCell,
  formatDelta,
  formatTm,
  worstStatus,
} from "../lib/melt-results";
import { type MeltingStep, WELL_TYPE_LABELS, type WellType } from "../types";
import { STRUCTURE_THUMBNAIL_SIZE } from "./grid-columns";

type Range = { window: string; low: number; high: number };
type Col = ColDef<ResultRow> | ColGroupDef<ResultRow>;
type Params = ICellRendererParams<ResultRow>;

const ROW_HEIGHT = 36;
/** What a structure adds to its row: the drawing and the gap under it. */
const STRUCTURE_HEIGHT = STRUCTURE_THUMBNAIL_SIZE + 8;
const GROUP_HEADER_HEIGHT = 32;
const DIFFERS_TEXT = "Different number of peaks than the reference";
const LIST = new Intl.ListFormat("en-US", { type: "conjunction" });
// AG Grid's row colours are unlayered CSS, so row-level utilities need `!`.
const SELECTED_ROW = "bg-primary/10! shadow-[inset_3px_0_0_var(--primary)]";
const MUTED_ROW = "text-muted-foreground!";
const NUMERIC = "text-right tabular-nums";
const SEARCH = "Find sample, position or batch";
// Only the identity columns feed the search box; numbers and status do not.
const NOT_SEARCHED = () => "";

/** A value whose peak nobody has reviewed counts as any other and is not
 *  flagged, so "provisional" has no chip: the column speaks of peak problems
 *  and of the reviews that were made. */
const STATUS: Record<
  Exclude<CellStatus, "provisional">,
  { label: string; variant: "secondary" | "warning" | "ghost"; className?: string }
> = {
  reference: { label: "Reference", variant: "secondary" },
  several_steps: { label: "Several peaks", variant: "warning" },
  no_step: { label: "No peak", variant: "warning" },
  no_reference: { label: "No reference", variant: "warning" },
  reviewed: { label: "Reviewed", variant: "ghost", className: "px-0 text-muted-foreground" },
};

const fmtTm = (v: number | null | undefined, limits?: readonly number[]) =>
  v == null ? "" : formatTm(v, limits);
const NO_RULES: readonly ApplicableRule[] = [];
// The line above the grid counts what a filter leaves; AG Grid's own notices
// would be drawn over the pinned reference rows.
const NO_EMPTY_NOTICE: OverlayType[] = ["noRows", "noMatchingRows"];

/** `Peak at 48.1 °C is outside every window. Pick it on the graph to assign it.` */
function outsideText(peaks: readonly number[]): string {
  const at = LIST.format(peaks.map((v) => `${fmtTm(v)} °C`));
  return peaks.length === 1
    ? `Peak at ${at} is outside every window. Pick it on the graph to assign it.`
    : `Peaks at ${at} are outside every window. Pick one on the graph to assign it.`;
}

/** Marks a Tm that a person named by assigning its peak. The tooltip says
 *  who, when and why, and where the peak falls by temperature. */
function AssignedMark({
  step,
  windows,
}: {
  step: MeltingStep | undefined;
  windows: readonly Range[];
}) {
  const inside = step
    ? windows.filter((w) => step.value >= w.low && step.value <= w.high).map((w) => w.window)
    : [];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span role="img" aria-label="Assigned peak" className="inline-flex text-muted-foreground">
          <Pin className="size-3" />
        </span>
      </TooltipTrigger>
      <TooltipContent>
        <p>
          {step?.assigned_by ? (
            <>
              {"Assigned by "}
              <MemberName id={step.assigned_by} />
            </>
          ) : (
            "Assigned"
          )}
          {step?.assigned_at && ` · ${formatDateTime(step.assigned_at)}`}
        </p>
        {step?.assignment_reason && <p>{step.assignment_reason}</p>}
        {step && (
          <p>
            {`By temperature: ${inside.length ? `in ${LIST.format(inside)}` : "outside every window"}`}
          </p>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

/** A hit is blue up (stabilising) or red down; everything else is muted. The
 *  sign says the same without colour. */
function deltaTint(d: number, isHit: boolean): string {
  if (isHit && d > 0) return "font-semibold text-blue-700 dark:text-blue-300";
  if (isHit && d < 0) return "font-semibold text-red-700 dark:text-red-300";
  return "text-muted-foreground";
}

function SampleCell({ row }: { row: ResultRow }) {
  const { registrationNumber, moleculeId, batchSuffix, smiles, label, aliases } = row.identity;
  if (registrationNumber) {
    const id = moleculeId ? (
      <EntityLink
        type="compound"
        id={moleculeId}
        label={registrationNumber}
        className="font-sans"
      />
    ) : (
      <span className="text-sm">{registrationNumber}</span>
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
        {batchSuffix && <span className="text-xs text-muted-foreground">{`·${batchSuffix}`}</span>}
        {aliases.length > 0 && (
          // The first alias gives way to the rest of the cell; "+N" never does.
          <span
            className="flex min-w-0 gap-1 text-xs text-muted-foreground"
            title={aliases.join(", ")}
          >
            <span className="truncate">{aliases[0]}</span>
            {aliases.length > 1 && <span>{`+${aliases.length - 1}`}</span>}
          </span>
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

/** The structure a row draws: its registered compound's, when it has one. */
const structureOf = (row: ResultRow) =>
  row.identity.registrationNumber ? row.identity.smiles : null;

/** The Sample cell while structures are shown: the text on a line as tall as
 *  the row was (36 px less the cell's borders), and the structure under it.
 *  The column is `autoHeight`, so only a row with a structure grows. */
function SampleWithStructure({ row }: { row: ResultRow }) {
  const smiles = structureOf(row);
  return (
    <div>
      <div className="h-[34px] truncate leading-[34px]">
        <SampleCell row={row} />
      </div>
      {smiles && (
        <div className="pb-2">
          <StructureThumbnail smiles={smiles} size={STRUCTURE_THUMBNAIL_SIZE} />
        </div>
      )}
    </div>
  );
}

/** Whether a reference's own peaks in the shown windows were reviewed: all of
 *  those that gave a Tm, and at least one. */
function referenceReviewed(row: ResultRow, windowNames: readonly string[]): boolean {
  const reviews = windowNames.map((n) => row.cells[n]?.review);
  return reviews.includes("reviewed") && !reviews.includes("provisional");
}

function StatusCell({ row, windowNames }: { row: ResultRow; windowNames: readonly string[] }) {
  const status = worstStatus(row, windowNames);
  const differs = windowNames.some((n) => row.cells[n]?.differs);
  const chip = status && status !== "provisional" ? STATUS[status] : null;
  // The same for every window of the signal, so the first shown one speaks.
  const outside =
    status === "no_step"
      ? (windowNames.map((n) => row.cells[n]?.outsidePeaks).find((peaks) => peaks?.length) ?? [])
      : [];
  const badge = chip && (
    <Badge variant={chip.variant} className={chip.className}>
      {status === "reference" && referenceReviewed(row, windowNames)
        ? `${chip.label} · Reviewed`
        : chip.label}
    </Badge>
  );
  return (
    <span className="flex h-full items-center gap-1.5">
      {outside.length > 0 ? (
        <Tooltip>
          <TooltipTrigger asChild>{badge}</TooltipTrigger>
          <TooltipContent>{outsideText(outside)}</TooltipContent>
        </Tooltip>
      ) : (
        badge
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

function windowColumns(
  name: string,
  hits: ReadonlySet<string>,
  grouped: boolean,
  steps: readonly MeltingStep[],
  windows: readonly Range[],
  applicable: readonly ApplicableRule[],
): ColDef<ResultRow>[] {
  const cell = (r: ResultRow | undefined): WindowCell | undefined => r?.cells[name];
  // A value beside a limit of the run's hit rule is shown to two decimals.
  const tmLimits = limitsFor(applicable, name, "tm");
  const deltaLimits = limitsFor(applicable, name, "delta_tm");
  return [
    {
      colId: `${name}:tm`,
      headerName: "Tm (°C)",
      width: 92,
      headerClass: "ag-right-aligned-header",
      cellClass: NUMERIC,
      getQuickFilterText: NOT_SEARCHED,
      valueGetter: (p) => cell(p.data)?.tm ?? null,
      valueFormatter: (p) => fmtTm(p.value, tmLimits),
      // A Tm named by assignment carries a marker; the rest read as plain numbers.
      cellRenderer: (p: Params) => {
        const c = cell(p.data);
        if (c?.namedBy !== "assignment") return fmtTm(c?.tm, tmLimits);
        return (
          <span className="inline-flex items-center gap-1">
            <AssignedMark step={steps.find((s) => s.id === c.stepId)} windows={windows} />
            {fmtTm(c.tm, tmLimits)}
          </span>
        );
      },
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
        p.data?.wellType === "reference"
          ? "—"
          : p.value == null
            ? ""
            : formatDelta(p.value, deltaLimits),
      cellClass: (p) =>
        cn(
          NUMERIC,
          p.data?.isSample &&
            p.value != null &&
            deltaTint(p.value as number, hits.has(p.data.wellId)),
        ),
    },
  ];
}

const statusRank = (s: CellStatus | null) =>
  s === "reference" ? -1 : s === null ? STATUS_ORDER.length : STATUS_ORDER.indexOf(s);

/** Grid height that fits the rows (`structures` of them with a drawing) up to
 *  560 px, then scrolls. */
const gridHeight = (rows: number, structures: number, grouped: boolean) =>
  Math.min(
    560,
    48 + ROW_HEIGHT * rows + STRUCTURE_HEIGHT * structures + (grouped ? GROUP_HEADER_HEIGHT : 0),
  );

/** The results of a run's temperature windows, one row per position: the
 *  references pinned, then samples by largest |ΔTm|, then the rest. Doubles as
 *  the position picker: rows select with click, Shift (range) and Ctrl/Cmd. */
export function MeltResultsGrid({
  rows,
  windowNames,
  steps,
  windows,
  hits,
  applicable = NO_RULES,
  doseUnit,
  showStructures = false,
  selection,
  onRowClick,
}: {
  rows: { pinned: ResultRow[]; body: ResultRow[] };
  windowNames: readonly string[];
  /** The run's peaks: the one that gave an assigned Tm says who assigned it. */
  steps: readonly MeltingStep[];
  /** The temperature windows on the shown signal. */
  windows: readonly Range[];
  /** The positions the run's hit rule calls hits. */
  hits: ReadonlySet<string>;
  /** The run's rules on Tm/ΔTm: a value beside one of their limits is shown to two decimals. */
  applicable?: readonly ApplicableRule[];
  doseUnit: string;
  /** Draw each registered compound's structure in its Sample cell; off, it shows on hover. */
  showStructures?: boolean;
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
            ? [
                p.data.sampleText,
                p.data.identity.label,
                p.data.identity.batchSuffix,
                ...p.data.identity.aliases,
              ]
                .filter(Boolean)
                .join(" ")
            : "",
        autoHeight: showStructures,
        cellRenderer: (p: Params) =>
          !p.data ? null : showStructures ? (
            <SampleWithStructure row={p.data} />
          ) : (
            <SampleCell row={p.data} />
          ),
      },
      {
        colId: "position",
        headerName: "Position",
        width: 110,
        valueGetter: (p) => p.data?.position,
        // As the holder is laid out (Capillary 2 before 11, A2 before A10), not as text.
        comparator: (_a, _b, a, b) => (a.data?.holderRank ?? 0) - (b.data?.holderRank ?? 0),
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
          children: windowColumns(n, hits, true, steps, windows, applicable),
        }))
      : windowColumns(windowNames[0], hits, false, steps, windows, applicable);
    return [
      ...identity,
      ...values,
      {
        colId: "hit",
        headerName: "Hit",
        width: 64,
        getQuickFilterText: NOT_SEARCHED,
        valueGetter: (p) => (p.data && hits.has(p.data.wellId) ? 1 : 0),
        cellRenderer: (p: Params) =>
          p.data && hits.has(p.data.wellId) ? (
            <Badge variant="secondary" className="px-1.5">
              Hit
            </Badge>
          ) : null,
      },
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
  }, [windowNames, compare, hits, doseUnit, steps, windows, applicable, showStructures]);

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

  const shown = [...rows.pinned, ...rows.body];
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
        height={gridHeight(
          shown.length,
          showStructures ? shown.filter(structureOf).length : 0,
          compare,
        )}
        suppressFilters
        suppressOverlays={NO_EMPTY_NOTICE}
        searchPlaceholder={SEARCH}
      />
    </TooltipProvider>
  );
}
