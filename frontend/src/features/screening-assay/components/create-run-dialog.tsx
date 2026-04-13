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
import { useCreateRun } from "../hooks/use-runs";
import { usePlateTemplates } from "../hooks/use-plate-templates";
import { PLATE_FORMAT_LABELS, type PlateFormat } from "../types";

interface CreateRunDialogProps {
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function CreateRunDialog({
  protocolId,
  open,
  onOpenChange,
}: CreateRunDialogProps) {
  const createMutation = useCreateRun();
  const { data: plateTemplates } = usePlateTemplates();
  const [runDate, setRunDate] = useState(todayISO);
  const [plateFormat, setPlateFormat] = useState<string>("96");
  const [plateTemplateId, setPlateTemplateId] = useState<string>("");
  const [notes, setNotes] = useState("");

  const resetForm = () => {
    setRunDate(todayISO());
    setPlateFormat("96");
    setPlateTemplateId("");
    setNotes("");
  };

  const handleSubmit = () => {
    createMutation.mutate(
      {
        protocol_id: protocolId,
        run_date: runDate,
        plate_format: plateFormat as PlateFormat,
        plate_template_id: plateTemplateId || null,
        notes: notes || null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          resetForm();
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Run</DialogTitle>
          <DialogDescription>
            Create a screening run for this protocol.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Run Date</Label>
            <Input
              type="date"
              value={runDate}
              onChange={(e) => setRunDate(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Plate Format</Label>
            <Select value={plateFormat} onValueChange={setPlateFormat}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(PLATE_FORMAT_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {plateTemplates && plateTemplates.length > 0 && (
            <div className="grid gap-2">
              <Label>Plate Template (optional)</Label>
              <Select
                value={plateTemplateId}
                onValueChange={setPlateTemplateId}
              >
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">None</SelectItem>
                  {plateTemplates.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid gap-2">
            <Label>Notes (optional)</Label>
            <Textarea
              placeholder="Run notes..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!runDate || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating..." : "Create Run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
