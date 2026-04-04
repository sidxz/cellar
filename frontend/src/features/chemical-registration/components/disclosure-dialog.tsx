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
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { useSubmitDisclosure } from "../hooks/use-disclosures";
import type { Molecule } from "../types";

interface DisclosureDialogProps {
  molecule: Molecule;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DisclosureDialog({
  molecule,
  open,
  onOpenChange,
}: DisclosureDialogProps) {
  const submitMutation = useSubmitDisclosure();

  const [smiles, setSmiles] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setSmiles("");
    setNotes("");
    setError(null);
  };

  const handleSubmit = async () => {
    setError(null);
    if (!smiles.trim()) {
      setError("SMILES is required to disclose a compound");
      return;
    }

    try {
      const result = await submitMutation.mutateAsync({
        molecule_id: molecule.id,
        disclosed_smiles: smiles.trim(),
        notes: notes.trim() || null,
      });
      reset();
      onOpenChange(false);
      if (result.was_merged) {
        alert(
          `Structure matched an existing compound. Molecule was merged into ${result.merged_into_molecule_id}.`
        );
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Disclosure failed";
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
          <DialogTitle>Disclose Compound</DialogTitle>
          <DialogDescription>
            Provide the structure for{" "}
            <span className="font-mono font-semibold">
              {molecule.registration_number}
            </span>{" "}
            ({molecule.name}). The structure will be standardized and
            checked for duplicates.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="disclosure-smiles">SMILES</Label>
            <Textarea
              id="disclosure-smiles"
              placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
              value={smiles}
              onChange={(e) => setSmiles(e.target.value)}
              rows={3}
              className="font-mono text-sm"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="disclosure-notes">Notes (optional)</Label>
            <Textarea
              id="disclosure-notes"
              placeholder="Reason for disclosure, source, etc."
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
            onClick={handleSubmit}
            disabled={submitMutation.isPending}
          >
            {submitMutation.isPending ? "Disclosing..." : "Disclose"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
