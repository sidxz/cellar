"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";
import { MoleculeSelector } from "./molecule-selector";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useBatchesByMolecule } from "../hooks/use-batches";
import { useSamplesByBatch } from "../hooks/use-samples";
import { useCreateShipment } from "../hooks/use-shipments";
import type { ShipmentItemInput } from "../types/shipment";

interface CreateShipmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** One item row with cascading selectors: compound → batch → sample */
interface ItemRowState {
  _moleculeId: string | null;
  _batchId: string;
  sample_id: string;
  amount_value: number;
  amount_unit: string;
}

const EMPTY_ITEM: ItemRowState = {
  _moleculeId: null,
  _batchId: "",
  sample_id: "",
  amount_value: 0,
  amount_unit: "mg",
};

// ---------------------------------------------------------------------------
// Cascading item row: Compound → Batch → Sample
// ---------------------------------------------------------------------------

function ShipmentItemRow({
  item,
  index,
  canRemove,
  onUpdate,
  onRemove,
}: {
  item: ItemRowState;
  index: number;
  canRemove: boolean;
  onUpdate: <K extends keyof ItemRowState>(key: K, value: ItemRowState[K]) => void;
  onRemove: () => void;
}) {
  const { data: batches, isLoading: batchesLoading } = useBatchesByMolecule(
    item._moleculeId ?? undefined
  );
  const { data: samples, isLoading: samplesLoading } = useSamplesByBatch(
    item._batchId || undefined
  );

  return (
    <div className="rounded-md border p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          Item {index + 1}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-destructive"
          disabled={!canRemove}
          onClick={onRemove}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Row 1: Compound → Batch */}
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1">
          <Label className="text-xs">
            Compound <span className="text-destructive">*</span>
          </Label>
          <MoleculeSelector
            selectedId={item._moleculeId}
            onSelect={(id) => {
              onUpdate("_moleculeId", id);
              onUpdate("_batchId", "");
              onUpdate("sample_id", "");
            }}
          />
        </div>

        <div className="grid gap-1">
          <Label className="text-xs">
            Batch <span className="text-destructive">*</span>
          </Label>
          {item._moleculeId ? (
            <Select
              value={item._batchId}
              onValueChange={(val) => {
                onUpdate("_batchId", val);
                onUpdate("sample_id", "");
              }}
              disabled={batchesLoading}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    batchesLoading
                      ? "Loading batches..."
                      : batches && batches.length === 0
                        ? "No batches found"
                        : "Select batch"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {batches?.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.batch_number}
                    {b.purity ? ` (${b.purity}% pure)` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Select disabled>
              <SelectTrigger>
                <SelectValue placeholder="Select compound first" />
              </SelectTrigger>
              <SelectContent />
            </Select>
          )}
        </div>
      </div>

      {/* Row 2: Sample → Amount */}
      <div className="grid grid-cols-[1fr_auto_auto] gap-3 items-end">
        <div className="grid gap-1">
          <Label className="text-xs">
            Sample <span className="text-destructive">*</span>
          </Label>
          {item._batchId && samples && samples.length > 0 ? (
            <Select
              value={item.sample_id}
              onValueChange={(val) => onUpdate("sample_id", val)}
              disabled={samplesLoading}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    samplesLoading ? "Loading samples..." : "Select sample"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {samples.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.barcode} — {s.amount_value} {s.amount_unit} available
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Select disabled>
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    !item._batchId
                      ? "Select batch first"
                      : samplesLoading
                        ? "Loading..."
                        : "No samples in this batch"
                  }
                />
              </SelectTrigger>
              <SelectContent />
            </Select>
          )}
        </div>

        <div className="grid gap-1 w-24">
          <Label className="text-xs">
            Amount <span className="text-destructive">*</span>
          </Label>
          <Input
            type="number"
            placeholder="0.0"
            min={0}
            value={item.amount_value || ""}
            onChange={(e) =>
              onUpdate("amount_value", parseFloat(e.target.value) || 0)
            }
          />
        </div>

        <div className="grid gap-1 w-20">
          <Label className="text-xs">Unit</Label>
          <Select
            value={item.amount_unit}
            onValueChange={(val) => onUpdate("amount_unit", val)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="mg">mg</SelectItem>
              <SelectItem value="g">g</SelectItem>
              <SelectItem value="mL">mL</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main dialog
// ---------------------------------------------------------------------------

export function CreateShipmentDialog({
  open,
  onOpenChange,
}: CreateShipmentDialogProps) {
  const mutation = useCreateShipment();
  const { data: orgs } = useOrganizations();

  const [destinationOrgId, setDestinationOrgId] = useState("");
  const [carrier, setCarrier] = useState("");
  const [expectedArrivalDate, setExpectedArrivalDate] = useState("");
  const [shippingConditions, setShippingConditions] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<ItemRowState[]>([{ ...EMPTY_ITEM }]);

  function resetForm() {
    setDestinationOrgId("");
    setCarrier("");
    setExpectedArrivalDate("");
    setShippingConditions("");
    setNotes("");
    setItems([{ ...EMPTY_ITEM }]);
  }

  function handleClose(v: boolean) {
    if (!v) resetForm();
    onOpenChange(v);
  }

  function addItem() {
    setItems((prev) => [...prev, { ...EMPTY_ITEM }]);
  }

  function removeItem(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }

  function updateItem<K extends keyof ItemRowState>(
    index: number,
    key: K,
    value: ItemRowState[K]
  ) {
    setItems((prev) =>
      prev.map((item, i) => (i === index ? { ...item, [key]: value } : item))
    );
  }

  const isValid =
    destinationOrgId.trim().length > 0 &&
    items.length > 0 &&
    items.every(
      (it) =>
        it.sample_id.trim().length > 0 &&
        it.amount_value > 0 &&
        it.amount_unit.length > 0
    );

  function handleSubmit() {
    const apiItems: ShipmentItemInput[] = items.map((it) => ({
      sample_id: it.sample_id,
      amount_value: it.amount_value,
      amount_unit: it.amount_unit,
    }));
    mutation.mutate(
      {
        destination_org_id: destinationOrgId.trim(),
        carrier: carrier.trim() || null,
        expected_arrival_date: expectedArrivalDate || null,
        shipping_conditions: shippingConditions.trim() || null,
        notes: notes.trim() || null,
        items: apiItems,
      },
      { onSuccess: () => handleClose(false) }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Shipment</DialogTitle>
          <DialogDescription>
            Select compounds, then pick batches and samples to ship.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Destination */}
          <div className="grid gap-2">
            <Label>
              Destination Organization{" "}
              <span className="text-destructive">*</span>
            </Label>
            <Select value={destinationOrgId} onValueChange={setDestinationOrgId}>
              <SelectTrigger>
                <SelectValue placeholder="Select destination organization" />
              </SelectTrigger>
              <SelectContent>
                {orgs?.map((o) => (
                  <SelectItem key={o.id} value={o.id}>
                    {o.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Carrier + Expected arrival */}
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Carrier</Label>
              <Input
                placeholder="e.g. FedEx, DHL"
                value={carrier}
                onChange={(e) => setCarrier(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Expected Arrival</Label>
              <Input
                type="date"
                value={expectedArrivalDate}
                onChange={(e) => setExpectedArrivalDate(e.target.value)}
              />
            </div>
          </div>

          {/* Shipping conditions */}
          <div className="grid gap-2">
            <Label>Shipping Conditions</Label>
            <Input
              placeholder="e.g. Keep refrigerated at 2-8°C"
              value={shippingConditions}
              onChange={(e) => setShippingConditions(e.target.value)}
            />
          </div>

          {/* Items — compound-first cascade */}
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label>
                Samples to Ship <span className="text-destructive">*</span>
              </Label>
              <Button type="button" variant="outline" size="sm" onClick={addItem}>
                <Plus className="mr-1 h-3 w-3" />
                Add Another Compound
              </Button>
            </div>

            <div className="space-y-3">
              {items.map((item, index) => (
                <ShipmentItemRow
                  key={index}
                  item={item}
                  index={index}
                  canRemove={items.length > 1}
                  onUpdate={(key, value) => updateItem(index, key, value)}
                  onRemove={() => removeItem(index)}
                />
              ))}
            </div>
          </div>

          {/* Notes */}
          <div className="grid gap-2">
            <Label>Notes</Label>
            <Textarea
              placeholder="Additional notes..."
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!isValid || mutation.isPending}>
            {mutation.isPending ? "Creating..." : "Create Shipment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
