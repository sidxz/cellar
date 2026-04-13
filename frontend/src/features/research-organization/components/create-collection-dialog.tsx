"use client";

import { useEffect, useState } from "react";
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
import { SearchableSelect } from "@/shared/components/searchable-select";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useProjects } from "../hooks/use-projects";
import {
  useCreateCollection,
  useUpdateCollection,
} from "../hooks/use-collections";
import type { Collection } from "../types";

interface CreateCollectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pass a collection to switch to edit mode. */
  collection?: Collection;
  /** Pre-select a project (e.g., when creating from project detail). */
  defaultProjectId?: string;
}

const NO_SELECTION = "__none__";

export function CreateCollectionDialog({
  open,
  onOpenChange,
  collection,
  defaultProjectId,
}: CreateCollectionDialogProps) {
  const isEdit = !!collection;
  const createMutation = useCreateCollection();
  const updateMutation = useUpdateCollection(collection?.id ?? "");

  const { data: projects } = useProjects();
  const { data: orgs } = useOrganizations();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [projectId, setProjectId] = useState<string>(NO_SELECTION);
  const [orgId, setOrgId] = useState<string>(NO_SELECTION);
  const [visibility, setVisibility] = useState<"private" | "shared">("private");

  // Reset form when dialog opens / collection changes
  useEffect(() => {
    if (open) {
      setName(collection?.name ?? "");
      setDescription(collection?.description ?? "");
      setProjectId(
        collection?.project_id ?? defaultProjectId ?? NO_SELECTION
      );
      setOrgId(collection?.owned_by_org_id ?? NO_SELECTION);
      setVisibility(collection?.visibility ?? "private");
    }
  }, [open, collection, defaultProjectId]);

  const resetForm = () => {
    setName("");
    setDescription("");
    setProjectId(defaultProjectId ?? NO_SELECTION);
    setOrgId(NO_SELECTION);
    setVisibility("private");
  };

  const mutation = isEdit ? updateMutation : createMutation;
  const canSubmit = name.trim() && !mutation.isPending;

  const handleSubmit = () => {
    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      project_id: projectId === NO_SELECTION ? null : projectId,
      owned_by_org_id: orgId === NO_SELECTION ? null : orgId,
      visibility,
    };

    mutation.mutate(payload, {
      onSuccess: () => {
        onOpenChange(false);
        resetForm();
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit Collection" : "New Collection"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the collection details."
              : "Create a collection to group related molecules."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input
              placeholder="e.g., EGFR Hit Series A"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit) handleSubmit();
              }}
            />
          </div>

          <div className="grid gap-2">
            <Label>Description (optional)</Label>
            <Textarea
              placeholder="Brief description of the collection..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>

          <div className="grid gap-2">
            <Label>Visibility</Label>
            <Select
              value={visibility}
              onValueChange={(v) => setVisibility(v as "private" | "shared")}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="private">Private</SelectItem>
                <SelectItem value="shared">Shared</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label>Project (optional)</Label>
            <SearchableSelect
              options={projects?.filter((p) => p.status === "active").map((p) => ({ value: p.id, label: p.name })) ?? []}
              value={projectId === NO_SELECTION ? null : projectId}
              onValueChange={(v) => setProjectId(v ?? NO_SELECTION)}
              placeholder="No project"
              searchPlaceholder="Search projects..."
            />
          </div>

          <div className="grid gap-2">
            <Label>Organization (optional)</Label>
            <SearchableSelect
              options={orgs?.map((o) => ({ value: o.id, label: o.name })) ?? []}
              value={orgId === NO_SELECTION ? null : orgId}
              onValueChange={(v) => setOrgId(v ?? NO_SELECTION)}
              placeholder="No organization"
              searchPlaceholder="Search organizations..."
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {mutation.isPending
              ? isEdit
                ? "Saving..."
                : "Creating..."
              : isEdit
                ? "Save Changes"
                : "Create Collection"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
