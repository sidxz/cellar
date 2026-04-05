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
import { Textarea } from "@/shared/components/ui/textarea";
import { useCreateSampleRequest } from "../hooks/use-sample-requests";
import { MoleculeSelector } from "@/features/inventory/components/molecule-selector";
import { BatchSelector } from "@/features/inventory/components/batch-selector";

interface CreateSampleRequestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateSampleRequestDialog({
  open,
  onOpenChange,
}: CreateSampleRequestDialogProps) {
  const mutation = useCreateSampleRequest();

  const [moleculeId, setMoleculeId] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [amountValue, setAmountValue] = useState("");
  const [amountUnit, setAmountUnit] = useState("mg");
  const [purpose, setPurpose] = useState("");
  const [priority, setPriority] = useState("routine");

  const resetState = () => {
    setMoleculeId(null);
    setBatchId(null);
    setAmountValue("");
    setAmountUnit("mg");
    setPurpose("");
    setPriority("routine");
  };

  const handleSubmit = () => {
    mutation.mutate(
      {
        molecule_id: moleculeId!,
        batch_id: batchId,
        amount_value: parseFloat(amountValue),
        amount_unit: amountUnit,
        purpose,
        priority,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          resetState();
        },
      }
    );
  };

  const isValid =
    moleculeId !== null &&
    amountValue !== "" &&
    parseFloat(amountValue) > 0 &&
    purpose.trim() !== "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Sample Request</DialogTitle>
          <DialogDescription>
            Submit a request for a physical sample of a registered compound.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Molecule</Label>
            <MoleculeSelector
              selectedId={moleculeId}
              onSelect={(id) => {
                setMoleculeId(id);
                setBatchId(null);
              }}
            />
          </div>

          {moleculeId && (
            <div className="grid gap-2">
              <Label>Batch (optional)</Label>
              <BatchSelector
                moleculeId={moleculeId}
                selectedId={batchId}
                onSelect={setBatchId}
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Amount</Label>
              <Input
                type="number"
                placeholder="10"
                value={amountValue}
                onChange={(e) => setAmountValue(e.target.value)}
                min={0}
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
            <Label>Purpose</Label>
            <Textarea
              placeholder="Describe the intended use for this sample"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              rows={3}
            />
          </div>

          <div className="grid gap-2">
            <Label>Priority</Label>
            <Select value={priority} onValueChange={setPriority}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="routine">Routine</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!isValid || mutation.isPending}
          >
            {mutation.isPending ? "Submitting..." : "Submit Request"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
