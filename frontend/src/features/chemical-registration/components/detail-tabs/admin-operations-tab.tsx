"use client";

import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { MoleculeSelector } from "@/features/inventory/components/molecule-selector";
import { useMergeMolecules } from "../../hooks/use-disclosures";

interface AdminOperationsTabProps {
  moleculeId: string;
}

export function AdminOperationsTab({ moleculeId }: AdminOperationsTabProps) {
  const mergeMutation = useMergeMolecules(moleculeId);

  const [targetId, setTargetId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleMerge = async () => {
    setError(null);
    if (!targetId) {
      setError("Please select a target compound");
      return;
    }
    if (targetId === moleculeId) {
      setError("Cannot merge a compound into itself");
      return;
    }

    try {
      await mergeMutation.mutateAsync({
        target_molecule_id: targetId,
        reason: "manual_merge",
        notes: notes.trim() || null,
      });
      setTargetId(null);
      setNotes("");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Merge failed";
      setError(message);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Manual Merge</CardTitle>
          <CardDescription>
            Merge this compound into another. All related data (batches, assay
            results, identifiers) will be transferred to the target.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
            <AlertTriangle className="mr-2 inline h-4 w-4" />
            This action is irreversible. The source compound will become a
            tombstone.
          </div>

          <div className="grid gap-2">
            <Label>Target Compound</Label>
            <MoleculeSelector
              selectedId={targetId}
              onSelect={setTargetId}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="admin-merge-notes">Notes (optional)</Label>
            <Textarea
              id="admin-merge-notes"
              placeholder="Reason for merge, context, etc."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button
            variant="destructive"
            onClick={handleMerge}
            disabled={!targetId || mergeMutation.isPending}
          >
            {mergeMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Merging...
              </>
            ) : (
              "Merge Into Target"
            )}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
