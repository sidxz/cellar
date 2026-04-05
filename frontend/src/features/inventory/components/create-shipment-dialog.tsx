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
import { useCreateShipment } from "../hooks/use-shipments";
import type { ShipmentItemInput } from "../types/shipment";

interface CreateShipmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const EMPTY_ITEM: ShipmentItemInput = {
  sample_id: "",
  amount_value: 0,
  amount_unit: "mg",
};

export function CreateShipmentDialog({
  open,
  onOpenChange,
}: CreateShipmentDialogProps) {
  const mutation = useCreateShipment();

  const [destinationOrgId, setDestinationOrgId] = useState("");
  const [carrier, setCarrier] = useState("");
  const [expectedArrivalDate, setExpectedArrivalDate] = useState("");
  const [shippingConditions, setShippingConditions] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<ShipmentItemInput[]>([
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

  function updateItem<K extends keyof ShipmentItemInput>(
    index: number,
    key: K,
    value: ShipmentItemInput[K]
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
    mutation.mutate(
      {
        destination_org_id: destinationOrgId.trim(),
        carrier: carrier.trim() || null,
        expected_arrival_date: expectedArrivalDate || null,
        shipping_conditions: shippingConditions.trim() || null,
        notes: notes.trim() || null,
        items,
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
              Destination Organization ID{" "}
              <span className="text-destructive">*</span>
            </Label>
            <Input
              id="dest-org"
              placeholder="UUID of destination organization"
              value={destinationOrgId}
              onChange={(e) => setDestinationOrgId(e.target.value)}
            />
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
                <div
                  key={index}
                  className="flex items-end gap-2 rounded-md border p-3"
                >
                  <div className="flex-1 grid gap-1">
                    <Label className="text-xs">Sample ID</Label>
                    <Input
                      placeholder="Sample UUID"
                      value={item.sample_id}
                      onChange={(e) =>
                        updateItem(index, "sample_id", e.target.value)
                      }
                    />
                  </div>
                  <div className="w-28 grid gap-1">
                    <Label className="text-xs">Amount</Label>
                    <Input
                      type="number"
                      placeholder="0.0"
                      min={0}
                      value={item.amount_value || ""}
                      onChange={(e) =>
                        updateItem(
                          index,
                          "amount_value",
                          parseFloat(e.target.value) || 0
                        )
                      }
                    />
                  </div>
                  <div className="w-24 grid gap-1">
                    <Label className="text-xs">Unit</Label>
                    <Select
                      value={item.amount_unit}
                      onValueChange={(val) =>
                        updateItem(index, "amount_unit", val)
                      }
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
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-9 w-9 text-destructive"
                    disabled={items.length === 1}
                    onClick={() => removeItem(index)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
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
