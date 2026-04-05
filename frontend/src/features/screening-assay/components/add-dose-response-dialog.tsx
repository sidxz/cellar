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
import { MoleculeSelector } from "@/features/inventory/components/molecule-selector";
import { BatchSelector } from "@/features/inventory/components/batch-selector";
import { useCreateDoseResponseCurve } from "../hooks/use-dose-response";
import {
  CURVE_CLASS_LABELS,
  CURVE_TYPE_LABELS,
  type CurveClass,
  type CurveType,
} from "../types";

interface AddDoseResponseDialogProps {
  runId: string;
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddDoseResponseDialog({
  runId,
  protocolId,
  open,
  onOpenChange,
}: AddDoseResponseDialogProps) {
  const createDoseResponse = useCreateDoseResponseCurve();

  const [moleculeId, setMoleculeId] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [curveType, setCurveType] = useState<string>("ic50");
  const [fittedValue, setFittedValue] = useState("");
  const [fittedUnit, setFittedUnit] = useState("");
  const [hillSlope, setHillSlope] = useState("");
  const [top, setTop] = useState("");
  const [bottom, setBottom] = useState("");
  const [rSquared, setRSquared] = useState("");
  const [numPoints, setNumPoints] = useState("");
  const [curveClass, setCurveClass] = useState<string>("");

  const resetForm = () => {
    setMoleculeId(null);
    setBatchId(null);
    setCurveType("ic50");
    setFittedValue("");
    setFittedUnit("");
    setHillSlope("");
    setTop("");
    setBottom("");
    setRSquared("");
    setNumPoints("");
    setCurveClass("");
  };

  const handleSubmit = () => {
    createDoseResponse.mutate(
      {
        protocol_id: protocolId,
        run_id: runId,
        molecule_id: moleculeId!,
        batch_id: batchId!,
        curve_type: curveType as CurveType,
        fitted_value: parseFloat(fittedValue),
        fitted_unit: fittedUnit,
        hill_slope: parseFloat(hillSlope),
        top: parseFloat(top),
        bottom: parseFloat(bottom),
        r_squared: parseFloat(rSquared),
        num_points: parseInt(numPoints, 10),
        curve_class: curveClass ? (curveClass as CurveClass) : undefined,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          resetForm();
        },
      }
    );
  };

  const isValid =
    moleculeId &&
    batchId &&
    fittedValue &&
    fittedUnit.trim() &&
    hillSlope &&
    top &&
    bottom &&
    rSquared &&
    numPoints;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Dose-Response Curve</DialogTitle>
          <DialogDescription>
            Record a dose-response curve fit result for this screening run.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Compound</Label>
            <MoleculeSelector
              selectedId={moleculeId}
              onSelect={(id) => {
                setMoleculeId(id);
                setBatchId(null);
              }}
            />
          </div>

          <div className="grid gap-2">
            <Label>Batch</Label>
            {moleculeId ? (
              <BatchSelector
                moleculeId={moleculeId}
                selectedId={batchId}
                onSelect={setBatchId}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Select a compound first</p>
            )}
          </div>

          <div className="grid gap-2">
            <Label>Curve Type</Label>
            <Select value={curveType} onValueChange={setCurveType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(CURVE_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Fitted Value</Label>
              <Input
                type="number"
                placeholder="e.g., 5.2"
                value={fittedValue}
                onChange={(e) => setFittedValue(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Fitted Unit</Label>
              <Input
                placeholder="e.g., nM"
                value={fittedUnit}
                onChange={(e) => setFittedUnit(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Hill Slope</Label>
              <Input
                type="number"
                placeholder="e.g., 1.0"
                value={hillSlope}
                onChange={(e) => setHillSlope(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>R-Squared</Label>
              <Input
                type="number"
                step="0.01"
                placeholder="e.g., 0.98"
                value={rSquared}
                onChange={(e) => setRSquared(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Top</Label>
              <Input
                type="number"
                placeholder="e.g., 100"
                value={top}
                onChange={(e) => setTop(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Bottom</Label>
              <Input
                type="number"
                placeholder="e.g., 0"
                value={bottom}
                onChange={(e) => setBottom(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Number of Points</Label>
              <Input
                type="number"
                placeholder="e.g., 8"
                value={numPoints}
                onChange={(e) => setNumPoints(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Curve Class</Label>
              <Select value={curveClass} onValueChange={setCurveClass}>
                <SelectTrigger>
                  <SelectValue placeholder="Optional" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CURVE_CLASS_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!isValid || createDoseResponse.isPending}
          >
            {createDoseResponse.isPending
              ? "Adding..."
              : "Add Dose-Response Curve"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
