"use client";

import { useState } from "react";
import { FolderPlus, Search } from "lucide-react";
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
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { useCollections } from "@/features/research-organization/hooks/use-collections";
import { useAddMolecules } from "@/features/research-organization/hooks/use-collection-molecules";

interface CollectionPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  moleculeIds: string[];
}

export function CollectionPickerDialog({
  open,
  onOpenChange,
  moleculeIds,
}: CollectionPickerDialogProps) {
  const { data: collections } = useCollections();
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const addMutation = useAddMolecules(selected ?? "");

  const filtered = collections?.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleAdd = () => {
    if (!selected || moleculeIds.length === 0) return;
    addMutation.mutate(
      {
        references: moleculeIds.map((id) => ({
          value: id,
          ref_type: "uuid" as const,
        })),
      },
      {
        onSuccess: () => {
          // useAddMolecules already shows a success toast via showSuccess
          onOpenChange(false);
          setSelected(null);
          setSearch("");
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add to Collection</DialogTitle>
          <DialogDescription>
            Add {moleculeIds.length} compound
            {moleculeIds.length !== 1 ? "s" : ""} to a collection.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search collections..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        <ScrollArea className="h-[240px]">
          <div className="space-y-1">
            {filtered?.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-sm transition-colors ${
                  selected === c.id
                    ? "bg-primary/10 text-primary"
                    : "hover:bg-accent"
                }`}
                onClick={() => setSelected(c.id)}
              >
                <span>{c.name}</span>
                <span className="text-xs text-muted-foreground">
                  {c.molecule_count} compound{c.molecule_count !== 1 ? "s" : ""}
                </span>
              </button>
            ))}
            {filtered?.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No collections found.
              </p>
            )}
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleAdd}
            disabled={!selected || addMutation.isPending}
          >
            <FolderPlus className="mr-2 h-4 w-4" />
            {addMutation.isPending ? "Adding..." : "Add to Collection"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
