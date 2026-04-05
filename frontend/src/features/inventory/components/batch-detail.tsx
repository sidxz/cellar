"use client";

import { useState } from "react";
import { ArrowLeft, Boxes, Pencil } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
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
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useMolecule } from "@/features/chemical-registration/hooks/use-molecules";
import { useBatch, useUpdateBatch } from "../hooks/use-batches";
import { SampleList } from "./sample-list";
import { BATCH_SOURCE_LABELS, type Batch, type BatchSource } from "../types";

interface BatchDetailProps {
  batchId: string;
}

export function BatchDetail({ batchId }: BatchDetailProps) {
  const { data: batch, isLoading } = useBatch(batchId);
  const { data: molecule } = useMolecule(batch?.molecule_id);
  const { data: orgs } = useOrganizations();
  const [editOpen, setEditOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!batch) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Boxes className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Batch not found</h3>
      </div>
    );
  }

  const supplier = orgs?.find((o) => o.id === batch.supplier_org_id);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/inventory">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight font-mono">
              {batch.batch_number}
            </h1>
            <Badge variant="outline">
              {BATCH_SOURCE_LABELS[batch.source as BatchSource] ?? batch.source}
            </Badge>
          </div>
          {molecule && (
            <p className="mt-1 text-muted-foreground">
              Batch of{" "}
              <EntityLink
                type="compound"
                id={batch.molecule_id}
                label={`${molecule.registration_number} — ${molecule.name}`}
              />
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
          <Pencil className="mr-2 h-4 w-4" />
          Edit
        </Button>
      </div>

      {/* Properties */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Properties</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Amount</p>
            <p className="font-medium">
              {batch.amount_value} {batch.amount_unit}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Purity</p>
            <p className="font-medium">
              {batch.purity != null ? `${batch.purity}%` : "\u2014"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Salt Form</p>
            <p className="font-medium">{batch.salt_form ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Appearance</p>
            <p className="font-medium">{batch.appearance ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Chemist</p>
            <p className="font-medium">{batch.chemist}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Synthesis Date</p>
            <p className="font-medium">{batch.synthesis_date ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Expiry Date</p>
            <p className="font-medium">{batch.expiry_date ?? "\u2014"}</p>
          </div>
          {supplier && (
            <div>
              <p className="text-xs text-muted-foreground">Supplier</p>
              <p className="font-medium">{supplier.name}</p>
            </div>
          )}
          {batch.vendor_catalog_number && (
            <div>
              <p className="text-xs text-muted-foreground">Catalog #</p>
              <p className="font-mono text-sm">{batch.vendor_catalog_number}</p>
            </div>
          )}
          {batch.vendor_lot_number && (
            <div>
              <p className="text-xs text-muted-foreground">Lot #</p>
              <p className="font-mono text-sm">{batch.vendor_lot_number}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Samples */}
      <div>
        <h2 className="text-lg font-semibold">Samples</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Physical samples derived from this batch.
        </p>
        <div className="mt-4">
          <SampleList batchId={batchId} />
        </div>
      </div>

      {batch && (
        <EditBatchDialog
          batch={batch}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      )}
    </div>
  );
}

function EditBatchDialog({
  batch,
  open,
  onOpenChange,
}: {
  batch: Batch;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useUpdateBatch(batch.id);
  const [saltForm, setSaltForm] = useState(batch.salt_form ?? "");
  const [purity, setPurity] = useState(batch.purity?.toString() ?? "");
  const [amountValue, setAmountValue] = useState(batch.amount_value.toString());
  const [amountUnit, setAmountUnit] = useState(batch.amount_unit);
  const [appearance, setAppearance] = useState(batch.appearance ?? "");
  const [expiryDate, setExpiryDate] = useState(batch.expiry_date ?? "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Batch</DialogTitle>
          <DialogDescription>
            Update properties for {batch.batch_number}.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Amount</Label>
              <Input
                type="number"
                value={amountValue}
                onChange={(e) => setAmountValue(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Unit</Label>
              <Input
                value={amountUnit}
                onChange={(e) => setAmountUnit(e.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Purity (%)</Label>
            <Input
              type="number"
              placeholder="e.g. 99.5"
              value={purity}
              onChange={(e) => setPurity(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label>Salt Form</Label>
            <Input
              placeholder="e.g. hydrochloride"
              value={saltForm}
              onChange={(e) => setSaltForm(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label>Appearance</Label>
            <Input
              placeholder="e.g. white powder"
              value={appearance}
              onChange={(e) => setAppearance(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label>Expiry Date</Label>
            <Input
              type="date"
              value={expiryDate}
              onChange={(e) => setExpiryDate(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  amount_value: parseFloat(amountValue) || null,
                  amount_unit: amountUnit || null,
                  purity: purity ? parseFloat(purity) : null,
                  salt_form: saltForm || null,
                  appearance: appearance || null,
                  expiry_date: expiryDate || null,
                },
                { onSuccess: () => onOpenChange(false) }
              );
            }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
