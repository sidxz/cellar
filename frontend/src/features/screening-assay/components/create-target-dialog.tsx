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
import { Textarea } from "@/shared/components/ui/textarea";
import { useState } from "react";
import { useCreateTarget } from "../hooks/use-targets";
import { TARGET_TYPE_LABELS, type Target, type TargetType } from "../types";

interface CreateTargetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fired with the newly-created target after a successful create. Lets a
   *  caller (e.g. an inline picker) auto-select what was just made. */
  onCreated?: (target: Target) => void;
}

export function CreateTargetDialog({ open, onOpenChange, onCreated }: CreateTargetDialogProps) {
  const createMutation = useCreateTarget();
  const [name, setName] = useState("");
  const [targetType, setTargetType] = useState<string>("single_protein");
  const [organism, setOrganism] = useState("");
  const [geneName, setGeneName] = useState("");
  const [uniprotId, setUniprotId] = useState("");
  const [description, setDescription] = useState("");

  const resetForm = () => {
    setName("");
    setTargetType("single_protein");
    setOrganism("");
    setGeneName("");
    setUniprotId("");
    setDescription("");
  };

  const handleSubmit = () => {
    createMutation.mutate(
      {
        name,
        target_type: targetType as TargetType,
        organism: organism || null,
        gene_name: geneName || null,
        uniprot_id: uniprotId || null,
        description: description || null,
      },
      {
        onSuccess: (created) => {
          onOpenChange(false);
          resetForm();
          onCreated?.(created);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Target</DialogTitle>
          <DialogDescription>Define a biological target for screening protocols.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input
              placeholder="e.g., EGFR Kinase"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Type</Label>
            <Select value={targetType} onValueChange={setTargetType}>
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
          <Button onClick={handleSubmit} disabled={!name.trim() || createMutation.isPending}>
            {createMutation.isPending ? "Creating..." : "Create Target"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
