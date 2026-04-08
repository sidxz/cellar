"use client";

import { useState } from "react";
import { ArrowLeft, Package, Pipette, Move, Trash2, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { EmptyState } from "@/shared/components/empty-state";
import { Card } from "@/shared/components/ui/card";
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
import { Skeleton } from "@/shared/components/ui/skeleton";
import { EntityLink } from "@/shared/components/entity-link";
import { MoleculeName } from "@/shared/components/entity-name";
import { AttachmentList, FileUploadZone } from "@/features/attachment";
import { useBatch } from "../hooks/use-batches";
import {
  useAliquotSample,
  useClearQuarantine,
  useDisposeSample,
  useMoveSample,
  useQuarantineSample,
  useSample,
} from "../hooks/use-samples";
import { useStorageLocations } from "../hooks/use-storage-locations";
import {
  CONTAINER_TYPE_LABELS,
  SAMPLE_STATUS_LABELS,
  type ContainerType,
  type SampleStatus,
  type StorageLocation,
} from "../types";

interface SampleDetailProps {
  sampleId: string;
}

const TERMINAL_STATUSES = new Set(["depleted", "disposed"]);

export function SampleDetail({ sampleId }: SampleDetailProps) {
  const { data: sample, isLoading } = useSample(sampleId);
  const { data: batch } = useBatch(sample?.batch_id);
  const { data: locations } = useStorageLocations();

  const [aliquotOpen, setAliquotOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [disposeOpen, setDisposeOpen] = useState(false);
  const [quarantineOpen, setQuarantineOpen] = useState(false);
  const clearQuarantine = useClearQuarantine();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!sample) {
    return (
      <EmptyState
        icon={Package}
        title="Sample not found"
        description="The sample may have been deleted or does not exist."
      />
    );
  }

  const isTerminal = TERMINAL_STATUSES.has(sample.status);
  const location = locations?.find((l) => l.id === sample.location_id);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link
            href={
              batch ? `/inventory/batches/${batch.id}` : "/inventory"
            }
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight font-mono">
              {sample.barcode}
            </h1>
            <StatusBadge
              status={sample.status}
              label={SAMPLE_STATUS_LABELS[sample.status as SampleStatus] ?? sample.status}
            />
          </div>
          {batch && (
            <p className="mt-1 text-muted-foreground">
              Sample from batch{" "}
              <EntityLink
                type="batch"
                id={batch.id}
                label={batch.batch_number}
              />
            </p>
          )}
        </div>
        {!isTerminal && (
          <div className="flex gap-2">
            {sample.status === "quarantined" ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => clearQuarantine.mutate(sample.id)}
                disabled={clearQuarantine.isPending}
              >
                <ShieldCheck className="mr-2 h-4 w-4" />
                {clearQuarantine.isPending ? "Clearing..." : "Clear Quarantine"}
              </Button>
            ) : (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setAliquotOpen(true)}
                >
                  <Pipette className="mr-2 h-4 w-4" />
                  Aliquot
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setMoveOpen(true)}
                >
                  <Move className="mr-2 h-4 w-4" />
                  Move
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setQuarantineOpen(true)}
                >
                  <ShieldAlert className="mr-2 h-4 w-4" />
                  Quarantine
                </Button>
              </>
            )}
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setDisposeOpen(true)}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Dispose
            </Button>
          </div>
        )}
      </div>

      {/* Properties */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Properties</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Container</p>
            <p className="font-medium">
              {CONTAINER_TYPE_LABELS[sample.container_type as ContainerType] ??
                sample.container_type}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Amount</p>
            <p className="font-medium">
              {sample.amount_value} {sample.amount_unit}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Solvent</p>
            <p className="font-medium">{sample.solvent ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Freeze/Thaw Count</p>
            <p className="font-medium">{sample.freeze_thaw_count}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Location</p>
            <p className="font-medium">
              {location ? `${location.name} (${location.type})` : "\u2014"}
            </p>
          </div>
          {sample.low_stock_threshold != null && (
            <div>
              <p className="text-xs text-muted-foreground">
                Low Stock Threshold
              </p>
              <p className="font-medium">{sample.low_stock_threshold}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Navigation links */}
      {batch && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Related</h2>
          <div className="mt-4 flex gap-6">
            <div>
              <p className="text-xs text-muted-foreground">Batch</p>
              <EntityLink
                type="batch"
                id={batch.id}
                label={batch.batch_number}
              />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Compound</p>
              <a
                href={`/compounds/${batch.molecule_id}`}
                className="text-sm text-primary hover:underline underline-offset-4"
              >
                <MoleculeName id={batch.molecule_id} />
              </a>
            </div>
          </div>
        </Card>
      )}

      {/* Attachments */}
      {sample && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-4">Files</h2>
          <FileUploadZone entityType="sample" entityId={sampleId} />
          <AttachmentList entityType="sample" entityId={sampleId} />
        </Card>
      )}

      {/* Inline action dialogs */}
      {sample && !isTerminal && (
        <>
          <AliquotDialog
            sample={sample}
            open={aliquotOpen}
            onOpenChange={setAliquotOpen}
          />
          <MoveDialog
            sample={sample}
            locations={locations ?? []}
            open={moveOpen}
            onOpenChange={setMoveOpen}
          />
          <DisposeDialog
            sample={sample}
            open={disposeOpen}
            onOpenChange={setDisposeOpen}
          />
          <QuarantineDialog
            sample={sample}
            open={quarantineOpen}
            onOpenChange={setQuarantineOpen}
          />
        </>
      )}
    </div>
  );
}

function AliquotDialog({
  sample,
  open,
  onOpenChange,
}: {
  sample: { id: string; barcode: string; amount_value: number; amount_unit: string };
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
                {
                  onSuccess: () => {
                    onOpenChange(false);
                    setAmount("");
                  },
                }
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
  locations,
  open,
  onOpenChange,
}: {
  sample: { id: string; barcode: string; location_id: string | null };
  locations: StorageLocation[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useMoveSample();
  const [locationId, setLocationId] = useState(sample.location_id ?? "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
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
            {locations.map((loc) => (
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
  sample: { id: string; barcode: string };
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

function QuarantineDialog({
  sample,
  open,
  onOpenChange,
}: {
  sample: { id: string; barcode: string };
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useQuarantineSample();
  const [reason, setReason] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Quarantine Sample</DialogTitle>
          <DialogDescription>
            Mark {sample.barcode} as quarantined. It will be unavailable until
            the quarantine is cleared.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label>Reason</Label>
          <Input
            placeholder="e.g., failed QC, contamination suspected"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                { sampleId: sample.id, reason },
                {
                  onSuccess: () => {
                    onOpenChange(false);
                    setReason("");
                  },
                }
              );
            }}
            disabled={!reason.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Quarantining..." : "Quarantine"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
