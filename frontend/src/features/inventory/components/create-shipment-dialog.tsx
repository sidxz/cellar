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
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useSamplesByBatch } from "../hooks/use-samples";
import { useCreateShipment } from "../hooks/use-shipments";
import type { ShipmentItemInput } from "../types/shipment";

interface CreateShipmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ItemRowState extends ShipmentItemInput {
  /** Batch ID used to load the sample list for this row — UI-only, not sent to API */
  _batch_id: string;
}

const EMPTY_ITEM: ItemRowState = {
  _batch_id: "",
  sample_id: "",
  amount_value: 0,
  amount_unit: "mg",
};

interface ShipmentItemRowProps {
  item: ItemRowState;
  index: number;
  canRemove: boolean;
  onUpdate: <K extends keyof ItemRowState>(key: K, value: ItemRowState[K]) => void;
  onRemove: () => void;
}

function ShipmentItemRow({ item, index, canRemove, onUpdate, onRemove }: ShipmentItemRowProps) {
  const { data: samples } = useSamplesByBatch(item._batch_id || undefined);

  return (
    <div className="rounded-md border p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Item {index + 1}</span>
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

      <div className="grid grid-cols-2 gap-2">
        <div className="grid gap-1">
          <Label className="text-xs">Batch ID</Label>
          <Input
            placeholder="Enter batch ID to load samples"
            value={item._batch_id}
            onChange={(e) => {
              onUpdate("_batch_id", e.target.value);
              onUpdate("sample_id", "");
            }}
          />
        </div>

        <div className="grid gap-1">
          <Label className="text-xs">
            Sample <span className="text-destructive">*</span>
          </Label>
          {samples && samples.length > 0 ? (
            <Select
              value={item.sample_id}
              onValueChange={(val) => onUpdate("sample_id", val)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select sample" />
              </SelectTrigger>
              <SelectContent>
                {samples.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.barcode} — {s.amount_value} {s.amount_unit}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Input
              placeholder={item._batch_id ? "No samples found for this batch" : "Sample barcode or ID"}
              value={item.sample_id}
              onChange={(e) => onUpdate("sample_id", e.target.value)}
              disabled={!!item._batch_id && (!samples || samples.length === 0)}
            />
          )}
        </div>
      </div>

      <div className="flex items-end gap-2">
        <div className="flex-1 grid gap-1">
          <Label className="text-xs">Amount <span className="text-destructive">*</span></Label>
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
        <div className="w-24 grid gap-1">
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
  const [items, setItems] = useState<ItemRowState[]>([
    { ...EMPTY_ITEM },
  ]);

  function resetForm() {
    setDestinationOrgId("");
    setCarrier("");
    setExpectedArrivalDate("");
    setShippingConditions("");
    setNotes("");
    setItems([{ ...EMPTY_ITEM }]);
  }

  function handleClose(open: boolean) {
    if (!open) resetForm();
    onOpenChange(open);
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
    items.every(
      (it) =>
        it.sample_id.trim().length > 0 &&
        it.amount_value > 0 &&
        it.amount_unit.length > 0
    );

  function handleSubmit() {
    // Strip the UI-only _batch_id field before sending to API
    const apiItems: ShipmentItemInput[] = items.map(({ _batch_id: _, ...rest }) => rest);
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
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>New Shipment</DialogTitle>
          <DialogDescription>
            Create an outbound shipment and specify the samples to include.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Destination */}
          <div className="grid gap-2">
            <Label htmlFor="dest-org">
              Destination Organization{" "}
              <span className="text-destructive">*</span>
            </Label>
            <Select value={destinationOrgId} onValueChange={setDestinationOrgId}>
              <SelectTrigger id="dest-org">
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
              <Label htmlFor="carrier">Carrier</Label>
              <Input
                id="carrier"
                placeholder="e.g. FedEx, DHL"
                value={carrier}
                onChange={(e) => setCarrier(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="arrival-date">Expected Arrival</Label>
              <Input
                id="arrival-date"
                type="date"
                value={expectedArrivalDate}
                onChange={(e) => setExpectedArrivalDate(e.target.value)}
              />
            </div>
          </div>

          {/* Shipping conditions */}
          <div className="grid gap-2">
            <Label htmlFor="shipping-cond">Shipping Conditions</Label>
            <Textarea
              id="shipping-cond"
              placeholder="e.g. Keep refrigerated at 2-8°C"
              rows={2}
              value={shippingConditions}
              onChange={(e) => setShippingConditions(e.target.value)}
            />
          </div>

          {/* Notes */}
          <div className="grid gap-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea
              id="notes"
              placeholder="Additional notes..."
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {/* Items */}
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label>
                Items <span className="text-destructive">*</span>
              </Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addItem}
              >
                <Plus className="mr-1 h-3 w-3" />
                Add Item
              </Button>
            </div>

            <div className="space-y-2">
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
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!isValid || mutation.isPending}
          >
            {mutation.isPending ? "Creating..." : "Create Shipment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
