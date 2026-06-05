"use client";

/**
 * AddFromCollectionDialog
 *
 * Lets the user pick a workspace Collection and add all its compounds
 * to the current campaign. Shows {added, skipped} in a toast on success.
 */

import { useCollections } from "@/features/research-organization/hooks/use-collections";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";
import { useAddResultsFromCollectionApiV1CampaignsCampaignIdAddFromCollectionPost } from "@/shared/lib/api/campaigns/campaigns";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { campaignKeys } from "../hooks/use-campaigns";

interface AddFromCollectionDialogProps {
  campaignId: string;
  projectId: string;
  open: boolean;
  onClose: () => void;
}

export function AddFromCollectionDialog({
  campaignId,
  projectId,
  open,
  onClose,
}: AddFromCollectionDialogProps) {
  const qc = useQueryClient();
  const [collectionId, setCollectionId] = useState("");
  const [description, setDescription] = useState("");

  const { data: collections, isLoading: collectionsLoading } = useCollections([projectId]);

  const mutation = useAddResultsFromCollectionApiV1CampaignsCampaignIdAddFromCollectionPost({
    mutation: {
      onSuccess: (result) => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        const collectionName =
          collections?.find((c) => c.id === collectionId)?.name ?? "collection";
        showSuccess(
          `Added ${result.added} compound${result.added !== 1 ? "s" : ""} from "${collectionName}". ` +
            `${result.skipped} were already on this campaign.`,
        );
        handleClose();
      },
      onError: () => {
        showError("Failed to add compounds from collection.");
      },
    },
  });

  const handleClose = () => {
    setCollectionId("");
    setDescription("");
    onClose();
  };

  const handleSubmit = () => {
    if (!collectionId) return;
    mutation.mutate({
      campaignId,
      data: {
        collection_id: collectionId,
        description: description.trim() || undefined,
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add compounds from a Collection</DialogTitle>
          <DialogDescription>
            All compounds in the selected collection will be added. Duplicates are skipped
            automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Collection *</Label>
            <Select
              value={collectionId}
              onValueChange={setCollectionId}
              disabled={collectionsLoading}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={collectionsLoading ? "Loading…" : "Select a collection…"}
                />
              </SelectTrigger>
              <SelectContent>
                {collections?.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                    {c.molecule_count != null && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        ({c.molecule_count})
                      </span>
                    )}
                  </SelectItem>
                ))}
                {!collectionsLoading && !collections?.length && (
                  <SelectItem value="__none__" disabled>
                    No collections in workspace
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="add-collection-desc">Note (optional)</Label>
            <Textarea
              id="add-collection-desc"
              placeholder="e.g. Q3 hit shortlist from EGFR panel"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={handleClose}>
            Cancel
          </Button>
          <Button size="sm" disabled={!collectionId || mutation.isPending} onClick={handleSubmit}>
            {mutation.isPending ? "Adding…" : "Add compounds"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
