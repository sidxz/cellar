"use client";

import { useEffect, useState } from "react";
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
import { useRegisterPlate } from "../hooks/use-plates";
import type { PlateType } from "../types/plates";
import { plateTypeLabels } from "../types/plates";

const PLATE_FORMATS = ["6", "12", "24", "48", "96", "384", "1536"] as const;
type PlateFormat = (typeof PLATE_FORMATS)[number];

interface RegisterPlateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RegisterPlateDialog({
  open,
  onOpenChange,
}: RegisterPlateDialogProps) {
  const registerMutation = useRegisterPlate();

  const [barcode, setBarcode] = useState("");
  const [label, setLabel] = useState("");
  const [format, setFormat] = useState<PlateFormat>("96");
  const [plateType, setPlateType] = useState<PlateType>("compound_storage");
  const [notes, setNotes] = useState("");

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setBarcode("");
      setLabel("");
      setFormat("96");
      setPlateType("compound_storage");
      setNotes("");
    }
  }, [open]);

  const canSubmit =
    barcode.trim() && label.trim() && !registerMutation.isPending;

  const handleSubmit = () => {
    if (!canSubmit) return;
    registerMutation.mutate(
      {
        barcode: barcode.trim(),
        plate_label: label.trim(),
        format,
        plate_type: plateType,
        notes: notes.trim() || null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Register Plate</DialogTitle>
          <DialogDescription>
            Register a new plate to track compound locations and well mappings.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Barcode */}
          <div className="grid gap-2">
            <Label>
              Barcode <span className="text-destructive">*</span>
            </Label>
            <Input
              placeholder="e.g., PLT-2024-001"
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit) handleSubmit();
              }}
            />
          </div>

          {/* Label */}
          <div className="grid gap-2">
            <Label>
              Label <span className="text-destructive">*</span>
            </Label>
            <Input
              placeholder="e.g., Compound Library Plate 1"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit) handleSubmit();
              }}
            />
          </div>

          {/* Format + Type row */}
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Format</Label>
              <Select
                value={format}
                onValueChange={(v) => setFormat(v as PlateFormat)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PLATE_FORMATS.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}-well
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label>Type</Label>
              <Select
                value={plateType}
                onValueChange={(v) => setPlateType(v as PlateType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(plateTypeLabels) as PlateType[]).map((t) => (
                    <SelectItem key={t} value={t}>
                      {plateTypeLabels[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Notes */}
          <div className="grid gap-2">
            <Label>Notes (optional)</Label>
            <Textarea
              placeholder="Any additional information about this plate..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={registerMutation.isPending}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {registerMutation.isPending ? "Registering..." : "Register Plate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
