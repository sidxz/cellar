"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { structureColumn } from "@/features/screening-assay/components/grid-columns";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Button } from "@/shared/components/ui/button";
import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import type { ColDef } from "ag-grid-community";

export interface RGroupTableProps {
  decomposition: RGroupDecompositionResponse;
  molecules: Molecule[];
  onSaveSelection: (moleculeIds: string[]) => void;
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

export function buildRGroupColumns(labels: string[]): ColDef<RGroupRow>[] {
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
      cellRenderer: (p: { data?: RGroupRow }) => {
        const smi = p.data?.rgroups[label];
        if (!smi) return <span className="text-muted-foreground">—</span>;
        return (
          <div className="flex h-full items-center gap-1.5">
            <StructureThumbnail
              smiles={smi}
              size={40}
              className="shrink-0 rounded border bg-background"
            />
            <span className="font-mono text-[11px] break-all">{smi}</span>
          </div>
        );
      },
    });
  }
  cols.push(
    {
      headerName: "MW",
      colId: "mw",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.mw ?? null,
    },
    {
      headerName: "cLogP",
      colId: "clogp",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.clogp ?? null,
    },
    {
      headerName: "TPSA",
      colId: "tpsa",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.tpsa ?? null,
    },
  );
  return cols;
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
export function RGroupTable({ decomposition, molecules, onSaveSelection }: RGroupTableProps) {
  const rows = buildRGroupRows(decomposition, molecules);
  const columns = buildRGroupColumns(decomposition.rgroup_labels);
  return (
    <DataGrid<RGroupRow>
      rowData={rows}
      columnDefs={columns}
      height="70vh"
      rowHeight={56}
      getRowId={(params) => params.data.id}
      selectionToolbar={(selected) => (
        <Button size="sm" onClick={() => onSaveSelection(selected.map((r) => r.id))}>
          Save as collection ({selected.length})
        </Button>
      )}
    />
  );
}
