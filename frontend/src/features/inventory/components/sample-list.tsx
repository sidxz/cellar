"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState } from "@/shared/components/empty-state";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Move, Package, Pipette, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  type SampleGlobalParams,
  useAliquotSample,
  useDisposeSample,
  useMoveSample,
  useSamplesByBatch,
  useSamplesGlobal,
} from "../hooks/use-samples";
import { useStorageLocations } from "../hooks/use-storage-locations";
import {
  CONTAINER_TYPE_LABELS,
  type ContainerType,
  SAMPLE_STATUS_LABELS,
  type Sample,
  type SampleListItem,
  type SampleStatus,
  type StorageLocation,
} from "../types";

interface SampleListProps {
  batchId?: string;
}

const TERMINAL_STATUSES = new Set(["depleted", "disposed"]);

export function SampleList({ batchId }: SampleListProps) {
  const { data: samples, isLoading } = useSamplesByBatch(batchId);
  const [aliquotSample, setAliquotSample] = useState<Sample | null>(null);
  const [moveSample, setMoveSample] = useState<Sample | null>(null);
  const [disposeSample, setDisposeSample] = useState<Sample | null>(null);

  const columnDefs = useMemo<ColDef<Sample>[]>(
    () => [
      {
        headerName: "Barcode",
        field: "barcode",
        cellClass: "font-mono text-sm",
        flex: 1,
        minWidth: 120,
      },
      {
        headerName: "Container",
        field: "container_type",
        width: 120,
        valueFormatter: (p) => CONTAINER_TYPE_LABELS[p.value as ContainerType] ?? p.value,
      },
      {
        headerName: "Amount",
        width: 110,
        valueGetter: (p) => (p.data ? `${p.data.amount_value} ${p.data.amount_unit}` : ""),
      },
      {
        headerName: "Status",
        field: "status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<Sample>) => (
          <StatusBadge
            status={params.value}
            label={SAMPLE_STATUS_LABELS[params.value as SampleStatus] ?? params.value}
          />
        ),
      },
      {
        headerName: "Solvent",
        field: "solvent",
        width: 100,
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "F/T",
        field: "freeze_thaw_count",
        width: 60,
      },
      {
        headerName: "",
        field: "id",
        width: 120,
        sortable: false,
        filter: false,
        resizable: false,
        cellRenderer: (params: ICellRendererParams<Sample>) => {
          const sample = params.data;
          if (!sample || TERMINAL_STATUSES.has(sample.status)) return null;
          return (
            <div className="flex justify-end gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Aliquot"
                aria-label="Aliquot sample"
                onClick={() => setAliquotSample(sample)}
              >
                <Pipette className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Move"
                aria-label="Move sample"
                onClick={() => setMoveSample(sample)}
              >
                <Move className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-destructive"
                title="Dispose"
                aria-label="Dispose sample"
                onClick={() => setDisposeSample(sample)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          );
        },
      },
    ],
    [],
  );

  if (!batchId) {
    return (
      <EmptyState
        icon={Package}
        title="Select a batch"
        description="Select a compound and batch to view samples."
      />
    );
  }

  return (
    <>
      <DataGrid<Sample>
        rowData={samples}
        columnDefs={columnDefs}
        loading={isLoading}
        height="300px"
        suppressFilters
        emptyState={
          <EmptyState
            icon={Package}
            title="No samples"
            description="No samples have been created for this batch yet."
          />
        }
      />

      {aliquotSample && (
        <AliquotDialog
          sample={aliquotSample}
          open={!!aliquotSample}
          onOpenChange={(open) => !open && setAliquotSample(null)}
        />
      )}
      {moveSample && (
        <MoveDialog
          sample={moveSample}
          open={!!moveSample}
          onOpenChange={(open) => !open && setMoveSample(null)}
        />
      )}
      {disposeSample && (
        <DisposeDialog
          sample={disposeSample}
          open={!!disposeSample}
          onOpenChange={(open) => !open && setDisposeSample(null)}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Global Sample List (all samples across batches, for inventory hub)
// ---------------------------------------------------------------------------

interface GlobalSampleListProps {
  params?: SampleGlobalParams;
}

/** Adapts a SampleListItem (flat DTO) to the Sample shape the dialogs expect. */
function asSample(item: SampleListItem): Sample {
  return {
    id: item.id,
    workspace_id: "",
    batch_id: item.batch_id,
    barcode: item.barcode,
    container_type: item.container_type,
    amount_value: item.amount_value,
    amount_unit: item.amount_unit,
    solvent: item.solvent,
    status: item.status,
    location_id: item.location_id,
    freeze_thaw_count: item.freeze_thaw_count,
    low_stock_threshold: item.low_stock_threshold,
  };
}

export function GlobalSampleList({ params }: GlobalSampleListProps) {
  const router = useRouter();
  const { data, isLoading } = useSamplesGlobal(params);
  const [aliquotSample, setAliquotSample] = useState<Sample | null>(null);
  const [moveSample, setMoveSample] = useState<Sample | null>(null);
  const [disposeSample, setDisposeSample] = useState<Sample | null>(null);

  const columnDefs = useMemo<ColDef<SampleListItem>[]>(
    () => [
      {
        headerName: "Barcode",
        field: "barcode",
        cellClass: "font-mono text-sm",
        flex: 1,
        minWidth: 130,
      },
      {
        headerName: "Compound",
        minWidth: 150,
        flex: 1,
        valueGetter: (p) =>
          p.data ? `${p.data.molecule_name} (${p.data.molecule_registration_number})` : "",
      },
      {
        headerName: "Batch #",
        field: "batch_number",
        width: 140,
        cellClass: "font-mono text-sm",
      },
      {
        headerName: "Container",
        field: "container_type",
        width: 110,
        valueFormatter: (p) => CONTAINER_TYPE_LABELS[p.value as ContainerType] ?? p.value,
      },
      {
        headerName: "Amount",
        width: 120,
        valueGetter: (p) => (p.data ? `${p.data.amount_value} ${p.data.amount_unit}` : ""),
        cellClass: (p) => {
          const d = p.data;
          if (
            d &&
            d.status === "available" &&
            d.low_stock_threshold != null &&
            d.amount_value < d.low_stock_threshold
          ) {
            return "text-warning";
          }
          return "";
        },
      },
      {
        headerName: "Status",
        field: "status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<SampleListItem>) => (
          <StatusBadge
            status={params.value}
            label={SAMPLE_STATUS_LABELS[params.value as SampleStatus] ?? params.value}
          />
        ),
      },
      {
        headerName: "Location",
        width: 150,
        valueGetter: (p) =>
          p.data?.location_name ? `${p.data.location_name} (${p.data.location_type})` : "\u2014",
      },
      {
        headerName: "F/T",
        field: "freeze_thaw_count",
        width: 60,
      },
      {
        headerName: "",
        field: "id",
        width: 120,
        sortable: false,
        filter: false,
        resizable: false,
        cellRenderer: (params: ICellRendererParams<SampleListItem>) => {
          const item = params.data;
          if (!item || TERMINAL_STATUSES.has(item.status)) return null;
          return (
            <div className="flex justify-end gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Aliquot"
                onClick={(e) => {
                  e.stopPropagation();
                  setAliquotSample(asSample(item));
                }}
              >
                <Pipette className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Move"
                onClick={(e) => {
                  e.stopPropagation();
                  setMoveSample(asSample(item));
                }}
              >
                <Move className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-destructive"
                title="Dispose"
                onClick={(e) => {
                  e.stopPropagation();
                  setDisposeSample(asSample(item));
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          );
        },
      },
    ],
    [],
  );

  return (
    <>
      <DataGrid<SampleListItem>
        rowData={data?.items}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        onRowClick={(row) => router.push(`/inventory/samples/${row.id}`)}
        emptyState={
          <EmptyState
            icon={Package}
            title="No samples"
            description="No samples match the current filters."
          />
        }
      />

      {aliquotSample && (
        <AliquotDialog
          sample={aliquotSample}
          open={!!aliquotSample}
          onOpenChange={(open) => !open && setAliquotSample(null)}
        />
      )}
      {moveSample && (
        <MoveDialog
          sample={moveSample}
          open={!!moveSample}
          onOpenChange={(open) => !open && setMoveSample(null)}
        />
      )}
      {disposeSample && (
        <DisposeDialog
          sample={disposeSample}
          open={!!disposeSample}
          onOpenChange={(open) => !open && setDisposeSample(null)}
        />
      )}
    </>
  );
}

// --- Inline action dialogs (unchanged) ---

function AliquotDialog({
  sample,
  open,
  onOpenChange,
}: {
  sample: Sample;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useAliquotSample();
  const [amount, setAmount] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Aliquot Sample</DialogTitle>
          <DialogDescription>
            Remove material from {sample.barcode}. Available: {sample.amount_value}{" "}
            {sample.amount_unit}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Amount to remove ({sample.amount_unit})</Label>
          <Input
            type="number"
            placeholder="0.0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            max={sample.amount_value}
          />
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                { sampleId: sample.id, amount: Number.parseFloat(amount) },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={
              !amount ||
              Number.parseFloat(amount) <= 0 ||
              Number.parseFloat(amount) > sample.amount_value ||
              mutation.isPending
            }
          >
            {mutation.isPending ? "Removing..." : "Remove"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MoveDialog({
  sample,
  open,
  onOpenChange,
}: {
  sample: Sample;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useMoveSample();
  const { data: locations } = useStorageLocations();
  const [locationId, setLocationId] = useState(sample.location_id ?? "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Move Sample</DialogTitle>
          <DialogDescription>Move {sample.barcode} to a new location.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Destination</Label>
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
          >
            <option value="">No location</option>
            {locations?.map((loc: StorageLocation) => (
              <option key={loc.id} value={loc.id}>
                {loc.name} ({loc.type})
              </option>
            ))}
          </select>
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                { sampleId: sample.id, locationId: locationId || null },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Moving..." : "Move"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DisposeDialog({
  sample,
  open,
  onOpenChange,
}: {
  sample: Sample;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useDisposeSample();
  const [reason, setReason] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Dispose Sample</DialogTitle>
          <DialogDescription>
            This will permanently mark {sample.barcode} as disposed. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Reason (optional)</Label>
          <Input
            placeholder="e.g., expired, contaminated"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            variant="destructive"
            onClick={() => {
              mutation.mutate(
                { sampleId: sample.id, reason: reason || undefined },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Disposing..." : "Dispose"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
