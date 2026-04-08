"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Plus, X } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMoleculeCollections } from "../../hooks/use-molecule-collections";
import { CollectionPickerDialog } from "@/features/research-organization/components/collection-picker-dialog";

// ---------------------------------------------------------------------------
// CollectionsTab
// ---------------------------------------------------------------------------

interface CollectionsTabProps {
  moleculeId: string;
}

export function CollectionsTab({ moleculeId }: CollectionsTabProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const { data: collections, isLoading } = useMoleculeCollections(moleculeId);
  const qc = useQueryClient();

  const removeMutation = useMutation({
    mutationFn: (collectionId: string) =>
      customInstance<{ removed: number }>({
        url: `/api/v1/collections/${collectionId}/molecules`,
        method: "DELETE",
        data: { molecule_ids: [moleculeId] },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["molecules", moleculeId, "collections"] });
      qc.invalidateQueries({ queryKey: ["collections"] });
      showSuccess("Removed from collection");
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Collections containing this molecule.
        </p>
        <Button size="sm" variant="outline" onClick={() => setPickerOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add to Collection
        </Button>
      </div>

      {!collections?.length ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <FolderOpen className="h-12 w-12 text-muted-foreground/40" />
          <h3 className="mt-4 text-lg font-semibold">No collections</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            This molecule is not in any collections yet.
          </p>
          <Button
            className="mt-4"
            size="sm"
            variant="outline"
            onClick={() => setPickerOpen(true)}
          >
            <Plus className="mr-2 h-4 w-4" />
            Add to Collection
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {collections.map((col) => (
            <div
              key={col.id}
              className="flex items-center gap-3 rounded-lg border p-3"
            >
              <FolderOpen className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <Link
                  href={`/collections/${col.id}`}
                  className="text-sm font-medium text-primary underline-offset-4 hover:underline"
                >
                  {col.name}
                </Link>
              </div>
              <Badge variant="secondary">
                {col.molecule_count} molecule{col.molecule_count !== 1 ? "s" : ""}
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                onClick={() => removeMutation.mutate(col.id)}
                disabled={removeMutation.isPending}
                title="Remove from collection"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <CollectionPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        moleculeIds={[moleculeId]}
        onComplete={() => {
          qc.invalidateQueries({ queryKey: ["molecules", moleculeId, "collections"] });
        }}
      />
    </div>
  );
}
