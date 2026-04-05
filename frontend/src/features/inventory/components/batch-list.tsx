"use client";

import { useMemo } from "react";
import { Boxes } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useBatchesByMolecule } from "../hooks/use-batches";
import { BATCH_SOURCE_LABELS, type Batch, type BatchSource } from "../types";

interface BatchListProps {
  moleculeId?: string;
  onSelectBatch?: (batchId: string | null) => void;
}

export function BatchList({ moleculeId, onSelectBatch }: BatchListProps) {
  const { data: batches, isLoading } = useBatchesByMolecule(moleculeId);

  const columnDefs = useMemo<ColDef<Batch>[]>(
    () => [
      {
        headerName: "Batch #",
        field: "batch_number",
        cellClass: "font-mono text-sm",
        flex: 1,
        minWidth: 120,
      },
      {
        headerName: "Source",
        field: "source",
        width: 130,
        cellRenderer: (params: ICellRendererParams<Batch>) => (
          <Badge variant="outline">
            {BATCH_SOURCE_LABELS[params.value as BatchSource] ?? params.value}
          </Badge>
        ),
      },
      {
        headerName: "Amount",
        width: 120,
        valueGetter: (p) =>
          p.data ? `${p.data.amount_value} ${p.data.amount_unit}` : "",
      },
      {
        headerName: "Purity",
        field: "purity",
        width: 90,
        valueFormatter: (p) => (p.value != null ? `${p.value}%` : "\u2014"),
      },
      {
        headerName: "Salt Form",
        field: "salt_form",
        width: 110,
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "Appearance",
        field: "appearance",
        flex: 1,
        minWidth: 100,
        cellClass: "text-muted-foreground",
        valueFormatter: (p) => p.value ?? "\u2014",
      },
    ],
    []
  );

  if (!moleculeId) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Boxes className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Select a compound</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Select a compound from the Compounds page to view its batches.
        </p>
      </div>
    );
  }

  return (
    <DataGrid<Batch>
      rowData={batches}
      columnDefs={columnDefs}
      loading={isLoading}
      height="300px"
      suppressFilters
      onRowClick={
        onSelectBatch
          ? (batch) => onSelectBatch(batch.id)
          : (batch) => {
              window.location.href = `/inventory/batches/${batch.id}`;
            }
      }
      emptyState={
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <Boxes className="h-12 w-12 text-muted-foreground/40" />
          <h3 className="mt-4 text-lg font-semibold">No batches</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            No batches have been created for this compound yet.
          </p>
        </div>
      }
    />
  );
}
