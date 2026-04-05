"use client";

import { useState } from "react";
import { Badge } from "@/shared/components/ui/badge";
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
import { StructureRenderer } from "@/shared/components/chemistry";
import { useMolecule } from "../hooks/use-molecules";
import { useResolveDisclosureConflict } from "../hooks/use-disclosures";
import type { DisclosureRequest } from "../types/disclosure";

interface ResolveConflictDialogProps {
  disclosure: DisclosureRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ResolveConflictDialog({
  disclosure,
  open,
  onOpenChange,
}: ResolveConflictDialogProps) {
  const { data: molecule } = useMolecule(disclosure.molecule_id);
  const resolve = useResolveDisclosureConflict(disclosure.id);
  const [reason, setReason] = useState("");

  const handleResolve = (resolution: string) => {
    resolve.mutate(
      { resolution, reason: reason || undefined },
      { onSuccess: () => onOpenChange(false) }
    );
  };

  const existingSmiles =
    molecule?.structure_status === "disclosed"
      ? molecule.structure?.smiles
      : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Resolve Disclosure Conflict</DialogTitle>
          <DialogDescription>
            Compare the disclosed structure with any existing structure and
            choose a resolution.
          </DialogDescription>
        </DialogHeader>

        {/* Conflict details */}
        {disclosure.conflict_reason && (
          <div className="rounded-md bg-destructive/10 p-3">
            <p className="text-sm font-medium text-destructive">
              {disclosure.conflict_reason}
            </p>
          </div>
        )}

        {/* Side-by-side comparison */}
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg border p-4">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="text-sm font-semibold">Existing Structure</h3>
              <Badge variant="outline">Current</Badge>
            </div>
            {existingSmiles ? (
              <StructureRenderer
                smiles={existingSmiles}
                width={250}
                height={200}
              />
            ) : (
              <div className="flex h-[200px] items-center justify-center rounded bg-muted text-sm text-muted-foreground">
                {molecule?.structure_status === "undisclosed"
                  ? "Undisclosed"
                  : "No structure"}
              </div>
            )}
            {existingSmiles && (
              <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                {existingSmiles}
              </p>
            )}
          </div>

          <div className="rounded-lg border p-4">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="text-sm font-semibold">Disclosed Structure</h3>
              <Badge variant="secondary">New</Badge>
            </div>
            <StructureRenderer
              smiles={disclosure.disclosed_smiles}
              width={250}
              height={200}
            />
            <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
              {disclosure.disclosed_smiles}
            </p>
          </div>
        </div>

        <div className="grid gap-2">
          <Label>Resolution Reason (optional)</Label>
          <Input
            placeholder="Why this resolution was chosen..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row">
          <Button
            variant="outline"
            onClick={() => handleResolve("reject")}
            disabled={resolve.isPending}
          >
            Reject
          </Button>
          <Button
            variant="outline"
            onClick={() => handleResolve("accept_merge")}
            disabled={resolve.isPending}
          >
            Accept & Merge
          </Button>
          <Button
            onClick={() => handleResolve("accept_as_new")}
            disabled={resolve.isPending}
          >
            {resolve.isPending ? "Resolving..." : "Accept as New"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
