"use client";

import { DoseResponseCell } from "@/features/research-organization/components/search/dose-response-cell";
import { activityValueToCurveSnapshot } from "@/features/research-organization/lib/activity-curve-snapshot";
import {
  CurveExpandDialog,
  type ExpandedCurve,
} from "@/features/screen-campaign/components/grid/curve-expand-dialog";
import { structureColumn } from "@/features/screening-assay/components/grid-columns";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Button } from "@/shared/components/ui/button";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { useMemo, useState } from "react";
import { type RGroupRow, useDecompositionRows } from "../hooks/use-decomposition-rows";
import { potencyShade } from "../lib/sar-activity-display";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { fragmentDisplay } from "../lib/sar-fragment-label";

export interface RGroupTableProps {
  runId: string;
  projectionId?: string | null;
  labels: string[];
  colorSpec?: SarColorSpec | null;
  /** Receives the selected (loaded) rows so the save dialog can preview them
   *  without `props.molecules`. */
  onSaveSelection: (rows: { id: string; label: string }[]) => void;
  /** Total matched (pre-filter) baseline for the toolbar count before the first
   *  page returns; the live filtered `total` from the rows hook supersedes it. */
  matchedCount?: number;
  /** Save every matched compound under the current filter (server-resolved). */
  onSaveAll?: (args: {
    count: number;
    filter?: Record<string, unknown>;
    projectionId?: string | null;
  }) => void;
}

/** Structure + Compound + one column per R-group + (optional) activity + physchem. */
export function buildRGroupColumns(
  labels: string[],
  activityColumns: ColDef<RGroupRow>[] = [],
): ColDef<RGroupRow>[] {
  const cols: ColDef<RGroupRow>[] = [structureColumn<RGroupRow>((r) => r.smiles)];
  cols.push({
    headerName: "Compound",
    colId: "registration_number",
    width: 130,
    valueGetter: (p) => p.data?.registration_number ?? "",
  });
  for (const label of labels) {
    cols.push({
      headerName: label,
      colId: `rg:${label}`,
      width: 160,
      // R-group sort + text filter are server-applied (mapped via colIdToBackendKey).
      sortable: true,
      valueGetter: (p) => p.data?.rgroups[label] ?? "",
      cellRenderer: (p: ICellRendererParams<RGroupRow>) => {
        const smi = p.data?.rgroups[label];
        if (!smi) return <span className="text-muted-foreground">—</span>;
        const frag = fragmentDisplay(smi);
        if (frag.isHydrogen) {
          return (
            <div className="flex h-full items-center" title={frag.title}>
              <span className="text-muted-foreground">{frag.label}</span>
            </div>
          );
        }
        return (
          <div className="flex h-full items-center gap-1.5" title={frag.title}>
            {frag.thumbnailSmiles && (
              <StructureThumbnail smiles={frag.thumbnailSmiles} size={64} className="shrink-0" />
            )}
            <span className="break-all text-[11px] font-medium">{frag.label}</span>
          </div>
        );
      },
    });
  }
  cols.push(...activityColumns);
  cols.push(
    {
      headerName: "MW",
      colId: "mw",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.mw ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : "—"),
    },
    {
      headerName: "cLogP",
      colId: "clogp",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.clogp ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(2) : "—"),
    },
    {
      headerName: "TPSA",
      colId: "tpsa",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.tpsa ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : "—"),
    },
  );
  return cols;
}

/** Toolbar label for the save-all action: matched (no filter) vs filtered. */
export function saveAllLabel(count: number | null, filterActive: boolean): string {
  const n = count ?? 0;
  return filterActive ? `Save ${n} filtered` : `Save all ${n} matched`;
}

/** Save-all is actionable only with a known, positive count. */
export function canSaveAll(count: number | null): boolean {
  return count != null && count > 0;
}

/**
 * Activity value + plot columns, fed from the server per-row `activity` /
 * `activitySnapshot` and the server `reference` (min scalar across the filtered
 * set). Shading is gated to `dr_curve` (lower-is-better); `readout_data` renders
 * the value uncolored.
 */
export function buildActivityColumns(
  colorSpec: SarColorSpec,
  reference: number | null,
): ColDef<RGroupRow>[] {
  const shadeByPotency = colorSpec.source === "dr_curve";
  return [
    {
      headerName: colorSpec.label,
      colId: "activity:value",
      width: 150,
      type: "numericColumn",
      valueGetter: (p) => p.data?.activity ?? null,
      valueFormatter: (p) => {
        if (p.value == null) return "—";
        const unit = p.data?.activitySnapshot?.unit ? ` ${p.data.activitySnapshot.unit}` : "";
        return `${formatMeasurementValue(p.value as number)}${unit}`;
      },
      cellClass: shadeByPotency
        ? (p) => potencyShade(p.data?.activity ?? null, reference)
        : undefined,
    },
    {
      headerName: "Plot",
      colId: "activity:plot",
      width: 240,
      sortable: false,
      filter: false,
      cellRenderer: (p: ICellRendererParams<RGroupRow>) => (
        <DoseResponseCell value={p.data?.activitySnapshot ?? undefined} />
      ),
    },
  ];
}

export function RGroupTable({
  runId,
  projectionId,
  labels,
  colorSpec,
  onSaveSelection,
  matchedCount,
  onSaveAll,
}: RGroupTableProps) {
  const [openCurve, setOpenCurve] = useState<ExpandedCurve | null>(null);
  const { datasource, activityReference, filterParam, total } = useDecompositionRows(
    runId,
    projectionId ?? null,
  );
  const filterActive = !!filterParam && Object.keys(filterParam).length > 0;
  const saveAllCount = total ?? matchedCount ?? null;

  const columns = useMemo(() => {
    if (!colorSpec) return buildRGroupColumns(labels);
    return buildRGroupColumns(labels, buildActivityColumns(colorSpec, activityReference));
  }, [labels, colorSpec, activityReference]);

  const handleRowClick = colorSpec
    ? (row: RGroupRow) => {
        const snapshot = activityValueToCurveSnapshot(row.activitySnapshot, {
          value: row.activity,
          label: colorSpec.label,
        });
        if (!snapshot) return;
        setOpenCurve({
          ...snapshot,
          unit: row.activitySnapshot?.unit ?? null,
          moleculeLabel: row.registration_number ?? row.name ?? row.id,
          channelLabel: colorSpec.label,
        });
      }
    : undefined;

  return (
    <>
      <DataGrid<RGroupRow>
        rowData={undefined}
        datasource={datasource ?? undefined}
        columnDefs={columns}
        height="70vh"
        rowHeight={112}
        getRowId={(params) => params.data.id}
        searchPlaceholder={false}
        onRowClick={handleRowClick}
        toolbarActions={
          onSaveAll ? (
            <Button
              size="sm"
              variant="outline"
              disabled={!canSaveAll(saveAllCount)}
              onClick={() =>
                onSaveAll({
                  count: saveAllCount ?? 0,
                  filter: filterActive ? filterParam : undefined,
                  projectionId: projectionId ?? null,
                })
              }
            >
              {saveAllLabel(saveAllCount, filterActive)}
            </Button>
          ) : undefined
        }
        selectionToolbar={(selected) => (
          <Button
            size="sm"
            onClick={() =>
              onSaveSelection(
                selected.map((r) => ({ id: r.id, label: r.registration_number ?? r.name ?? r.id })),
              )
            }
          >
            Save as collection ({selected.length})
          </Button>
        )}
      />
      <CurveExpandDialog data={openCurve} onOpenChange={(open) => !open && setOpenCurve(null)} />
    </>
  );
}
