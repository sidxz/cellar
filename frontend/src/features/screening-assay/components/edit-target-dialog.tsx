"use client";

import { useState } from "react";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { useUpdateTarget } from "../hooks/use-targets";
import { TARGET_TYPE_LABELS, type Target, type TargetType } from "../types";

interface EditTargetDialogProps {
  target: Target;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditTargetDialog({
  target,
  open,
  onOpenChange,
}: EditTargetDialogProps) {
  const mutation = useUpdateTarget(target.id);
  const [name, setName] = useState(target.name);
  const [targetType, setTargetType] = useState(target.target_type);
  const [organism, setOrganism] = useState(target.organism ?? "");
  const [geneName, setGeneName] = useState(target.gene_name ?? "");
  const [uniprotId, setUniprotId] = useState(target.uniprot_id ?? "");
  const [description, setDescription] = useState(target.description ?? "");

  const handleSubmit = () => {
    mutation.mutate(
      {
        name,
        target_type: targetType,
        organism: organism || null,
        gene_name: geneName || null,
        uniprot_id: uniprotId || null,
        description: description || null,
      },
      { onSuccess: () => onOpenChange(false) }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Target</DialogTitle>
          <DialogDescription>
            Update target details for {target.name}.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          <div className="grid gap-2">
            <Label>Type</Label>
            <Select value={targetType} onValueChange={(v) => setTargetType(v as TargetType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(TARGET_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label>Organism</Label>
            <Input
              placeholder="e.g., Homo sapiens"
              value={organism}
              onChange={(e) => setOrganism(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Gene Name</Label>
            <Input
              placeholder="e.g., EGFR"
              value={geneName}
              onChange={(e) => setGeneName(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>UniProt ID</Label>
            <Input
              placeholder="e.g., P00533"
              value={uniprotId}
              onChange={(e) => setUniprotId(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Description</Label>
            <Textarea
              placeholder="Optional description..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!name.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
