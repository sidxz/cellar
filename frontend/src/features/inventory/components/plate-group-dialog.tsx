"use client";

import { useVocabularyTerms } from "@/features/workspace-config/hooks/use-vocabularies";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
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
import { useEffect, useState } from "react";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { useCreatePlateGroup, useUpdatePlateGroup } from "../hooks/use-plate-groups";

/** Spec §4.2 seed list — used when no `plate_group_type` vocabulary exists. */
const DEFAULT_GROUP_TYPES = ["vendor", "screening", "master_twin", "hit_collection"];
const NONE = "__none__";

export interface PlateGroupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Owner org for creation (ignored in edit mode). */
  orgId: string;
  /** Parent for creation (null = root; ignored in edit mode). */
  parentGroupId: string | null;
  /** Non-null switches the dialog to edit mode. */
  group: PlateGroupNode | null;
}

export function PlateGroupDialog({
  open,
  onOpenChange,
  orgId,
  parentGroupId,
  group,
}: PlateGroupDialogProps) {
  const isEdit = group !== null;
  const [name, setName] = useState("");
  const [groupType, setGroupType] = useState<string>(NONE);
  const [description, setDescription] = useState("");
  // Suggestions from the `plate_group_type` controlled vocabulary; seed list otherwise.
  const vocabTypes = useVocabularyTerms("plate_group_type");
  const groupTypes = vocabTypes.length > 0 ? vocabTypes : DEFAULT_GROUP_TYPES;
  const create = useCreatePlateGroup();
  const update = useUpdatePlateGroup();
  const pending = create.isPending || update.isPending;

  useEffect(() => {
    if (!open) return;
    setName(group?.name ?? "");
    setGroupType(group?.group_type ?? NONE);
    setDescription(group?.description ?? "");
  }, [open, group]);

  const handleSave = () => {
    const type = groupType === NONE ? null : groupType;
    const desc = description.trim() === "" ? null : description;
    const opts = { onSuccess: () => onOpenChange(false) };
    if (group) {
      update.mutate({ groupId: group.id, name, group_type: type, description: desc }, opts);
    } else {
      create.mutate(
        {
          name,
          owner_org_id: orgId,
          parent_group_id: parentGroupId,
          group_type: type,
          description: desc,
        },
        opts,
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit group" : parentGroupId ? "Add child group" : "New group"}
          </DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="group-name">Name</Label>
            <Input
              id="group-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={300}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="group-type">Type</Label>
            <Select value={groupType} onValueChange={setGroupType}>
              <SelectTrigger id="group-type" aria-label="Group type">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>None</SelectItem>
                {groupTypes.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="group-description">Description</Label>
            <Textarea
              id="group-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={pending || name.trim() === ""}>
            {isEdit ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
