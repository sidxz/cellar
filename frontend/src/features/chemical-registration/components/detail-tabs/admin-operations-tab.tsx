"use client";

import { MoleculeSelector } from "@/features/inventory/components/molecule-selector";
import { CascadeDeleteDialog } from "@/shared/components/cascade-delete-dialog";
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
import { AlertTriangle, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMergeMolecules } from "../../hooks/use-disclosures";
import { useMolecule } from "../../hooks/use-molecules";
import type { Molecule } from "../../types";

interface AdminOperationsTabProps {
  moleculeId: string;
}

export function AdminOperationsTab({ moleculeId }: AdminOperationsTabProps) {
  const router = useRouter();
  const { data: molecule } = useMolecule(moleculeId);
  const mergeMutation = useMergeMolecules(moleculeId);

  const [target, setTarget] = useState<Molecule | null>(null);
  const targetId = target?.id ?? null;
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
      setTarget(null);
      setNotes("");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Merge failed";
      setError(message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Hard delete — cascade removes all dependent rows */}
      {molecule && (
        <Card>
          <CardHeader>
            <CardTitle>Permanent deletion</CardTitle>
            <CardDescription>
              Permanently delete this compound and all its dependent data (batches, assay results,
              identifiers, relationships). Cannot be undone.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CascadeDeleteDialog
              entityType="molecule"
              entityId={moleculeId}
              entityLabel={molecule.registration_number ?? moleculeId}
              onDeleted={() => router.push("/compounds")}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Manual Merge</CardTitle>
          <CardDescription>
            Select the compound that will receive the merged records.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
            <AlertTriangle className="mr-2 inline h-4 w-4" />
            {molecule?.registration_number ?? moleculeId} will be marked as merged into{" "}
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
