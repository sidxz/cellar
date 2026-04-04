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
import { Switch } from "@/shared/components/ui/switch";
import { useProtocol } from "../hooks/use-protocols";
import { useCreateReadoutData } from "../hooks/use-readout-data";

const QUALIFIER_OPTIONS = ["=", "<", ">", "<=", ">=", "~"] as const;

interface AddReadoutDataDialogProps {
  runId: string;
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddReadoutDataDialog({
  runId,
  protocolId,
  open,
  onOpenChange,
}: AddReadoutDataDialogProps) {
  const createReadoutData = useCreateReadoutData();
  const { data: protocol } = useProtocol(protocolId);

  const [moleculeId, setMoleculeId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [readoutDefinitionId, setReadoutDefinitionId] = useState("");
  const [valueNumeric, setValueNumeric] = useState("");
  const [valueQualifier, setValueQualifier] = useState("");
  const [isOutlier, setIsOutlier] = useState(false);

  const resetForm = () => {
    setMoleculeId("");
    setBatchId("");
    setReadoutDefinitionId("");
    setValueNumeric("");
    setValueQualifier("");
    setIsOutlier(false);
  };

  const handleSubmit = () => {
    createReadoutData.mutate(
      {
        run_id: runId,
        molecule_id: moleculeId,
        batch_id: batchId,
        readout_definition_id: readoutDefinitionId,
        value_numeric: valueNumeric ? parseFloat(valueNumeric) : undefined,
        value_qualifier: valueQualifier || undefined,
        is_outlier: isOutlier,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          resetForm();
        },
      }
    );
  };

  const readoutDefinitions = protocol?.readout_definitions ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Readout Data</DialogTitle>
          <DialogDescription>
            Record a readout data point for this screening run.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Molecule ID</Label>
            <Input
              placeholder="UUID of the molecule"
              value={moleculeId}
              onChange={(e) => setMoleculeId(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Batch ID</Label>
            <Input
              placeholder="UUID of the batch"
              value={batchId}
              onChange={(e) => setBatchId(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Readout Definition</Label>
            <Select
              value={readoutDefinitionId}
              onValueChange={setReadoutDefinitionId}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a readout definition" />
              </SelectTrigger>
              <SelectContent>
                {readoutDefinitions.map((rd) => (
                  <SelectItem key={rd.id} value={rd.id}>
                    {rd.name}
                    {rd.unit ? ` (${rd.unit})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label>Numeric Value</Label>
            <Input
              type="number"
              placeholder="e.g., 42.5"
              value={valueNumeric}
              onChange={(e) => setValueNumeric(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Qualifier</Label>
            <Select value={valueQualifier} onValueChange={setValueQualifier}>
              <SelectTrigger>
                <SelectValue placeholder="Select qualifier (optional)" />
              </SelectTrigger>
              <SelectContent>
                {QUALIFIER_OPTIONS.map((q) => (
                  <SelectItem key={q} value={q}>
                    {q}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-3">
            <Switch checked={isOutlier} onCheckedChange={setIsOutlier} />
            <Label>Mark as outlier</Label>
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={
              !moleculeId.trim() ||
              !batchId.trim() ||
              !readoutDefinitionId ||
              createReadoutData.isPending
            }
          >
            {createReadoutData.isPending ? "Adding..." : "Add Readout Data"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
