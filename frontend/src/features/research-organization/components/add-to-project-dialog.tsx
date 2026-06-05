"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { FolderPlus } from "lucide-react";
import { useState } from "react";
import { useAddMoleculeToProject } from "../hooks/use-molecule-projects";
import { useProjects } from "../hooks/use-projects";

interface AddToProjectDialogProps {
  moleculeId: string;
  existingProjectIds?: string[];
}

export function AddToProjectDialog({
  moleculeId,
  existingProjectIds = [],
}: AddToProjectDialogProps) {
  const [open, setOpen] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const { data: projects } = useProjects();
  const addMutation = useAddMoleculeToProject(selectedProjectId);

  const availableProjects = projects?.filter(
    (p) => p.status === "active" && !existingProjectIds.includes(p.id),
  );

  const handleAdd = () => {
    if (!selectedProjectId) return;
    addMutation.mutate(moleculeId, {
      onSuccess: () => {
        setOpen(false);
        setSelectedProjectId("");
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <FolderPlus className="mr-2 h-4 w-4" /> Add to Project
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Compound to Project</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Select value={selectedProjectId} onValueChange={setSelectedProjectId}>
            <SelectTrigger>
              <SelectValue placeholder="Select project..." />
            </SelectTrigger>
            <SelectContent>
              {availableProjects?.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={handleAdd} disabled={!selectedProjectId || addMutation.isPending}>
            Add
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
