"use client";

import { useState, useMemo } from "react";
import { Package, Pipette, Move, Trash2 } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
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
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import {
  useAliquotSample,
  useDisposeSample,
  useMoveSample,
  useSamplesByBatch,
} from "../hooks/use-samples";
import { useStorageLocations } from "../hooks/use-storage-locations";
import {
  CONTAINER_TYPE_LABELS,
  SAMPLE_STATUS_LABELS,
  type ContainerType,
  type Sample,
  type SampleStatus,
  type StorageLocation,
} from "../types";

interface SampleListProps {
  batchId?: string;
}

function statusBadgeVariant(
  status: SampleStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "available":
      return "default";
    case "quarantined":
      return "secondary";
    case "depleted":
    case "expired":
    case "disposed":
      return "destructive";
    default:
      return "outline";
  }
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
        valueFormatter: (p) =>
          CONTAINER_TYPE_LABELS[p.value as ContainerType] ?? p.value,
      },
      {
        headerName: "Amount",
        width: 110,
        valueGetter: (p) =>
          p.data ? `${p.data.amount_value} ${p.data.amount_unit}` : "",
      },
      {
        headerName: "Status",
        field: "status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<Sample>) => (
          <Badge variant={statusBadgeVariant(params.value as SampleStatus)}>
            {SAMPLE_STATUS_LABELS[params.value as SampleStatus] ?? params.value}
          </Badge>
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
                onClick={() => setAliquotSample(sample)}
              >
                <Pipette className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Move"
                onClick={() => setMoveSample(sample)}
              >
                <Move className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-destructive"
                title="Dispose"
                onClick={() => setDisposeSample(sample)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          );
        },
      },
    ],
    []
  );

  if (!batchId) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Package className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Select a batch</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Select a compound and batch to view samples.
        </p>
      </div>
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
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
            <Package className="h-12 w-12 text-muted-foreground/40" />
            <h3 className="mt-4 text-lg font-semibold">No samples</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              No samples have been created for this batch yet.
            </p>
          </div>
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
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Aliquot Sample</DialogTitle>
          <DialogDescription>
            Remove material from {sample.barcode}. Available:{" "}
            {sample.amount_value} {sample.amount_unit}
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
                { sampleId: sample.id, amount: parseFloat(amount) },
                { onSuccess: () => onOpenChange(false) }
              );
            }}
            disabled={
              !amount ||
              parseFloat(amount) <= 0 ||
              parseFloat(amount) > sample.amount_value ||
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
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Move Sample</DialogTitle>
          <DialogDescription>
            Move {sample.barcode} to a new location.
          </DialogDescription>
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
                { onSuccess: () => onOpenChange(false) }
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
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Dispose Sample</DialogTitle>
          <DialogDescription>
            This will permanently mark {sample.barcode} as disposed. This action
            cannot be undone.
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
                { onSuccess: () => onOpenChange(false) }
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
