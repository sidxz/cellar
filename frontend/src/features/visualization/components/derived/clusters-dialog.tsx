"use client";

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
import { useId, useState } from "react";
import { CLUSTER_MAX_COMPOUNDS, CLUSTER_MIN_COMPOUNDS } from "../../lib/limits";

const fmt = (n: number) => n.toLocaleString();

/** "Clusters…": the cluster job's threshold (its own default, editable) over the dataset's
 * ``compoundCount`` compounds with a structure; refused, saying why, outside the job's bounds. */
export function ClustersDialog({
  open,
  onOpenChange,
  compoundCount,
  initialThreshold = 0.4,
  onApply,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  compoundCount: number;
  initialThreshold?: number;
  onApply: (threshold: number) => void;
}) {
  const [text, setText] = useState(String(initialThreshold));
  const id = useId();
  const threshold = Number(text);
  const badThreshold = text.trim() === "" || !(threshold >= 0.05 && threshold <= 0.95);
  const reason =
    compoundCount < CLUSTER_MIN_COMPOUNDS
      ? `Clustering needs at least ${CLUSTER_MIN_COMPOUNDS} compounds.`
      : compoundCount > CLUSTER_MAX_COMPOUNDS
        ? `${fmt(compoundCount)} compounds; clustering is capped at ${fmt(CLUSTER_MAX_COMPOUNDS)}. Choose fewer runs.`
        : badThreshold
          ? "Enter a threshold from 0.05 to 0.95."
          : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add cluster columns</DialogTitle>
          <DialogDescription>
            Groups the {fmt(compoundCount)} compounds with a structure by similarity: a Cluster
            column and the cluster map's X and Y.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor={id}>Cluster threshold (Tanimoto distance)</Label>
          <Input
            id={id}
            type="number"
            min={0.05}
            max={0.95}
            step={0.05}
            className="w-28"
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-invalid={badThreshold}
            aria-describedby={reason ? `${id}-hint ${id}-reason` : `${id}-hint`}
          />
          <p id={`${id}-hint`} className="text-xs text-muted-foreground">
            Lower = tighter clusters. Butina clustering on Morgan fingerprints; the map is UMAP.
          </p>
        </div>
        <p className="text-sm text-muted-foreground">
          Over 500 compounds run in the background — you can keep working.
        </p>
        {reason && (
          <p id={`${id}-reason`} className="text-sm text-warning">
            {reason}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={reason !== null}
            onClick={() => {
              onApply(threshold);
              onOpenChange(false);
            }}
          >
            Add cluster columns
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
