"use client";

import { useState } from "react";
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
import { useCreateBatch } from "../hooks/use-batches";
import { BATCH_SOURCE_LABELS, type BatchSource } from "../types";

interface CreateBatchDialogProps {
  moleculeId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateBatchDialog({
  moleculeId,
  open,
  onOpenChange,
}: CreateBatchDialogProps) {
  const createMutation = useCreateBatch();
  const [source, setSource] = useState<string>("synthesized");
  const [amountValue, setAmountValue] = useState("");
  const [amountUnit, setAmountUnit] = useState("mg");
  const [saltForm, setSaltForm] = useState("");
  const [purity, setPurity] = useState("");
  const [appearance, setAppearance] = useState("");

  const handleSubmit = () => {
    createMutation.mutate(
      {
        molecule_id: moleculeId,
        source,
        amount_value: parseFloat(amountValue),
        amount_unit: amountUnit,
        salt_form: saltForm || null,
        purity: purity ? parseFloat(purity) : null,
        appearance: appearance || null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setSource("synthesized");
          setAmountValue("");
          setPurity("");
          setSaltForm("");
          setAppearance("");
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Batch</DialogTitle>
          <DialogDescription>
            Register a new batch for this compound.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Source</Label>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(BATCH_SOURCE_LABELS).map(([value, label]) => (
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
                placeholder="100"
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
                  <SelectItem value="kg">kg</SelectItem>
                  <SelectItem value="mL">mL</SelectItem>
                  <SelectItem value="L">L</SelectItem>
                  <SelectItem value="umol">umol</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Purity (%)</Label>
            <Input
              type="number"
              placeholder="99.5"
              value={purity}
              onChange={(e) => setPurity(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Salt Form</Label>
            <Input
              placeholder="e.g., hydrochloride, free base"
              value={saltForm}
              onChange={(e) => setSaltForm(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Appearance</Label>
            <Input
              placeholder="e.g., white powder"
              value={appearance}
              onChange={(e) => setAppearance(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!amountValue || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating..." : "Create Batch"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
