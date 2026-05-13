"use client";

/**
 * ManualAddDialog — extracted from compound-list-pane.tsx (Task 2.3)
 *
 * Controlled dialog for adding a single compound to a campaign by name /
 * registration number search.
 */

import { useState } from "react";
import { SearchInput } from "@/shared/components/search-input";
import { useQueryClient } from "@tanstack/react-query";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Button } from "@/shared/components/ui/button";

import { useMoleculeSearch } from "@/features/chemical-registration/hooks/use-molecules";
import { useAddResultRowApiV1CampaignsCampaignIdResultsPost } from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../../lib/hooks";

export interface ManualAddDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: string;
}

export function ManualAddDialog({ open, onOpenChange, campaignId }: ManualAddDialogProps) {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");

  const { data: results, isLoading } = useMoleculeSearch(search);

  const addMutation = useAddResultRowApiV1CampaignsCampaignIdResultsPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onOpenChange(false);
        setSearch("");
      },
    },
  });

  const handleOpenChange = (o: boolean) => {
    if (!o) setSearch("");
    onOpenChange(o);
  };

  const handleSelect = (moleculeId: string) => {
    addMutation.mutate({
      campaignId,
      data: { molecule_id: moleculeId },
    });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Compound</DialogTitle>
          <DialogDescription>
            Search for a compound to add to this campaign.
          </DialogDescription>
        </DialogHeader>

        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search by name or reg number..."
          autoFocus
        />

        <div className="max-h-52 overflow-y-auto border rounded divide-y text-sm">
          {search.length < 2 && (
            <p className="p-2 text-muted-foreground text-xs">Type at least 2 characters</p>
          )}
          {isLoading && <p className="p-2 text-muted-foreground text-xs">Searching…</p>}
          {!isLoading && search.length >= 2 && !results?.length && (
            <p className="p-2 text-muted-foreground text-xs">No results</p>
          )}
          {results?.map((mol) => (
            <button
              key={mol.id}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/50 text-left"
              onClick={() => handleSelect(mol.id)}
              disabled={addMutation.isPending}
            >
              <span className="font-mono text-xs text-muted-foreground">
                {mol.registration_number}
              </span>
              <span className="truncate">{mol.name}</span>
            </button>
          ))}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
