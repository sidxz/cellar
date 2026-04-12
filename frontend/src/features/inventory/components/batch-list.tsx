"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { Boxes } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { EmptyState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useBatchesByMolecule } from "../hooks/use-batches";
import { BATCH_SOURCE_LABELS, type Batch, type BatchSource } from "../types";

interface BatchListProps {
  moleculeId?: string;
  onSelectBatch?: (batchId: string | null) => void;
}

export function BatchList({ moleculeId, onSelectBatch }: BatchListProps) {
  const router = useRouter();
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
        field: "salt_name",
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
      <EmptyState
        icon={Boxes}
        title="Select a compound"
        description="Select a compound from the Compounds page to view its batches."
      />
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
              router.push(`/inventory/batches/${batch.id}`);
            }
      }
      emptyState={
        <EmptyState
          icon={Boxes}
          title="No batches"
          description="No batches have been created for this compound yet."
        />
      }
    />
  );
}
