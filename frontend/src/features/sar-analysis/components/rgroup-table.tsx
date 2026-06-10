"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { DoseResponseCell } from "@/features/research-organization/components/search/dose-response-cell";
import type { ActivityValue } from "@/features/research-organization/types";
import {
  type CurveSnapshot,
  DoseResponseFigure,
} from "@/features/screening-assay/components/dose-response-figure";
import { structureColumn } from "@/features/screening-assay/components/grid-columns";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Button } from "@/shared/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/shared/components/ui/dialog";
import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { useState } from "react";
import { type SarColorSpec, colorSpecScalar } from "../lib/sar-color-spec";

export interface RGroupTableProps {
  decomposition: RGroupDecompositionResponse;
  molecules: Molecule[];
  onSaveSelection: (moleculeIds: string[]) => void;
  /** When set, the table appends an activity value column + plot column for
   *  the named (protocol, readout/intercept) pair and shades the value cells
   *  by potency relative to the most-potent row. Null/omitted ⇒ Plan A
   *  behavior (no activity columns, no row-click curve). */
  colorSpec?: SarColorSpec | null;
  /** Activity cell per molecule id (from `useSarActivity`). Keyed by the same
   *  `molecule_id` the rows are keyed by. */
  activityByMolecule?: Record<string, ActivityValue | undefined>;
}

/**
 * One grid row per matched R-group assignment, joined to its molecule by id.
 *
 * `clogp` is sourced from the molecule's calculated `descriptors.logp` (RDKit
 * Crippen cLogP) — the row/column key stays `clogp` for the displayed header,
 * but the value comes off the real `logp` descriptor field.
 */
export interface RGroupRow {
  id: string;
  registration_number: string | null;
  name: string | null;
  smiles: string | null;
  rgroups: Record<string, string>;
  mw: number | null;
  clogp: number | null;
  tpsa: number | null;
}

export function buildRGroupRows(
  d: RGroupDecompositionResponse,
  molecules: Molecule[],
): RGroupRow[] {
  const byId = new Map(molecules.map((m) => [m.id, m]));
  return d.assignments.map((a) => {
    const m = byId.get(a.molecule_id);
    return {
      id: a.molecule_id,
      registration_number: m?.registration_number ?? null,
      name: m?.name ?? null,
      smiles: m?.structure?.smiles ?? null,
      rgroups: a.rgroups,
      mw: m?.descriptors?.molecular_weight ?? null,
      clogp: m?.descriptors?.logp ?? null,
      tpsa: m?.descriptors?.tpsa ?? null,
    };
  });
}

/**
 * Structure + Compound + one column per R-group + physchem (MW/cLogP/TPSA).
 *
 * `activityColumns` (optional) are inserted BETWEEN the R-group columns and the
 * physchem columns — so the activity the chemist colors by reads adjacent to
 * the substituents that drive it, with the physchem properties trailing. When
 * omitted (Plan A callers / the builder tests) the column set is unchanged.
 */
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
      sortable: false,
      valueGetter: (p) => p.data?.rgroups[label] ?? "",
      cellRenderer: (p: ICellRendererParams<RGroupRow>) => {
        const smi = p.data?.rgroups[label];
        if (!smi) return <span className="text-muted-foreground">—</span>;
        return (
          <div className="flex h-full items-center gap-1.5">
            <StructureThumbnail smiles={smi} size={64} className="shrink-0" />
            <span className="font-mono text-[11px] break-all">{smi}</span>
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

// ─── Activity: potency reference + shading (pure, exported for B4 reuse) ──────

/**
 * The most-potent reference scalar across the table = the minimum non-null
 * value. Assumes a LOWER-is-better scale (IC50 / EC50 / Kd potency): a smaller
 * fitted concentration means a more potent compound, so the minimum anchors the
 * "best" end of the shading ramp. Returns null when there are no non-null
 * scalars (no activity to anchor against).
 */
export function pickReference(scalars: (number | null)[]): number | null {
  let ref: number | null = null;
  for (const s of scalars) {
    if (s == null || !Number.isFinite(s)) continue;
    if (ref == null || s < ref) ref = s;
  }
  return ref;
}

/**
 * A tailwind bg+text class on a green→red potency ramp, keyed on the fold
 * difference `scalar / reference` (≈ `log10` buckets). LOWER scalar = more
 * potent ⇒ greener; larger fold-off from the most-potent reference ⇒ redder.
 *
 * Buckets (fold vs. the most-potent reference):
 *   ≤1×   → green  (the reference itself + anything at least as potent)
 *   ≤3×   → green, lighter
 *   ≤10×  → amber
 *   ≤100× → orange
 *   >100× → red
 *
 * Returns "" when the scalar or reference is null (nothing to shade) — the
 * grid then renders the cell with its default background.
 */
export function potencyShade(scalar: number | null, reference: number | null): string {
  if (scalar == null || reference == null) return "";
  if (!Number.isFinite(scalar) || !Number.isFinite(reference) || reference <= 0) return "";

  const fold = scalar / reference;
  if (fold <= 1) return "bg-green-600/30 text-green-900 dark:text-green-100";
  if (fold <= 3) return "bg-green-500/20 text-green-900 dark:text-green-100";
  if (fold <= 10) return "bg-amber-500/20 text-amber-900 dark:text-amber-100";
  if (fold <= 100) return "bg-orange-500/25 text-orange-900 dark:text-orange-100";
  return "bg-red-600/30 text-red-900 dark:text-red-100";
}

/**
 * Map a DR `ActivityValue` to the shared {@link CurveSnapshot} the
 * `DoseResponseFigure` renders. Faithful copy of the mapping in
 * `dose-response-cell.tsx` (so the row-click expand draws the same picture as
 * the search-grid plot cell). Returns null for cells that don't carry a
 * fittable dose-response curve (readout-sourced, no raw points, no params).
 */
export function snapshotFromActivity(av: ActivityValue | undefined): CurveSnapshot | null {
  if (
    !av ||
    !av.raw_data ||
    av.raw_data.length === 0 ||
    av.source !== "dose_response" ||
    av.curve_params == null ||
    av.value == null
  ) {
    return null;
  }
  return {
    fitted_value: av.value,
    top: av.curve_params.top,
    bottom: av.curve_params.bottom,
    hill_slope: av.curve_params.hill_slope,
    r_squared: av.r_squared,
    curve_class: av.curve_params.curve_class ?? null,
    raw_data: av.raw_data,
    additional_curves: av.additional_curves ?? null,
    aggregate: av.aggregate ?? null,
  };
}

/**
 * The two activity columns the table appends when a `colorSpec` is set:
 *   - `activity:value` — the named scalar, formatted to 3 sig figs + unit,
 *     with the cell background shaded by {@link potencyShade} vs `reference`.
 *   - `activity:plot` — the shared {@link DoseResponseCell} (renders the curve
 *     for DR sources; an em-dash for readout_data sources, which is fine).
 *
 * `reference` is the most-potent scalar across the visible rows (see
 * {@link pickReference}); pass it in so the ramp anchors consistently for the
 * whole table rather than per cell.
 */
export function buildActivityColumns(
  colorSpec: SarColorSpec,
  activityByMolecule: Record<string, ActivityValue | undefined>,
  reference: number | null,
): ColDef<RGroupRow>[] {
  const scalarFor = (row: RGroupRow | undefined): number | null =>
    row ? colorSpecScalar(activityByMolecule[row.id], colorSpec) : null;

  return [
    {
      headerName: colorSpec.label,
      colId: "activity:value",
      width: 150,
      type: "numericColumn",
      valueGetter: (p) => scalarFor(p.data),
      // 3 significant figures matches potency convention (values span orders of
      // magnitude — fixed decimals would lose precision on sub-nM and clutter
      // on µM). Unit comes off the cell, like the search grid's readout column.
      valueFormatter: (p) => {
        if (p.value == null) return "—";
        const av = p.data ? activityByMolecule[p.data.id] : undefined;
        const unit = av?.unit ? ` ${av.unit}` : "";
        return `${Number(p.value).toPrecision(3)}${unit}`;
      },
      cellClass: (p) => potencyShade(scalarFor(p.data), reference),
    },
    {
      headerName: "Plot",
      colId: "activity:plot",
      width: 240,
      sortable: false,
      filter: false,
      cellRenderer: (p: ICellRendererParams<RGroupRow>) => (
        <DoseResponseCell value={p.data ? activityByMolecule[p.data.id] : undefined} />
      ),
    },
  ];
}

/**
 * R-group decomposition table: structure + a column per R-group substituent +
 * physchem (MW/cLogP/TPSA), with multi-select → "Save as collection".
 *
 * Selection is wired through {@link DataGrid}'s `selectionToolbar` render prop,
 * which on its own enables `rowSelection="multiple"` and prepends the checkbox
 * column. (We must NOT also pass `enableMultiSelect` — the grid only renders
 * `selectionToolbar` when `enableMultiSelect` is falsy.)
 */
export function RGroupTable({
  decomposition,
  molecules,
  onSaveSelection,
  colorSpec,
  activityByMolecule,
}: RGroupTableProps) {
  // Curve clicked open in the row-click dialog. Only DR rows produce a
  // snapshot; readout_data rows (or rows with no activity) leave it null so the
  // click is a no-op.
  const [openCurve, setOpenCurve] = useState<{
    snapshot: CurveSnapshot;
    unit: string | null;
  } | null>(null);

  const rows = buildRGroupRows(decomposition, molecules);

  // Anchor the potency ramp to the most-potent (minimum) scalar across the
  // visible rows, then build + insert the activity columns. Both are gated on
  // `colorSpec` — without it the table is exactly Plan A.
  const activityMap = activityByMolecule ?? {};
  const reference = colorSpec
    ? pickReference(rows.map((r) => colorSpecScalar(activityMap[r.id], colorSpec)))
    : null;
  const activityColumns = colorSpec ? buildActivityColumns(colorSpec, activityMap, reference) : [];
  const columns = buildRGroupColumns(decomposition.rgroup_labels, activityColumns);

  // Row click → expand the clicked row's DR curve. Wired only when coloring by
  // an activity spec; a no-op for rows without a fittable curve.
  const handleRowClick = colorSpec
    ? (row: RGroupRow) => {
        const av = activityMap[row.id];
        const snapshot = snapshotFromActivity(av);
        if (snapshot) setOpenCurve({ snapshot, unit: av?.unit ?? null });
      }
    : undefined;

  return (
    <>
      <DataGrid<RGroupRow>
        rowData={rows}
        columnDefs={columns}
        height="70vh"
        rowHeight={112}
        getRowId={(params) => params.data.id}
        onRowClick={handleRowClick}
        selectionToolbar={(selected) => (
          <Button size="sm" onClick={() => onSaveSelection(selected.map((r) => r.id))}>
            Save as collection ({selected.length})
          </Button>
        )}
      />
      <Dialog open={openCurve != null} onOpenChange={(open) => !open && setOpenCurve(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{colorSpec?.label ?? "Dose-response"}</DialogTitle>
          </DialogHeader>
          {openCurve ? (
            <DoseResponseFigure
              curve={openCurve.snapshot}
              size="expand"
              interactive
              unit={openCurve.unit}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
