"use client";

import { AttachmentList, FileUploadZone } from "@/features/attachment";
import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { DetailShell } from "@/shared/components/detail-shell";
import { OrgName } from "@/shared/components/entity-name";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { formatStatusLabel } from "@/shared/lib/status-variants";
import { PackageCheck, Pencil, Trash2, Truck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useLoan } from "../hooks/use-plate-loans";
import {
  useAddShipmentItem,
  useDeleteShipment,
  useDeliverShipment,
  useMarkInTransit,
  useResolveShipmentItems,
  useReturnShipment,
  useShipShipment,
  useShipment,
  useUpdateShipment,
} from "../hooks/use-shipments";
import { loanTitle } from "../lib/loan-summary";
import {
  type ResolvedItem,
  SHIPMENT_STATUS_LABELS,
  type Shipment,
  type ShipmentItem,
  type ShipmentStatus,
} from "../types/shipment";

interface ShipmentDetailProps {
  shipmentId: string;
}

const itemHref = (item: ShipmentItem) =>
  `/inventory/${item.item_type === "plate" ? "plates" : "samples"}/${item.item_id}`;

/** "carries loan → Maia Young · Set 5" — the loan whose plates ride in this box. */
function LoanLink({ loanId }: { loanId: string }) {
  const { data: loan } = useLoan(loanId);
  const memberName = useMemberNames();
  return (
    <span>
      · carries loan →{" "}
      <Link href={`/inventory/loans/${loanId}`} className="text-primary hover:underline">
        {loan ? loanTitle(loan, memberName(loan.requested_by)) : "…"}
      </Link>
    </span>
  );
}

export function ShipmentDetail({ shipmentId }: ShipmentDetailProps) {
  const router = useRouter();
  const query = useShipment(shipmentId);
  const [shipDialogOpen, setShipDialogOpen] = useState(false);
  const [addItemOpen, setAddItemOpen] = useState(false);
  const [deliverOpen, setDeliverOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const markInTransit = useMarkInTransit();
  const returnShipment = useReturnShipment();
  const deleteMutation = useDeleteShipment();

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory/shipments"
        backLabel="Back to Shipments"
        title={(s) => s.tracking_number || "Shipment"}
        badge={(s) => ({
          status: s.status,
          label: SHIPMENT_STATUS_LABELS[s.status as ShipmentStatus] ?? s.status,
        })}
        notFoundMessage="Shipment not found."
        actions={(s) => {
          const isTerminal = s.status === "delivered" || s.status === "returned";
          if (isTerminal) return undefined;
          return (
            <>
              {s.status === "preparing" && (
                <>
                  <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
                    <Pencil className="mr-1 h-3.5 w-3.5" />
                    Edit
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setAddItemOpen(true)}>
                    Add Item
                  </Button>
                  <Button size="sm" onClick={() => setShipDialogOpen(true)}>
                    <Truck className="mr-2 h-4 w-4" />
                    Ship
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setDeleteOpen(true)}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 className="mr-1 h-3.5 w-3.5" />
                    Delete
                  </Button>
                </>
              )}
              {s.status === "shipped" && (
                <Button
                  size="sm"
                  onClick={() => markInTransit.mutate({ id: shipmentId })}
                  disabled={markInTransit.isPending}
                >
                  {markInTransit.isPending ? "Updating..." : "Mark In Transit"}
                </Button>
              )}
              {s.status === "in_transit" && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => returnShipment.mutate({ id: shipmentId })}
                    disabled={returnShipment.isPending}
                  >
                    {returnShipment.isPending ? "Processing..." : "Return"}
                  </Button>
                  <Button size="sm" onClick={() => setDeliverOpen(true)}>
                    <PackageCheck className="mr-2 h-4 w-4" />
                    Deliver
                  </Button>
                </>
              )}
            </>
          );
        }}
      >
        {(shipment) => (
          <>
            <p className="-mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="outline">{formatStatusLabel(shipment.direction)}</Badge>
              <span>
                Shipment {shipment.direction === "inbound" ? "from" : "to"}{" "}
                <OrgName id={shipment.destination_org_id} />
              </span>
              {shipment.loan_id ? <LoanLink loanId={shipment.loan_id} /> : null}
            </p>

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
                  <p className="font-mono text-sm">{shipment.tracking_number ?? "\u2014"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Shipping Date</p>
                  <p className="font-medium">{shipment.shipping_date ?? "\u2014"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Expected Arrival</p>
                  <p className="font-medium">{shipment.expected_arrival_date ?? "\u2014"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Received Date</p>
                  <p className="font-medium">{shipment.received_date ?? "\u2014"}</p>
                </div>
                {shipment.shipping_conditions && (
                  <div className="col-span-2">
                    <p className="text-xs text-muted-foreground">Shipping Conditions</p>
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
                Plates and samples in this shipment.
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
                          <th className="px-4 py-2 text-left font-medium">Type</th>
                          <th className="px-4 py-2 text-left font-medium">Barcode</th>
                          <th className="px-4 py-2 text-left font-medium">Label</th>
                          <th className="px-4 py-2 text-right font-medium">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shipment.items.map((item) => (
                          <tr key={item.id} className="border-b last:border-0">
                            <td className="px-4 py-2">
                              <Badge variant="outline">{formatStatusLabel(item.item_type)}</Badge>
                            </td>
                            <td className="px-4 py-2">
                              <Link
                                href={itemHref(item)}
                                className="font-mono text-primary hover:underline"
                              >
                                {item.barcode ?? item.item_id}
                              </Link>
                            </td>
                            <td className="px-4 py-2 text-muted-foreground">
                              {item.label ?? "\u2014"}
                            </td>
                            <td className="px-4 py-2 text-right">
                              {item.amount_value != null
                                ? `${item.amount_value} ${item.amount_unit ?? ""}`
                                : "\u2014"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            {/* Attachments */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold mb-4">Files</h2>
              <FileUploadZone entityType="shipment" entityId={shipmentId} />
              <AttachmentList entityType="shipment" entityId={shipmentId} />
            </Card>
          </>
        )}
      </DetailShell>

      {/* Dialogs */}
      {query.data?.status === "preparing" && (
        <EditShipmentDialog shipment={query.data} open={editOpen} onOpenChange={setEditOpen} />
      )}
      {query.data && (
        <ShipDialog shipment={query.data} open={shipDialogOpen} onOpenChange={setShipDialogOpen} />
      )}
      <AddItemDialog shipmentId={shipmentId} open={addItemOpen} onOpenChange={setAddItemOpen} />
      <DeliverDialog shipmentId={shipmentId} open={deliverOpen} onOpenChange={setDeliverOpen} />

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Shipment"
        description="This will permanently delete this shipment. This action cannot be undone."
        onConfirm={() =>
          deleteMutation.mutate(shipmentId, {
            onSuccess: () => router.push("/inventory/shipments"),
          })
        }
        isPending={deleteMutation.isPending}
      />
    </>
  );
}

// --- EditShipmentDialog ---

function EditShipmentDialog({
  shipment,
  open,
  onOpenChange,
}: {
  shipment: Shipment;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useUpdateShipment();
  const [carrier, setCarrier] = useState(shipment.carrier ?? "");
  const [expectedArrival, setExpectedArrival] = useState(shipment.expected_arrival_date ?? "");
  const [shippingConditions, setShippingConditions] = useState(shipment.shipping_conditions ?? "");
  const [notes, setNotes] = useState(shipment.notes ?? "");

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setCarrier(shipment.carrier ?? "");
          setExpectedArrival(shipment.expected_arrival_date ?? "");
          setShippingConditions(shipment.shipping_conditions ?? "");
          setNotes(shipment.notes ?? "");
        }
        onOpenChange(v);
      }}
    >
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Edit Shipment</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="edit-ship-carrier">Carrier</Label>
            <Input
              id="edit-ship-carrier"
              placeholder="e.g. FedEx, DHL, UPS"
              value={carrier}
              onChange={(e) => setCarrier(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-ship-arrival">Expected Arrival Date</Label>
            <Input
              id="edit-ship-arrival"
              type="date"
              value={expectedArrival}
              onChange={(e) => setExpectedArrival(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-ship-conditions">Shipping Conditions</Label>
            <Input
              id="edit-ship-conditions"
              placeholder="e.g. Ambient, Cold chain (2-8C)"
              value={shippingConditions}
              onChange={(e) => setShippingConditions(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="edit-ship-notes">Notes</Label>
            <Textarea
              id="edit-ship-notes"
              rows={3}
              placeholder="Additional notes..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
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
                  carrier: carrier.trim() || null,
                  expected_arrival_date: expectedArrival || null,
                  shipping_conditions: shippingConditions.trim() || null,
                  notes: notes.trim() || null,
                },
                { onSuccess: () => onOpenChange(false) },
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
      <DialogContent className="">
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
                { onSuccess: () => onOpenChange(false) },
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
  const resolve = useResolveShipmentItems();
  const [barcode, setBarcode] = useState("");
  const [hit, setHit] = useState<ResolvedItem | null>(null);
  const [amountValue, setAmountValue] = useState("");
  const [amountUnit, setAmountUnit] = useState("mg");

  const isSample = hit?.item_type === "sample";
  const amount = Number.parseFloat(amountValue) || 0;
  const canAdd = !!hit?.item_type && !!hit.item_id && (!isSample || amount > 0);

  const reset = () => {
    setBarcode("");
    setHit(null);
    setAmountValue("");
    setAmountUnit("mg");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Add Item</DialogTitle>
          <DialogDescription>Add a plate or a sample by barcode.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="item-barcode">
              Barcode <span className="text-destructive">*</span>
            </Label>
            <div className="flex gap-2">
              <Input
                id="item-barcode"
                placeholder="e.g. SMP-0042 or 005261"
                value={barcode}
                onChange={(e) => {
                  setBarcode(e.target.value);
                  setHit(null);
                }}
              />
              <Button
                type="button"
                variant="secondary"
                disabled={!barcode.trim() || resolve.isPending}
                onClick={() =>
                  resolve.mutate([barcode.trim()], { onSuccess: (rows) => setHit(rows[0] ?? null) })
                }
              >
                {resolve.isPending ? "Resolving..." : "Resolve"}
              </Button>
            </div>
            {hit?.error ? (
              <p className="text-sm text-destructive">{hit.error}</p>
            ) : hit?.item_type ? (
              <p className="flex items-center gap-2 text-sm">
                <Badge variant="outline">{formatStatusLabel(hit.item_type)}</Badge>
                <span className="text-muted-foreground">{hit.label}</span>
              </p>
            ) : null}
          </div>
          {isSample ? (
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
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              if (!hit?.item_type || !hit.item_id) return;
              mutation.mutate(
                {
                  id: shipmentId,
                  item_type: hit.item_type,
                  item_id: hit.item_id,
                  ...(isSample ? { amount_value: amount, amount_unit: amountUnit } : {}),
                },
                {
                  onSuccess: () => {
                    reset();
                    onOpenChange(false);
                  },
                },
              );
            }}
            disabled={!canAdd || mutation.isPending}
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
      <DialogContent className="">
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
                { onSuccess: () => onOpenChange(false) },
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
