"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Boxes } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { EmptyState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import {
  useBatchesByMolecule,
  useBatchesGlobal,
  type BatchGlobalParams,
} from "../hooks/use-batches";
import {
  BATCH_SOURCE_LABELS,
  type Batch,
  type BatchListItem,
  type BatchSource,
} from "../types";

// ---------------------------------------------------------------------------
// ScopedBatchList — batches for a single molecule (compound detail page)
// ---------------------------------------------------------------------------

interface ScopedBatchListProps {
  moleculeId?: string;
  onSelectBatch?: (batchId: string | null) => void;
}

export function ScopedBatchList({
  moleculeId,
  onSelectBatch,
}: ScopedBatchListProps) {
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

// Backward-compatible alias for existing imports
export { ScopedBatchList as BatchList };

// ---------------------------------------------------------------------------
// GlobalBatchList — all batches across compounds (inventory hub)
// ---------------------------------------------------------------------------

interface GlobalBatchListProps {
  params?: BatchGlobalParams;
}

export function GlobalBatchList({ params }: GlobalBatchListProps) {
  const router = useRouter();
  const { data, isLoading } = useBatchesGlobal(params);

  const columnDefs = useMemo<ColDef<BatchListItem>[]>(
    () => [
      {
        headerName: "Batch #",
        field: "batch_number",
        cellClass: "font-mono text-sm",
        flex: 1,
        minWidth: 140,
      },
      {
        headerName: "Compound",
        flex: 1,
        minWidth: 160,
        valueGetter: (p) =>
          p.data
            ? `${p.data.molecule_name} (${p.data.molecule_registration_number})`
            : "",
      },
      {
        headerName: "Source",
        field: "source",
        width: 130,
        cellRenderer: (params: ICellRendererParams<BatchListItem>) => (
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
        headerName: "Samples",
        field: "sample_count",
        width: 100,
        cellRenderer: (params: ICellRendererParams<BatchListItem>) => {
          if (params.data == null) return null;
          return (
            <span className="flex items-center gap-1">
              {params.data.sample_count}
              {params.data.has_low_stock_sample && (
                <AlertTriangle className="h-3.5 w-3.5 text-yellow-500" />
              )}
            </span>
          );
        },
      },
      {
        headerName: "Created",
        field: "created_at",
        width: 120,
        valueFormatter: (p) =>
          p.value ? new Date(p.value).toLocaleDateString() : "\u2014",
      },
    ],
    []
  );

  return (
    <DataGrid<BatchListItem>
      rowData={data?.items}
      columnDefs={columnDefs}
      loading={isLoading}
      height="500px"
      onRowClick={(batch) => router.push(`/inventory/batches/${batch.id}`)}
      emptyState={
        <EmptyState
          icon={Boxes}
          title="No batches"
          description="No batches have been registered yet."
        />
      }
    />
  );
}
