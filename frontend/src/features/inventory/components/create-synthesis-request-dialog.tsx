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
import { useCreateSynthesisRequest } from "../hooks/use-synthesis-requests";

interface CreateSynthesisRequestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateSynthesisRequestDialog({
  open,
  onOpenChange,
}: CreateSynthesisRequestDialogProps) {
  const mutation = useCreateSynthesisRequest();

  const [moleculeId, setMoleculeId] = useState("");
  const [amountValue, setAmountValue] = useState("");
  const [amountUnit, setAmountUnit] = useState("mg");
  const [purpose, setPurpose] = useState("");
  const [priority, setPriority] = useState("routine");
  const [targetPurity, setTargetPurity] = useState("");
  const [projectId, setProjectId] = useState("");

  const resetState = () => {
    setMoleculeId("");
    setAmountValue("");
    setAmountUnit("mg");
    setPurpose("");
    setPriority("routine");
    setTargetPurity("");
    setProjectId("");
  };

  const handleSubmit = () => {
    mutation.mutate(
      {
        molecule_id: moleculeId,
        amount_value: parseFloat(amountValue),
        amount_unit: amountUnit,
        purpose,
        priority,
        target_purity: targetPurity !== "" ? parseFloat(targetPurity) : null,
        project_id: projectId.trim() !== "" ? projectId.trim() : null,
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
    moleculeId.trim() !== "" &&
    amountValue !== "" &&
    parseFloat(amountValue) > 0 &&
    purpose.trim() !== "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Synthesis Request</DialogTitle>
          <DialogDescription>
            Submit a request to synthesize a compound. The request is created in
            draft status — submit it to begin the approval workflow.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Molecule ID</Label>
            <Input
              placeholder="UUID of the target molecule"
              value={moleculeId}
              onChange={(e) => setMoleculeId(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Amount</Label>
              <Input
                type="number"
                placeholder="100"
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
              placeholder="Describe the intended use for this synthesis"
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

          <div className="grid gap-2">
            <Label>Target Purity % (optional)</Label>
            <Input
              type="number"
              placeholder="95"
              value={targetPurity}
              onChange={(e) => setTargetPurity(e.target.value)}
              min={0}
              max={100}
            />
          </div>

          <div className="grid gap-2">
            <Label>Project ID (optional)</Label>
            <Input
              placeholder="UUID of the associated project"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!isValid || mutation.isPending}
          >
            {mutation.isPending ? "Creating..." : "Create Request"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
