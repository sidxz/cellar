"use client";

import { MoleculeSelector } from "@/features/inventory/components/molecule-selector";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { useState } from "react";
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

  const [target, setTarget] = useState<Molecule | null>(null);
  const targetId = target?.id ?? null;
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTarget(null);
    setNotes("");
    setError(null);
  };

  const handleMerge = async () => {
    setError(null);
    if (!targetId) {
      setError("Please select a target compound");
      return;
    }
    if (targetId === sourceMolecule.id) {
      setError("Cannot merge a compound into itself");
      return;
    }

    try {
      await mergeMutation.mutateAsync({
        target_molecule_id: targetId,
        reason: "manual_merge",
        notes: notes.trim() || null,
      });
      reset();
      onOpenChange(false);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Merge failed";
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
            <span className="font-mono font-semibold">{sourceMolecule.registration_number}</span> (
            {sourceMolecule.name}) into the selected target compound.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
            {sourceMolecule.registration_number ?? sourceMolecule.id} will be marked as merged into{" "}
            {target?.registration_number ?? targetId ?? "the selected target compound"}. Its
            batches, assay results, and identifiers will transfer to that compound. This cannot be
            undone.
          </div>

          <div className="grid gap-2">
            <Label>Target Compound</Label>
            <MoleculeSelector
              selectedId={targetId}
              onSelect={(_, selected) => setTarget(selected ?? null)}
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
            disabled={!targetId || mergeMutation.isPending}
          >
            {mergeMutation.isPending ? "Merging..." : "Merge"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
