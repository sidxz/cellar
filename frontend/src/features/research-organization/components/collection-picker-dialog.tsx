"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Badge } from "@/shared/components/ui/badge";
import { Plus, CheckCircle2, AlertCircle } from "lucide-react";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { useCollections, useCreateCollection } from "../hooks/use-collections";
import { useAddMolecules } from "../hooks/use-collection-molecules";
import type { MembershipResult, MoleculeReference } from "../types";

interface CollectionPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  moleculeIds: string[];
  onComplete?: () => void;
}

export function CollectionPickerDialog({
  open,
  onOpenChange,
  moleculeIds,
  onComplete,
}: CollectionPickerDialogProps) {
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [result, setResult] = useState<MembershipResult | null>(null);
  const [isPendingDirect, setIsPendingDirect] = useState(false);

  const { data: collections } = useCollections();
  const createMutation = useCreateCollection();
  // Used for the normal "add to existing collection" path only.
  const addMutation = useAddMolecules(selectedCollectionId);

  const reset = () => {
    setSelectedCollectionId("");
    setCreating(false);
    setNewName("");
    setResult(null);
    setIsPendingDirect(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) reset();
    onOpenChange(nextOpen);
  };

  /**
   * Call the membership endpoint directly with a known collectionId.
   * This is needed for the create-and-add flow because `useAddMolecules`
   * closes over `selectedCollectionId` at hook instantiation time; calling
   * addMutation.mutateAsync after creating a new collection would still hit
   * the stale (empty-string) URL.
   */
  const addDirectly = async (collectionId: string): Promise<MembershipResult> => {
    const refs: MoleculeReference[] = moleculeIds.map((id) => ({
      value: id,
      ref_type: "uuid",
    }));
    return customInstance<MembershipResult>({
      url: `/api/v1/collections/${collectionId}/molecules`,
      method: "POST",
      data: { references: refs },
    });
  };

  const handleCreateAndAdd = async () => {
    setIsPendingDirect(true);
    try {
      const col = await createMutation.mutateAsync({ name: newName });
      const res = await addDirectly(col.id);
      setResult(res);
      setCreating(false);
      setNewName("");
    } finally {
      setIsPendingDirect(false);
    }
  };

  const handleAdd = async () => {
    const refs: MoleculeReference[] = moleculeIds.map((id) => ({
      value: id,
      ref_type: "uuid",
    }));
    const res = await addMutation.mutateAsync({ references: refs });
    setResult(res);
  };

  const handleDone = () => {
    handleOpenChange(false);
    onComplete?.();
  };

  const isPending =
    addMutation.isPending || createMutation.isPending || isPendingDirect;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add to Collection</DialogTitle>
          <DialogDescription>
            Add {moleculeIds.length} molecule
            {moleculeIds.length !== 1 ? "s" : ""} to a collection.
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              <span className="text-sm font-medium">
                {result.added_count} added
              </span>
              {result.already_present > 0 && (
                <Badge variant="secondary">
                  {result.already_present} already present
                </Badge>
              )}
            </div>
            {result.unresolved.length > 0 && (
              <div className="flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-yellow-500" />
                <span className="text-sm">
                  {result.unresolved.length} could not be resolved
                </span>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4 py-2">
            {creating ? (
              <div className="space-y-2">
                <Label>New collection name</Label>
                <div className="flex gap-2">
                  <Input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Enter name..."
                    autoFocus
                  />
                  <Button
                    size="sm"
                    onClick={handleCreateAndAdd}
                    disabled={!newName.trim() || isPending}
                  >
                    Create &amp; Add
                  </Button>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setCreating(false)}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <Label>Choose collection</Label>
                <Select
                  value={selectedCollectionId}
                  onValueChange={setSelectedCollectionId}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a collection..." />
                  </SelectTrigger>
                  <SelectContent>
                    {collections?.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({c.molecule_count})
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCreating(true)}
                >
                  <Plus className="mr-1 h-3 w-3" />
                  Create New Collection
                </Button>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {result ? (
            <Button onClick={handleDone}>Done</Button>
          ) : (
            <Button
              onClick={handleAdd}
              disabled={!selectedCollectionId || isPending || creating}
            >
              {isPending ? "Adding..." : "Add to Collection"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
