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
import { Textarea } from "@/shared/components/ui/textarea";
import { useMergeMolecules } from "../hooks/use-disclosures";
import type { Molecule } from "../types";

interface MergeConfirmationDialogProps {
  sourceMolecule: Molecule;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MergeConfirmationDialog({
  sourceMolecule,
  open,
  onOpenChange,
}: MergeConfirmationDialogProps) {
  const mergeMutation = useMergeMolecules(sourceMolecule.id);

  const [targetId, setTargetId] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTargetId("");
    setNotes("");
    setError(null);
  };

  const handleMerge = async () => {
    setError(null);
    if (!targetId.trim()) {
      setError("Target molecule ID is required");
      return;
    }
    if (targetId.trim() === sourceMolecule.id) {
      setError("Cannot merge a molecule into itself");
      return;
    }

    try {
      await mergeMutation.mutateAsync({
        target_molecule_id: targetId.trim(),
        reason: "manual_merge",
        notes: notes.trim() || null,
      });
      reset();
      onOpenChange(false);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Merge failed";
      setError(message);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Merge Compound</DialogTitle>
          <DialogDescription>
            Merge{" "}
            <span className="font-mono font-semibold">
              {sourceMolecule.registration_number}
            </span>{" "}
            ({sourceMolecule.name}) into another compound. All related data
            will be transferred to the target compound.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
            This action is irreversible. The source compound will become a
            tombstone and all its data (batches, assay results, identifiers)
            will be moved to the target compound.
          </div>

          <div className="grid gap-2">
            <Label htmlFor="merge-target">Target Molecule ID</Label>
            <Input
              id="merge-target"
              placeholder="UUID of the target molecule"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="font-mono text-sm"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="merge-notes">Notes (optional)</Label>
            <Textarea
              id="merge-notes"
              placeholder="Reason for merge, context, etc."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleMerge}
            disabled={mergeMutation.isPending}
          >
            {mergeMutation.isPending ? "Merging..." : "Merge"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
