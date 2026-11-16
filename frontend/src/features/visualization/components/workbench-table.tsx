"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { cellarTheme } from "@/shared/components/data-grid/ag-grid-theme";
import { EntityLink } from "@/shared/components/entity-link";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/components/ui/tooltip";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import {
  AllCommunityModule,
  type ColDef,
  type ColGroupDef,
  type ICellRendererParams,
  ModuleRegistry,
  type RowClassParams,
  type RowHeightParams,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { type ReactNode, useCallback, useMemo, useState } from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import { categoryLabel, column, numberAt } from "../lib/dataset";
import { orderTableRows } from "../lib/table-rows";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset, DatasetColumn } from "../types";

ModuleRegistry.registerModules([AllCommunityModule]);

type Density = "compact" | "chemistry";
/** A grid row points at dataset row ``i``; ``i = -1`` is the "Selected (n)" label row. */
interface Row {
  i: number;
  label?: string;
  collapsed?: boolean;
}
type Col = ColDef<Row> | ColGroupDef<Row>;

const ROW_HEIGHT: Record<Density, number> = { compact: 28, chemistry: 108 };
const NUMERIC = "text-right tabular-nums";
const SIBLING = /:(q|outlier)$/;
const OWN_COLUMNS = new Set(["compound", "structure"]);
const isData = (row: Row | undefined): row is Row => !!row && row.i >= 0;
const fmt = (n: number) => n.toLocaleString();

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

function CompoundCell({ data, value, ds }: ICellRendererParams<Row> & { ds: Dataset }) {
  if (!isData(data) || value == null) return null;
  const id = ds.values.molecule_id?.[data.i];
  return typeof id === "string" ? (
    <EntityLink type="compound" id={id} label={String(value)} />
  ) : (
    <span className="font-mono text-sm">{String(value)}</span>
  );
}

function StructureCell({ value }: ICellRendererParams<Row>) {
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

function SelectedGroupRow({ data, onToggle }: ICellRendererParams<Row> & { onToggle: () => void }) {
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

function leafColumn(ds: Dataset, c: DatasetColumn): ColDef<Row> {
  const base = { colId: c.key, headerName: c.label, headerTooltip: c.label, width: 120 };
  if (c.kind !== "number") {
    return {
      ...base,
      valueGetter: (p) => (isData(p.data) ? (ds.values[c.key]?.[p.data.i] ?? null) : null),
      valueFormatter: (p) => (p.value == null ? "" : categoryLabel(c.key, p.value)),
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
      const text = Number.isInteger(p.value) ? String(p.value) : formatMeasurementValue(p.value);
      const q = qualifier?.[p.data.i];
      return q ? `${q} ${text}` : text;
    },
    cellClassRules: outlier
      ? {
          "line-through text-muted-foreground": (p) => isData(p.data) && outlier[p.data.i] != null,
        }
      : undefined,
  };
}

/** Select + compound pinned left, structure in chemistry density, then every visible
 * column grouped by its dataset group (qualifier/outlier siblings render inside values). */
function tableColumns(ds: Dataset, chemistry: boolean): Col[] {
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
    });
  }
  for (const c of ds.columns) {
    if (c.hidden || SIBLING.test(c.key) || OWN_COLUMNS.has(c.key)) continue;
    const leaf = leafColumn(ds, c);
    const last = cols.at(-1);
    if (c.group && last && "children" in last && last.headerName === c.group) {
      last.children.push(leaf);
    } else {
      cols.push(c.group ? { headerName: c.group, children: [leaf] } : leaf);
    }
  }
  return cols;
}

/** The linked table: passing rows (all rows on request), selected rows pinned on top
 * under a collapsible "Selected (n)" row, compact or chemistry density. */
/** `actions` (Save, Export…) sit at the right end of the table toolbar. */
export function WorkbenchTable({ ds, actions }: { ds: Dataset; actions?: ReactNode }) {
  const mask = usePassMask(ds);
  const selection = useWorkbench((s) => s.selection);
  const [density, setDensity] = useState<Density>("chemistry");
  const [showAll, setShowAll] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  // One stable object per dataset row, so the grid diffs re-orderings by id.
  const rows = useMemo<Row[]>(() => ds.row_ids.map((_, i) => ({ i })), [ds]);
  const { pinned, rest } = useMemo(
    () => orderTableRows(ds, mask, selection, showAll),
    [ds, mask, selection, showAll],
  );
  const rowData = useMemo(() => rest.map((i) => rows[i]), [rest, rows]);
  const pinnedRows = useMemo<Row[]>(
    () =>
      pinned.length === 0
        ? []
        : [
            { i: -1, label: `Selected (${fmt(pinned.length)})`, collapsed },
            ...(collapsed ? [] : pinned.map((i) => rows[i])),
          ],
    [pinned, rows, collapsed],
  );
  const columnDefs = useMemo(() => tableColumns(ds, density === "chemistry"), [ds, density]);
  const toggleGroup = useCallback(() => setCollapsed((c) => !c), []);
  const groupParams = useMemo(() => ({ onToggle: toggleGroup }), [toggleGroup]);
  // The label row stays compact whatever the density.
  const getRowHeight = useCallback(
    (p: RowHeightParams<Row>) => (p.data?.i === -1 ? ROW_HEIGHT.compact : ROW_HEIGHT[density]),
    [density],
  );
  const getRowClass = useCallback(
    (p: RowClassParams<Row>) =>
      isData(p.data) && !mask[p.data.i] ? "text-muted-foreground opacity-60" : undefined,
    [mask],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
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
      <div className="min-h-0 flex-1">
        <AgGridReact<Row>
          theme={cellarTheme}
          rowData={rowData}
          pinnedTopRowData={pinnedRows}
          columnDefs={columnDefs}
          defaultColDef={{ sortable: true, resizable: true, suppressMovable: true }}
          getRowId={(p) => (p.data.i < 0 ? "selected-group" : ds.row_ids[p.data.i])}
          isFullWidthRow={(p) => p.rowNode.data?.i === -1}
          fullWidthCellRenderer={SelectedGroupRow}
          fullWidthCellRendererParams={groupParams}
          getRowClass={getRowClass}
          rowHeight={ROW_HEIGHT[density]}
          getRowHeight={getRowHeight}
          suppressCellFocus
          animateRows={false}
        />
      </div>
    </div>
  );
}
