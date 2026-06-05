"use client";

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
import { useState } from "react";
import { useCreateSample } from "../hooks/use-samples";
import { useStorageLocations } from "../hooks/use-storage-locations";
import { CONTAINER_TYPE_LABELS, type StorageLocation } from "../types";
import { BatchSelector } from "./batch-selector";
import { MoleculeSelector } from "./molecule-selector";

interface CreateSampleDialogProps {
  batchId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateSampleDialog({ batchId, open, onOpenChange }: CreateSampleDialogProps) {
  const createMutation = useCreateSample();
  const { data: locations } = useStorageLocations();
  const [selectedMoleculeId, setSelectedMoleculeId] = useState<string | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(batchId ?? null);
  const [barcode, setBarcode] = useState("");
  const [locationId, setLocationId] = useState("");
  const [containerType, setContainerType] = useState("vial");
  const [amountValue, setAmountValue] = useState("");
  const [amountUnit, setAmountUnit] = useState("mg");
  const [solvent, setSolvent] = useState("");
  const [lowStockThreshold, setLowStockThreshold] = useState("");

  const resolvedBatchId = selectedBatchId ?? batchId;

  const handleSubmit = () => {
    if (!resolvedBatchId) return;
    createMutation.mutate(
      {
        batch_id: resolvedBatchId,
        barcode,
        container_type: containerType,
        amount_value: Number.parseFloat(amountValue),
        amount_unit: amountUnit,
        solvent: solvent || null,
        location_id: locationId || null,
        low_stock_threshold: lowStockThreshold ? Number.parseFloat(lowStockThreshold) : null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setBarcode("");
          setContainerType("vial");
          setAmountValue("");
          setLocationId("");
          setSolvent("");
          setLowStockThreshold("");
          if (!batchId) {
            setSelectedMoleculeId(null);
            setSelectedBatchId(null);
          }
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Sample</DialogTitle>
          <DialogDescription>Create a new sample from this batch.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {!batchId && (
            <>
              <div className="grid gap-2">
                <Label>Compound *</Label>
                <MoleculeSelector
                  selectedId={selectedMoleculeId}
                  onSelect={(id) => {
                    setSelectedMoleculeId(id);
                    setSelectedBatchId(null);
                  }}
                />
              </div>
              {selectedMoleculeId && (
                <div className="grid gap-2">
                  <Label>Batch *</Label>
                  <BatchSelector
                    moleculeId={selectedMoleculeId}
                    selectedId={selectedBatchId}
                    onSelect={setSelectedBatchId}
                  />
                </div>
              )}
            </>
          )}

          <div className="grid gap-2">
            <Label>Barcode</Label>
            <Input
              placeholder="SMP-001"
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Container Type</Label>
            <Select value={containerType} onValueChange={setContainerType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(CONTAINER_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Amount</Label>
              <Input
                type="number"
                placeholder="5"
                value={amountValue}
                onChange={(e) => setAmountValue(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Unit</Label>
              <Select value={amountUnit} onValueChange={setAmountUnit}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mg">mg</SelectItem>
                  <SelectItem value="g">g</SelectItem>
                  <SelectItem value="mL">mL</SelectItem>
                  <SelectItem value="umol">umol</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Storage Location</Label>
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

          <div className="grid gap-2">
            <Label>Solvent</Label>
            <Input
              placeholder="e.g., DMSO, water"
              value={solvent}
              onChange={(e) => setSolvent(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Low Stock Threshold</Label>
            <Input
              type="number"
              placeholder="Alert when below this amount"
              value={lowStockThreshold}
              onChange={(e) => setLowStockThreshold(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!resolvedBatchId || !barcode || !amountValue || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating..." : "Create Sample"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
