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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { COLLECTIONS_KEY } from "../hooks/query-keys";
import { useCollections } from "../hooks/use-collections";
import type { Collection } from "../types";

interface BooleanCollectionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const OPERATIONS = [
  { value: "union", label: "Union", description: "Molecules in ANY selected collection" },
  { value: "intersect", label: "Intersect", description: "Molecules in ALL selected collections" },
  { value: "difference", label: "Difference", description: "In first but not others" },
  { value: "symmetric_difference", label: "Exclusive", description: "In exactly one collection" },
] as const;

export function BooleanCollectionsDialog({ open, onOpenChange }: BooleanCollectionsDialogProps) {
  const queryClient = useQueryClient();
  const { data: collections } = useCollections();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [operation, setOperation] = useState<string>("union");
  const [resultName, setResultName] = useState("");

  const composeMutation = useMutation({
    mutationFn: (params: { operation: string; collection_ids: string[]; result_name: string }) =>
      customInstance<Collection>({
        url: `${API_V1}/collections/compose`,
        method: "POST",
        data: params,
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: COLLECTIONS_KEY });
      showSuccess(`Created "${data.name}" with ${data.molecule_count} molecules`);
      handleClose();
    },
  });

  const handleClose = () => {
    setSelectedIds([]);
    setOperation("union");
    setResultName("");
    onOpenChange(false);
  };

  const toggleCollection = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSubmit = () => {
    composeMutation.mutate({
      operation,
      collection_ids: selectedIds,
      result_name: resultName,
    });
  };

  const opInfo = OPERATIONS.find((o) => o.value === operation);

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) handleClose();
        else onOpenChange(o);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Boolean Collection Operations</DialogTitle>
          <DialogDescription>
            Create a new collection from a set operation on existing collections.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Select collections (min 2)</Label>
            <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border p-2">
              {collections?.map((c) => (
                <label
                  key={c.id}
                  className="flex items-center gap-2 rounded p-1 hover:bg-muted/50 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(c.id)}
                    onChange={() => toggleCollection(c.id)}
                  />
                  <span className="text-sm">{c.name}</span>
                  <span className="text-xs text-muted-foreground">({c.molecule_count})</span>
                </label>
              ))}
              {!collections?.length && (
                <p className="py-2 text-center text-sm text-muted-foreground">
                  No collections available
                </p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label>Operation</Label>
            <Select value={operation} onValueChange={setOperation}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {OPERATIONS.map((op) => (
                  <SelectItem key={op.value} value={op.value}>
                    {op.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {opInfo && <p className="text-xs text-muted-foreground">{opInfo.description}</p>}
          </div>

          <div className="space-y-2">
            <Label>Result collection name</Label>
            <Input
              value={resultName}
              onChange={(e) => setResultName(e.target.value)}
              placeholder="Enter name for new collection..."
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={selectedIds.length < 2 || !resultName.trim() || composeMutation.isPending}
          >
            {composeMutation.isPending ? "Creating..." : "Create Collection"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
