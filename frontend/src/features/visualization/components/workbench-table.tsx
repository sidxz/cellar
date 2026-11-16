"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { cellarTheme } from "@/shared/components/data-grid/ag-grid-theme";
import { EntityLink } from "@/shared/components/entity-link";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/components/ui/tooltip";
import { saveText } from "@/shared/lib/api/download";
import {
  AllCommunityModule,
  type ColDef,
  type ColGroupDef,
  type GridApi,
  type ICellRendererParams,
  ModuleRegistry,
  type PaginationChangedEvent,
  type RowClassParams,
  type RowHeightParams,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { ChevronDown, ChevronRight, Columns3 } from "lucide-react";
import {
  type KeyboardEvent,
  type ReactNode,
  type Ref,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import { isComparedValue } from "../lib/cross-protocol";
import { categoryLabel, column, numberAt } from "../lib/dataset";
import { nullsLast, orderTableRows, pinnedBlock } from "../lib/table-rows";
import { cellText, qualifierText } from "../lib/value-description";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset, DatasetColumn } from "../types";
import { CurveSparklineCell, CurvesCountCell } from "./table/curve-cells";
import { ValueCell } from "./table/value-cell";

ModuleRegistry.registerModules([AllCommunityModule]);

type Density = "compact" | "chemistry";
/** A grid row points at dataset row ``i``; ``i = -1`` is the "Selected (n)" label row and
 * ``i = -2`` the "and n more selected" row under the pinned ones. */
interface Row {
  i: number;
  label?: string;
  collapsed?: boolean;
}
type Col = ColDef<Row> | ColGroupDef<Row>;

const ROW_HEIGHT: Record<Density, number> = { compact: 28, chemistry: 108 };
const NUMERIC = "text-right tabular-nums";
const OWN_COLUMNS = new Set(["compound", "structure"]);
const LEADING = new Set(["well", "well_type"]);
/** Shown only on request: Run date repeats Run; the rest matter for plate QC. */
const HIDDEN_BY_DEFAULT = new Set([
  "run_date",
  "run_status",
  "well_row",
  "well_column",
  "well_order",
]);
/** Readout values (p-values included); their siblings (qualifier, n, SD …) carry a stat. */
const isValue = (c: DatasetColumn) => !!c.provenance.readout_definition_id;
/** Table-only columns (checkbox, curves): never exported. */
const OWN_PREFIX = "__";
type OpenCurves = (valueKey: string, i: number) => void;
const isData = (row: Row | undefined): row is Row => !!row && row.i >= 0;
const fmt = (n: number) => n.toLocaleString();
const NO_ROWS = { noRowsToShow: "No rows match the filters" };
const MORE = -2;
/** Cells take no focus (``suppressCellFocus``); their buttons and links do. The grid's own
 * keys (cell-to-cell arrows) would hold focus on a button that cannot move, so every key from
 * a cell goes to the browser; Tab is the table's own (see ``tabThroughRows``). */
const DEFAULT_COL: ColDef<Row> = {
  sortable: true,
  resizable: true,
  suppressMovable: true,
  suppressKeyboardEvent: () => true,
};
const TABBABLE = [
  "a[href]",
  "button:not(:disabled)",
  "input:not(:disabled)",
  "select:not(:disabled)",
  '[tabindex]:not([tabindex="-1"])',
];
/** Controls inside rows (a row's own tab stop not included). */
const ROW_CONTROLS = TABBABLE.map((s) => `.ag-row ${s}`).join(",");

/** The rows' controls in reading order: row by row, the pinned rows first, and within a row
 * its left-pinned, centre and right cells. AG Grid renders each of those in a container of its
 * own, so the DOM (the browser's Tab order) walks one container's rows before the next's. */
function rowControls(root: HTMLElement): HTMLElement[] {
  const byRow = new Map<string, HTMLElement[]>();
  for (const el of root.querySelectorAll<HTMLElement>(ROW_CONTROLS)) {
    const row = el.closest(".ag-row") as HTMLElement;
    const key = `${row.closest(".ag-floating-top") ? 0 : 1}:${row.getAttribute("row-index")}`;
    byRow.set(key, [...(byRow.get(key) ?? []), el]);
  }
  const rank = (key: string) => {
    const [section, index] = key.split(":");
    return Number(section) * 1e9 + Number(index.replace(/^t-/, ""));
  };
  return [...byRow.entries()].sort(([a], [b]) => rank(a) - rank(b)).flatMap(([, els]) => els);
}

/** The first control after the rows (the pager's), where Tab from the last row goes. */
function afterRows(root: HTMLElement): HTMLElement | undefined {
  const body = root.querySelector(".ag-body");
  if (!body) return undefined;
  return [...root.querySelectorAll<HTMLElement>(TABBABLE.join(","))].find(
    (el) =>
      !body.contains(el) &&
      !!(body.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      !el.classList.contains("ag-tab-guard") &&
      el.getAttribute("aria-disabled") !== "true",
  );
}

/** Tab and Shift+Tab through the table: from the last column's header into the first row,
 * row by row through each row's controls ("Selected (n)" and its rows included), past the last
 * row on to the pager, and back the same way. Anything else is left to the grid and the
 * browser. */
function tabThroughRows(e: KeyboardEvent<HTMLDivElement>, api: GridApi<Row> | undefined) {
  if (e.key !== "Tab" || e.altKey || e.ctrlKey || e.metaKey || !api) return;
  const root = e.currentTarget;
  const target = e.target as HTMLElement;
  const back = e.shiftKey;
  const controls = rowControls(root);
  const lastColumn = api.getAllDisplayedColumns().at(-1);
  const after = afterRows(root);
  let next: HTMLElement | "header" | undefined;
  if (target.closest(".ag-header-cell")) {
    const last =
      target.closest(".ag-header-cell")?.getAttribute("col-id") === lastColumn?.getColId();
    if (!back && last) next = controls[0];
  } else if (target === after) {
    if (back) next = controls.at(-1);
  } else {
    const k = controls.indexOf(target);
    if (k < 0) return;
    next = controls[k + (back ? -1 : 1)] ?? (back ? "header" : after);
  }
  if (!next) return;
  e.preventDefault();
  e.stopPropagation(); // the grid's own Tab handling never runs
  if (next !== "header") next.focus();
  else if (lastColumn) api.setFocusedHeader(lastColumn);
}
const PAGE_SIZE = 100;
const PAGE_SIZES = [50, 100, 250, 500];
/** The grid is as tall as its page and the viewport scrolls it (see WorkbenchBody), so the
 * grid's own clipping goes: the header sticks to the viewport's top and the sideways
 * scrollbar to its bottom while the table is in view. */
const STICKY = [
  ".viz-table .ag-root-wrapper,.viz-table .ag-root.ag-layout-auto-height{overflow:visible}",
  ".viz-table .ag-header{position:sticky;top:0;z-index:3}",
  ".viz-table .ag-body-horizontal-scroll{position:sticky;bottom:0;z-index:3;background:var(--background)}",
].join("");

function SelectCell({ data, rowIds }: ICellRendererParams<Row> & { rowIds: string[] }) {
  const selection = useWorkbench((s) => s.selection);
  const setSelection = useWorkbench((s) => s.setSelection);
  if (!isData(data)) return null;
  const id = rowIds[data.i];
  return (
    <div className="flex h-full items-center">
      <Checkbox
        aria-label="Select row"
        checked={selection.has(id)}
        onCheckedChange={(on) => {
          const next = new Set(selection);
          if (on === true) next.add(id);
          else next.delete(id);
          setSelection(next);
        }}
      />
    </div>
  );
}

const NoCompound = ({ text = "no compound" }: { text?: string }) => (
  <span className="truncate text-sm text-muted-foreground">{text}</span>
);

/** A row's compound, linked; a well without one by its label, else its role in words. */
function CompoundCell({ data, value, ds }: ICellRendererParams<Row> & { ds: Dataset }) {
  if (!isData(data)) return null;
  if (value == null) {
    const label = ds.values.label?.[data.i];
    const role = ds.values.well_type?.[data.i];
    if (typeof label === "string" && label) return <NoCompound text={label} />;
    if (role && role !== "sample") return <NoCompound text={categoryLabel("well_type", role)} />;
    return <NoCompound />;
  }
  const id = ds.values.molecule_id?.[data.i];
  return typeof id === "string" ? (
    <EntityLink type="compound" id={id} label={String(value)} />
  ) : (
    <span className="font-mono text-sm">{String(value)}</span>
  );
}

function StructureCell({ data, value, ds }: ICellRendererParams<Row> & { ds: Dataset }) {
  if (!isData(data)) return null;
  if (ds.values.compound?.[data.i] == null) {
    return (
      <div className="flex h-full items-center justify-center">
        <NoCompound />
      </div>
    );
  }
  if (typeof value !== "string" || !value) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex h-full items-center justify-center py-1">
          <StructureThumbnail smiles={value} size={100} />
        </div>
      </TooltipTrigger>
      <TooltipContent
        side="right"
        sideOffset={6}
        collisionPadding={12}
        className="border bg-popover p-1.5 text-popover-foreground shadow-lg"
      >
        <div className="rounded-sm bg-white p-1">
          <StructureThumbnail smiles={value} size={240} />
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

function SelectedGroupRow({
  data,
  onToggle,
  onFilter,
}: ICellRendererParams<Row> & { onToggle: () => void; onFilter: () => void }) {
  if (data?.i === MORE) {
    return (
      <div className="flex h-full items-center gap-2 bg-primary/5 px-2 text-xs text-muted-foreground">
        {data.label}
        <Button size="sm" variant="link" className="h-6 px-0 text-xs" onClick={onFilter}>
          Filter to selection
        </Button>
      </div>
    );
  }
  const Icon = data?.collapsed ? ChevronRight : ChevronDown;
  return (
    <button
      type="button"
      aria-expanded={!data?.collapsed}
      className="flex h-full w-full items-center gap-1 bg-primary/5 px-2 text-left text-xs font-medium"
      onClick={onToggle}
    >
      <Icon className="h-3.5 w-3.5" />
      {data?.label}
    </button>
  );
}

/** A column's header under its group: the group says what the "{group} · " prefix would. */
const shortLabel = (c: DatasetColumn) =>
  c.group && c.label.startsWith(`${c.group} · `) ? c.label.slice(c.group.length + 3) : c.label;

function leafColumn(ds: Dataset, c: DatasetColumn): ColDef<Row> {
  const base = {
    colId: c.key,
    headerName: shortLabel(c),
    headerTooltip: c.label,
    width: 120,
    // Compared values rank measured compounds only: untested ones stay last both ways.
    ...(isComparedValue(ds, c.key) && { comparator: nullsLast }),
  };
  if (c.kind !== "number") {
    return {
      ...base,
      valueGetter: (p) => (isData(p.data) ? (ds.values[c.key]?.[p.data.i] ?? null) : null),
      valueFormatter: (p) => (p.value == null ? "" : categoryLabel(c.key, p.value)),
    };
  }
  if (c.provenance.aggregation) {
    // Aggregated levels: qualifier, inactive badge and a popover saying how it was computed.
    return {
      ...base,
      width: ds.values[`${c.key}:n_inactive`] ? 190 : 130,
      headerClass: "ag-right-aligned-header",
      valueGetter: (p) => (isData(p.data) ? numberAt(ds, c.key, p.data.i) : null),
      cellRenderer: (p: ICellRendererParams<Row>) =>
        isData(p.data) ? <ValueCell ds={ds} valueKey={c.key} i={p.data.i} /> : null,
    };
  }
  const qualifier = ds.values[`${c.key}:q`];
  const outlier = ds.values[`${c.key}:outlier`];
  return {
    ...base,
    headerClass: "ag-right-aligned-header",
    cellClass: NUMERIC,
    valueGetter: (p) => (isData(p.data) ? numberAt(ds, c.key, p.data.i) : null),
    valueFormatter: (p) => {
      if (typeof p.value !== "number" || !isData(p.data)) return "";
      const text = cellText(p.value);
      const q = qualifierText(qualifier?.[p.data.i]);
      return q ? `${q} ${text}` : text;
    },
    cellClassRules: outlier
      ? {
          "line-through text-muted-foreground": (p) => isData(p.data) && outlier[p.data.i] != null,
        }
      : undefined,
  };
}

/** A value's qualifier for the CSV export only (hidden on screen, where the bound stands in
 * front of its number): ``<``, ``>``, ``≤``, ``≥``; blank for ``=`` and none. Null when the
 * value has no qualifier sibling. */
function qualifierColumn(ds: Dataset, c: DatasetColumn): ColDef<Row> | null {
  const q = ds.values[`${c.key}:q`];
  if (c.kind !== "number" || !q) return null;
  return {
    colId: `${c.key}:q`,
    headerName: "qualifier",
    headerTooltip: `${c.label} qualifier`,
    hide: true,
    valueGetter: (p) =>
      isData(p.data) && q[p.data.i] !== "=" ? qualifierText(q[p.data.i]) || null : null,
  };
}

/** Columns the chooser offers, in table order: well and well type, the readout values,
 * then the rest (run, plate, conditions …) in dataset order. Compound and structure have
 * their own columns; siblings (qualifier, outlier, n, SD, fit parameters …) render inside
 * their values, their popover or their curve. */
function tableFields(ds: Dataset): DatasetColumn[] {
  const rank = (c: DatasetColumn) => (LEADING.has(c.key) ? 0 : isValue(c) ? 1 : 2);
  return ds.columns
    .filter((c) => !c.hidden && !c.provenance.stat && !OWN_COLUMNS.has(c.key))
    .sort((a, b) => rank(a) - rank(b));
}

/** Hidden until chosen: the redundant identity columns and any that hold no value. */
function defaultHidden(ds: Dataset): Set<string> {
  const empty = (key: string) => (ds.values[key] ?? []).every((v) => v == null || v === "");
  return new Set(
    tableFields(ds)
      .filter((c) => HIDDEN_BY_DEFAULT.has(c.key) || (!isValue(c) && empty(c.key)))
      .map((c) => c.key),
  );
}

function ColumnChooser({
  fields,
  hidden,
  onToggle,
}: {
  fields: DatasetColumn[];
  hidden: Set<string>;
  onToggle: (key: string) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline" className="h-7">
          <Columns3 className="h-3.5 w-3.5" />
          Columns
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-80 w-60 overflow-y-auto">
        {fields.map((c) => (
          <DropdownMenuCheckboxItem
            key={c.key}
            checked={!hidden.has(c.key)}
            onCheckedChange={() => onToggle(c.key)}
            // Stay open so several columns can be toggled in a row.
            onSelect={(e) => e.preventDefault()}
          >
            <span className="truncate">{c.label}</span>
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The curve column after a dose-response value: at Runs this run's curve, above it a
 * "Curves (n)" button; both open the curves dialog. Null for any other column. */
function curveColumn(
  ds: Dataset,
  c: DatasetColumn,
  chemistry: boolean,
  onOpen: OpenCurves,
): ColDef<Row> | null {
  const { aggregation, layer } = c.provenance;
  const fit = aggregation === "fit";
  if (!fit && !(aggregation === "geomean" && !layer)) return null;
  return {
    colId: `${OWN_PREFIX}curve:${c.key}`,
    headerName: `${fit ? "Curve" : "Curves"} · ${shortLabel(c)}`,
    headerTooltip: `${fit ? "Curve" : "Curves"} · ${c.label}`,
    width: fit && chemistry ? 160 : 120,
    sortable: false,
    cellRenderer: (p: ICellRendererParams<Row>) => {
      if (!isData(p.data)) return null;
      const props = { ds, valueKey: c.key, i: p.data.i, onOpen };
      return fit ? (
        <CurveSparklineCell {...props} compact={!chemistry} />
      ) : (
        <CurvesCountCell {...props} />
      );
    },
  };
}

/** Select + compound pinned left, structure in chemistry density, then the shown fields
 * grouped by their dataset group (a dose-response value followed by its curve column). */
function tableColumns(
  ds: Dataset,
  chemistry: boolean,
  hidden: Set<string>,
  onOpenCurves: OpenCurves,
): Col[] {
  const cols: Col[] = [
    {
      colId: "__select__",
      headerName: "",
      pinned: "left",
      lockPinned: true,
      width: 44,
      resizable: false,
      sortable: false,
      cellRenderer: SelectCell,
      cellRendererParams: { rowIds: ds.row_ids },
    },
    {
      colId: "compound",
      headerName: "Compound",
      pinned: "left",
      lockPinned: true,
      width: 150,
      valueGetter: (p) => (isData(p.data) ? (ds.values.compound?.[p.data.i] ?? null) : null),
      cellRenderer: CompoundCell,
      cellRendererParams: { ds },
    },
  ];
  if (chemistry && column(ds, "structure")) {
    cols.push({
      colId: "structure",
      headerName: "Structure",
      width: 116,
      sortable: false,
      valueGetter: (p) => (isData(p.data) ? (ds.values.structure?.[p.data.i] ?? null) : null),
      cellRenderer: StructureCell,
      cellRendererParams: { ds },
    });
  }
  for (const c of tableFields(ds)) {
    if (hidden.has(c.key)) continue;
    for (const leaf of [
      leafColumn(ds, c),
      qualifierColumn(ds, c),
      curveColumn(ds, c, chemistry, onOpenCurves),
    ]) {
      if (!leaf) continue;
      const last = cols.at(-1);
      if (c.group && last && "children" in last && last.headerName === c.group) {
        last.children.push(leaf);
      } else {
        cols.push(c.group ? { headerName: c.group, children: [leaf] } : leaf);
      }
    }
  }
  return cols;
}

export interface WorkbenchTableHandle {
  /** Download the rows Save acts on — the selected passing rows, else every passing row —
   * over the visible columns; numbers unrounded and bare, a value's qualifier in a
   * "{label} qualifier" column beside it. */
  exportCsv: (fileName: string) => void;
}

/** The linked table: passing rows (all rows on request) in pages of 100 that flow with the
 * page, selected rows pinned on top under a collapsible "Selected (n)" row, compact or
 * chemistry density, a Columns chooser.
 * `actions` (Save…) sit at the right end of the toolbar; `ref` exposes the CSV export;
 * `onOpenCurves` opens the curves behind a dose-response value. */
export function WorkbenchTable({
  ds,
  actions,
  ref,
  onOpenCurves,
}: {
  ds: Dataset;
  actions?: ReactNode;
  ref?: Ref<WorkbenchTableHandle>;
  onOpenCurves: OpenCurves;
}) {
  const grid = useRef<AgGridReact<Row>>(null);
  const root = useRef<HTMLDivElement>(null);
  const mask = usePassMask(ds);
  const selection = useWorkbench((s) => s.selection);
  const filterToSelection = useWorkbench((s) => s.filterToSelection);
  const [density, setDensity] = useState<Density>("chemistry");
  const [showAll, setShowAll] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [hidden, setHidden] = useState(() => defaultHidden(ds));
  const fields = useMemo(() => tableFields(ds), [ds]);
  const toggleColumn = useCallback(
    (key: string) =>
      setHidden((h) => {
        const next = new Set(h);
        if (!next.delete(key)) next.add(key);
        return next;
      }),
    [],
  );

  // One stable object per dataset row, so the grid diffs re-orderings by id.
  const rows = useMemo<Row[]>(() => ds.row_ids.map((_, i) => ({ i })), [ds]);
  const { pinned, rest } = useMemo(
    () => orderTableRows(ds, mask, selection, showAll),
    [ds, mask, selection, showAll],
  );
  const rowData = useMemo(() => rest.map((i) => rows[i]), [rest, rows]);
  const pinnedRows = useMemo<Row[]>(() => {
    if (pinned.length === 0) return [];
    const { shown, more } = pinnedBlock(pinned, collapsed);
    return [
      { i: -1, label: `Selected (${fmt(pinned.length)})`, collapsed },
      ...shown.map((i) => rows[i]),
      ...(more ? [{ i: MORE, label: `and ${fmt(more)} more selected` }] : []),
    ];
  }, [pinned, rows, collapsed]);
  const columnDefs = useMemo(
    () => tableColumns(ds, density === "chemistry", hidden, onOpenCurves),
    [ds, density, hidden, onOpenCurves],
  );
  const toggleGroup = useCallback(() => setCollapsed((c) => !c), []);
  const groupParams = useMemo(
    () => ({ onToggle: toggleGroup, onFilter: filterToSelection }),
    [toggleGroup, filterToSelection],
  );
  // The label rows stay compact whatever the density.
  const getRowHeight = useCallback(
    (p: RowHeightParams<Row>) => (isData(p.data) ? ROW_HEIGHT[density] : ROW_HEIGHT.compact),
    [density],
  );
  useImperativeHandle(
    ref,
    () => ({
      exportCsv: (fileName) => {
        const api = grid.current?.api;
        if (!api) return;
        // The Selected group shows only some of its rows (or none, collapsed); lend the grid
        // all of them for the (synchronous) read.
        const lend = pinnedRows.filter(isData).length < pinned.length;
        if (lend)
          api.setGridOption(
            "pinnedTopRowData",
            pinned.map((i) => rows[i]),
          );
        const csv = api.getDataAsCsv({
          skipColumnGroupHeaders: true,
          // Without the group row, each column keeps its full label ("Counter · pIC50").
          processHeaderCallback: (p) =>
            p.column.getColDef().headerTooltip ??
            p.api.getDisplayNameForColumn(p.column, "csv") ??
            "",
          columnKeys: api
            .getAllDisplayedColumns()
            .filter((c) => !c.getColId().startsWith(OWN_PREFIX))
            .flatMap((c) => {
              const q = api.getColumn(`${c.getColId()}:q`);
              return q ? [c, q] : [c];
            }),
          shouldRowBeSkipped: (p) =>
            !isData(p.node.data) ||
            !mask[p.node.data.i] ||
            (selection.size > 0 && !selection.has(ds.row_ids[p.node.data.i])),
          // Numbers as they are: the cells' formatter rounds them and puts the bound in front.
          processCellCallback: (p) =>
            typeof p.value === "number" ? String(p.value) : p.formatValue(p.value),
        });
        if (lend) api.setGridOption("pinnedTopRowData", pinnedRows);
        // The byte-order mark makes Excel read the file as UTF-8 (≥, µ).
        if (csv !== undefined) saveText(`\uFEFF${csv}`, fileName);
      },
    }),
    [ds, mask, selection, pinned, pinnedRows, rows],
  );
  const getRowClass = useCallback(
    (p: RowClassParams<Row>) =>
      isData(p.data) && !mask[p.data.i] ? "text-muted-foreground opacity-60" : undefined,
    [mask],
  );
  // New rows that no longer reach the current page: the grid would fall back to the last page;
  // start over instead. A layout effect, so it runs before the grid takes the rows (an effect).
  useLayoutEffect(() => {
    const api = grid.current?.api;
    if (api && api.paginationGetCurrentPage() * api.paginationGetPageSize() >= rowData.length) {
      api.paginationGoToFirstPage();
    }
  }, [rowData]);
  // Paged at the foot of a long page: show the new page from its top.
  const onPaginationChanged = useCallback((e: PaginationChangedEvent<Row>) => {
    const el = root.current;
    if (e.newPage && el && el.getBoundingClientRect().top < 0)
      el.scrollIntoView({ block: "start" });
  }, []);

  return (
    <div
      ref={root}
      className="viz-table flex flex-col"
      onKeyDownCapture={(e) => tabThroughRows(e, grid.current?.api)}
    >
      <style>{STICKY}</style>
      <div className="flex shrink-0 items-center gap-2 px-2 py-1 text-xs">
        <span className="text-muted-foreground">{fmt(pinned.length + rest.length)} rows</span>
        <fieldset aria-label="Row density" className="ml-auto flex items-center gap-0.5">
          {(["compact", "chemistry"] as const).map((d) => (
            <Button
              key={d}
              size="sm"
              variant={density === d ? "secondary" : "ghost"}
              aria-pressed={density === d}
              className="h-7"
              onClick={() => setDensity(d)}
            >
              {d === "compact" ? "Compact" : "Chemistry"}
            </Button>
          ))}
        </fieldset>
        <ColumnChooser fields={fields} hidden={hidden} onToggle={toggleColumn} />
        <Button
          size="sm"
          variant={showAll ? "secondary" : "outline"}
          aria-pressed={showAll}
          className="h-7"
          onClick={() => setShowAll((v) => !v)}
        >
          Show filtered rows
        </Button>
        {actions}
      </div>
      <AgGridReact<Row>
        ref={grid}
        theme={cellarTheme}
        domLayout="autoHeight"
        pagination
        paginationPageSize={PAGE_SIZE}
        paginationPageSizeSelector={PAGE_SIZES}
        onPaginationChanged={onPaginationChanged}
        rowData={rowData}
        pinnedTopRowData={pinnedRows}
        columnDefs={columnDefs}
        defaultColDef={DEFAULT_COL}
        getRowId={(p) => (p.data.i < 0 ? `selected-${p.data.i}` : ds.row_ids[p.data.i])}
        isFullWidthRow={(p) => (p.rowNode.data?.i ?? 0) < 0}
        fullWidthCellRenderer={SelectedGroupRow}
        fullWidthCellRendererParams={groupParams}
        getRowClass={getRowClass}
        rowHeight={ROW_HEIGHT[density]}
        getRowHeight={getRowHeight}
        suppressCellFocus
        // Rows stay in the DOM in their shown order, so Tab through the cell buttons follows
        // a sort or a re-pin.
        ensureDomOrder
        animateRows={false}
        localeText={NO_ROWS}
      />
    </div>
  );
}
