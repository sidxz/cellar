"use client";

import { useState } from "react";
import { ArrowLeft, PackageCheck, Truck } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { OrgName } from "@/shared/components/entity-name";
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
import { Textarea } from "@/shared/components/ui/textarea";
import {
  useAddShipmentItem,
  useDeliverShipment,
  useMarkInTransit,
  useReturnShipment,
  useShipment,
  useShipShipment,
} from "../hooks/use-shipments";
import {
  SHIPMENT_STATUS_LABELS,
  type Shipment,
  type ShipmentStatus,
} from "../types/shipment";

interface ShipmentDetailProps {
  shipmentId: string;
}

function statusBadgeVariant(
  status: ShipmentStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "delivered":
      return "default";
    case "shipped":
    case "in_transit":
      return "secondary";
    case "returned":
      return "destructive";
    case "preparing":
    default:
      return "outline";
  }
}

export function ShipmentDetail({ shipmentId }: ShipmentDetailProps) {
  const { data: shipment, isLoading } = useShipment(shipmentId);
  const [shipDialogOpen, setShipDialogOpen] = useState(false);
  const [addItemOpen, setAddItemOpen] = useState(false);
  const [deliverOpen, setDeliverOpen] = useState(false);

  const markInTransit = useMarkInTransit();
  const returnShipment = useReturnShipment();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!shipment) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Truck className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Shipment not found</h3>
      </div>
    );
  }

  const isTerminal =
    shipment.status === "delivered" || shipment.status === "returned";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/inventory/shipments">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              Shipment to <OrgName id={shipment.destination_org_id} />
            </h1>
            <Badge variant={statusBadgeVariant(shipment.status)}>
              {SHIPMENT_STATUS_LABELS[shipment.status]}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {SHIPMENT_STATUS_LABELS[shipment.status]} &middot;{" "}
            {shipment.tracking_number ?? "No tracking number"}
          </p>
        </div>

        {/* Action buttons */}
        {!isTerminal && (
          <div className="flex gap-2">
            {shipment.status === "preparing" && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setAddItemOpen(true)}
                >
                  Add Item
                </Button>
                <Button size="sm" onClick={() => setShipDialogOpen(true)}>
                  <Truck className="mr-2 h-4 w-4" />
                  Ship
                </Button>
              </>
            )}
            {shipment.status === "shipped" && (
              <Button
                size="sm"
                onClick={() =>
                  markInTransit.mutate({ id: shipmentId })
                }
                disabled={markInTransit.isPending}
              >
                {markInTransit.isPending ? "Updating..." : "Mark In Transit"}
              </Button>
            )}
            {shipment.status === "in_transit" && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    returnShipment.mutate({ id: shipmentId })
                  }
                  disabled={returnShipment.isPending}
                >
                  {returnShipment.isPending ? "Processing..." : "Return"}
                </Button>
                <Button
                  size="sm"
                  onClick={() => setDeliverOpen(true)}
                >
                  <PackageCheck className="mr-2 h-4 w-4" />
                  Deliver
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Properties */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Shipment Details</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Carrier</p>
            <p className="font-medium">{shipment.carrier ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Tracking Number</p>
            <p className="font-mono text-sm">
              {shipment.tracking_number ?? "\u2014"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Shipping Date</p>
            <p className="font-medium">{shipment.shipping_date ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Expected Arrival</p>
            <p className="font-medium">
              {shipment.expected_arrival_date ?? "\u2014"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Received Date</p>
            <p className="font-medium">
              {shipment.received_date ?? "\u2014"}
            </p>
          </div>
          {shipment.shipping_conditions && (
            <div className="col-span-2">
              <p className="text-xs text-muted-foreground">
                Shipping Conditions
              </p>
              <p className="font-medium">{shipment.shipping_conditions}</p>
            </div>
          )}
          {shipment.notes && (
            <div className="col-span-2 sm:col-span-3">
              <p className="text-xs text-muted-foreground">Notes</p>
              <p className="text-sm">{shipment.notes}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Items */}
      <div>
        <h2 className="text-lg font-semibold">Items</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Samples included in this shipment.
        </p>
        <div className="mt-4">
          {shipment.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
              <p className="text-sm text-muted-foreground">No items added yet.</p>
            </div>
          ) : (
            <div className="rounded-md border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-2 text-left font-medium">
                      Sample ID
                    </th>
                    <th className="px-4 py-2 text-right font-medium">
                      Amount
                    </th>
                    <th className="px-4 py-2 text-left font-medium">Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {shipment.items.map((item) => (
                    <tr key={item.id} className="border-b last:border-0">
                      <td className="px-4 py-2 font-mono text-xs">
                        {item.sample_id}
                      </td>
                      <td className="px-4 py-2 text-right">
                        {item.amount_value}
                      </td>
                      <td className="px-4 py-2">{item.amount_unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Dialogs */}
      <ShipDialog
        shipment={shipment}
        open={shipDialogOpen}
        onOpenChange={setShipDialogOpen}
      />
      <AddItemDialog
        shipmentId={shipmentId}
        open={addItemOpen}
        onOpenChange={setAddItemOpen}
      />
      <DeliverDialog
        shipmentId={shipmentId}
        open={deliverOpen}
        onOpenChange={setDeliverOpen}
      />
    </div>
  );
}

// --- ShipDialog ---

function ShipDialog({
  shipment,
  open,
  onOpenChange,
}: {
  shipment: Shipment;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useShipShipment();
  const [trackingNumber, setTrackingNumber] = useState("");
  const [shippingDate, setShippingDate] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Ship Shipment</DialogTitle>
          <DialogDescription>
            Mark this shipment as shipped. A tracking number is required.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="tracking">
              Tracking Number <span className="text-destructive">*</span>
            </Label>
            <Input
              id="tracking"
              placeholder="e.g. 1Z999AA10123456784"
              value={trackingNumber}
              onChange={(e) => setTrackingNumber(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="ship-date">Shipping Date</Label>
            <Input
              id="ship-date"
              type="date"
              value={shippingDate}
              onChange={(e) => setShippingDate(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: shipment.id,
                  tracking_number: trackingNumber.trim(),
                  shipping_date: shippingDate || null,
                },
                { onSuccess: () => onOpenChange(false) }
              );
            }}
            disabled={!trackingNumber.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Processing..." : "Confirm Ship"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- AddItemDialog ---

function AddItemDialog({
  shipmentId,
  open,
  onOpenChange,
}: {
  shipmentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useAddShipmentItem();
  const [sampleId, setSampleId] = useState("");
  const [amountValue, setAmountValue] = useState("");
  const [amountUnit, setAmountUnit] = useState("mg");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Add Item</DialogTitle>
          <DialogDescription>
            Add a sample to this shipment.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="item-sample">
              Sample Barcode <span className="text-destructive">*</span>
            </Label>
            <Input
              id="item-sample"
              placeholder="e.g. SMP-0042"
              value={sampleId}
              onChange={(e) => setSampleId(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="item-amount">Amount</Label>
              <Input
                id="item-amount"
                type="number"
                placeholder="0.0"
                min={0}
                value={amountValue}
                onChange={(e) => setAmountValue(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Unit</Label>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={amountUnit}
                onChange={(e) => setAmountUnit(e.target.value)}
              >
                <option value="mg">mg</option>
                <option value="g">g</option>
                <option value="mL">mL</option>
              </select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: shipmentId,
                  sample_id: sampleId.trim(),
                  amount_value: parseFloat(amountValue) || 0,
                  amount_unit: amountUnit,
                },
                {
                  onSuccess: () => {
                    setSampleId("");
                    setAmountValue("");
                    setAmountUnit("mg");
                    onOpenChange(false);
                  },
                }
              );
            }}
            disabled={
              !sampleId.trim() ||
              !amountValue ||
              parseFloat(amountValue) <= 0 ||
              mutation.isPending
            }
          >
            {mutation.isPending ? "Adding..." : "Add Item"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- DeliverDialog ---

function DeliverDialog({
  shipmentId,
  open,
  onOpenChange,
}: {
  shipmentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useDeliverShipment();
  const [receivedDate, setReceivedDate] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Mark as Delivered</DialogTitle>
          <DialogDescription>
            Confirm that the shipment has been received by the destination.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-4">
          <Label htmlFor="received-date">Received Date</Label>
          <Input
            id="received-date"
            type="date"
            value={receivedDate}
            onChange={(e) => setReceivedDate(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  id: shipmentId,
                  received_date: receivedDate || null,
                },
                { onSuccess: () => onOpenChange(false) }
              );
            }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Processing..." : "Confirm Delivery"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
