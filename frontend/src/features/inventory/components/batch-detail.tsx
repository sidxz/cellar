"use client";

import { useState } from "react";
import { Paperclip, Pencil } from "lucide-react";
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
import { DetailShell } from "@/shared/components/detail-shell";
import { EntityLink } from "@/shared/components/entity-link";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useMolecule } from "@/features/chemical-registration/hooks/use-molecules";
import { FileUploadZone, AttachmentList } from "@/features/attachment";
import { useBatch, useUpdateBatch } from "../hooks/use-batches";
import { SampleList } from "./sample-list";
import { BATCH_SOURCE_LABELS, type Batch, type BatchSource } from "../types";

interface BatchDetailProps {
  batchId: string;
}

export function BatchDetail({ batchId }: BatchDetailProps) {
  const query = useBatch(batchId);
  const { data: molecule } = useMolecule(query.data?.molecule_id);
  const { data: orgs } = useOrganizations();
  const [editOpen, setEditOpen] = useState(false);

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory"
        backLabel="Back to Inventory"
        title={(b) => b.batch_number || "Batch"}
        notFoundMessage="Batch not found."
        actions={() => (
          <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
            <Pencil className="mr-2 h-4 w-4" />
            Edit
          </Button>
        )}
      >
        {(batch) => {
          const supplier = orgs?.find((o) => o.id === batch.supplier_org_id);
          return (
            <>
              {molecule && (
                <p className="-mt-3 text-muted-foreground">
                  Batch of{" "}
                  <EntityLink
                    type="compound"
                    id={batch.molecule_id}
                    label={`${molecule.registration_number} — ${molecule.name}`}
                  />
                </p>
              )}

              <Badge variant="outline">
                {BATCH_SOURCE_LABELS[batch.source as BatchSource] ?? batch.source}
              </Badge>

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

              {/* Files */}
              <div>
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <Paperclip className="h-4 w-4" />
                  Files
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Attachments associated with this batch.
                </p>
                <div className="mt-4 space-y-6">
                  <FileUploadZone entityType="batch" entityId={batchId} />
                  <AttachmentList entityType="batch" entityId={batchId} />
                </div>
              </div>
            </>
          );
        }}
      </DetailShell>

      {query.data && (
        <EditBatchDialog
          batch={query.data}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      )}
    </>
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
