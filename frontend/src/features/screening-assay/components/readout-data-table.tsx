"use client";

import { useMemo } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EntityLink } from "@/shared/components/entity-link";
import { cn } from "@/shared/lib/utils";
import { useMolecules } from "@/features/chemical-registration/hooks/use-molecules";
import { useProtocol } from "../hooks/use-protocols";
import { useReadoutDataByRun } from "../hooks/use-readout-data";
import type { ReadoutData } from "../types";

interface ReadoutDataTableProps {
  runId: string;
  protocolId: string;
  className?: string;
}

interface PivotRow {
  key: string;
  label: string;
  moleculeId: string;
  batchId: string;
  values: Map<string, ReadoutData>;
}

/** Format a value with qualifier prefix: "85.2", "<12.7", ">1000" */
function formatValue(row: ReadoutData): string {
  if (row.value_numeric === null || row.value_numeric === undefined) {
    return row.value_text ?? "\u2014";
  }
  const prefix =
    row.value_qualifier && row.value_qualifier !== "=" ? row.value_qualifier : "";
  return `${prefix}${row.value_numeric.toFixed(3)}`;
}

export function ReadoutDataTable({
  runId,
  protocolId,
  className,
}: ReadoutDataTableProps) {
  const { data, isLoading } = useReadoutDataByRun(runId);
  const { data: molecules } = useMolecules();
  const { data: protocol } = useProtocol(protocolId);

  const readoutDefs = protocol?.readout_definitions ?? [];

  const molMap = useMemo(() => {
    const m = new Map<string, { reg: string; name: string }>();
    for (const mol of molecules ?? []) {
      m.set(mol.id, { reg: mol.registration_number, name: mol.name });
    }
    return m;
  }, [molecules]);

  // Pivot readout data into rows
  const pivotRows = useMemo<PivotRow[]>(() => {
    if (!data) return [];

    const groups = new Map<string, PivotRow>();
    for (const row of data) {
      const key = `${row.molecule_id}::${row.batch_id}`;
      let group = groups.get(key);
      if (!group) {
        const mol = molMap.get(row.molecule_id);
        group = {
          key,
          label: mol ? `${mol.reg} \u2014 ${mol.name}` : "Unknown compound",
          moleculeId: row.molecule_id,
          batchId: row.batch_id,
          values: new Map(),
        };
        groups.set(key, group);
      }
      group.values.set(row.readout_definition_id, row);
    }
    return Array.from(groups.values());
  }, [data, molMap]);

  // Dynamic columns: Compound + one per readout definition
  const columnDefs = useMemo<ColDef<PivotRow>[]>(() => {
    const cols: ColDef<PivotRow>[] = [
      {
        headerName: "Compound",
        field: "label",
        pinned: "left",
        minWidth: 180,
        flex: 1,
        cellRenderer: (params: ICellRendererParams<PivotRow>) => {
          const row = params.data;
          if (!row) return null;
          return (
            <EntityLink
              type="compound"
              id={row.moleculeId}
              label={row.label}
              className="text-xs"
            />
          );
        },
      },
    ];

    for (const rd of readoutDefs) {
      const baseName = rd.unit ? `${rd.name} (${rd.unit})` : rd.name;
      const headerName = rd.is_calculated ? `${baseName} [calc]` : baseName;
      cols.push({
        headerName,
        headerTooltip: rd.is_calculated && rd.calculation_formula
          ? `Calculated: ${rd.calculation_formula}`
          : undefined,
        colId: rd.id,
        width: 130,
        cellClass: "text-right tabular-nums",
        headerClass: rd.is_calculated
          ? "ag-right-aligned-header italic"
          : "ag-right-aligned-header",
        valueGetter: (p) => {
          const row = p.data?.values.get(rd.id);
          if (!row) return null;
          return row.value_numeric ?? row.value_text ?? null;
        },
        cellRenderer: (params: { data: PivotRow | undefined }) => {
          const row = params.data?.values.get(rd.id);
          if (!row) return <span className="text-muted-foreground">{"\u2014"}</span>;
          return (
            <span
              className={cn(
                row.is_outlier &&
                  "text-destructive line-through decoration-destructive/50"
              )}
              title={row.is_outlier ? "Flagged as outlier" : undefined}
            >
              {formatValue(row)}
            </span>
          );
        },
      });
    }
    return cols;
  }, [readoutDefs]);

  return (
    <div className={className}>
      <DataGrid<PivotRow>
        rowData={pivotRows}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        suppressFilters
        getRowId={(params) => params.data.key}
        emptyState={
          <p className="py-8 text-center text-sm text-muted-foreground">
            No readout data recorded for this run.
          </p>
        }
      />
    </div>
  );
}
