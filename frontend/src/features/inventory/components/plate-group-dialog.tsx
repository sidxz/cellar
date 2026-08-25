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
import { useStorageLocations } from "../hooks/use-storage-locations";

/** Spec §4.2 seed list — used when no `plate_group_type` vocabulary exists. */
const DEFAULT_GROUP_TYPES = ["vendor", "screening", "master_twin", "hit_collection"];
/** Seed list — used when no `plate_group_state` vocabulary exists. */
export const DEFAULT_GROUP_STATES = ["Dry", "Solubilized", "Retired"];
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
  const [state, setState] = useState<string>(NONE);
  const [locationId, setLocationId] = useState<string>(NONE);
  const [volume, setVolume] = useState("");
  const [concentration, setConcentration] = useState("");
  const [compoundCount, setCompoundCount] = useState("");
  const [scientist, setScientist] = useState("");
  // Suggestions from the `plate_group_type` controlled vocabulary; seed list otherwise.
  const vocabTypes = useVocabularyTerms("plate_group_type");
  const groupTypes = vocabTypes.length > 0 ? vocabTypes : DEFAULT_GROUP_TYPES;
  const vocabStates = useVocabularyTerms("plate_group_state");
  const groupStates = vocabStates.length > 0 ? vocabStates : DEFAULT_GROUP_STATES;
  const { data: storageLocations } = useStorageLocations();
  const create = useCreatePlateGroup();
  const update = useUpdatePlateGroup();
  const pending = create.isPending || update.isPending;
  const hasNegative = Number(volume) < 0 || Number(concentration) < 0 || Number(compoundCount) < 0;

  useEffect(() => {
    if (!open) return;
    setName(group?.name ?? "");
    setGroupType(group?.group_type ?? NONE);
    setDescription(group?.description ?? "");
    setState(group?.state ?? NONE);
    setLocationId(group?.storage_location_id ?? NONE);
    setVolume(group?.initial_volume_ul != null ? String(group.initial_volume_ul) : "");
    setConcentration(
      group?.initial_concentration_mm != null ? String(group.initial_concentration_mm) : "",
    );
    setCompoundCount(group?.compound_count != null ? String(group.compound_count) : "");
    setScientist(group?.scientist ?? "");
  }, [open, group]);

  const handleSave = () => {
    const type = groupType === NONE ? null : groupType;
    const desc = description.trim() === "" ? null : description;
    const meta = {
      state: state === NONE ? null : state,
      storage_location_id: locationId === NONE ? null : locationId,
      initial_volume_ul: volume.trim() ? Number(volume) : null,
      initial_concentration_mm: concentration.trim() ? Number(concentration) : null,
      compound_count: compoundCount.trim() ? Number(compoundCount) : null,
      scientist: scientist.trim() ? scientist.trim() : null,
    };
    const opts = { onSuccess: () => onOpenChange(false) };
    if (group) {
      update.mutate(
        { groupId: group.id, name, group_type: type, description: desc, ...meta },
        opts,
      );
    } else {
      create.mutate(
        {
          name,
          owner_org_id: orgId,
          parent_group_id: parentGroupId,
          group_type: type,
          description: desc,
          ...meta,
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
            <Label htmlFor="group-state">State</Label>
            <Select value={state} onValueChange={setState}>
              <SelectTrigger id="group-state" aria-label="Group state">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>None</SelectItem>
                {groupStates.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="group-location">Storage location</Label>
            <Select value={locationId} onValueChange={setLocationId}>
              <SelectTrigger id="group-location" aria-label="Storage location">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>None</SelectItem>
                {storageLocations?.map((l) => (
                  <SelectItem key={l.id} value={l.id}>
                    {l.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="group-volume">Initial volume (µL)</Label>
              <Input
                id="group-volume"
                type="number"
                min={0}
                step="any"
                value={volume}
                onChange={(e) => setVolume(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="group-concentration">Initial concentration (mM)</Label>
              <Input
                id="group-concentration"
                type="number"
                min={0}
                step="any"
                value={concentration}
                onChange={(e) => setConcentration(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="group-compound-count">Compound count</Label>
            <Input
              id="group-compound-count"
              type="number"
              min={0}
              step={1}
              value={compoundCount}
              onChange={(e) => setCompoundCount(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="group-scientist">Scientist</Label>
            <Input
              id="group-scientist"
              value={scientist}
              onChange={(e) => setScientist(e.target.value)}
              maxLength={200}
            />
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
          <Button onClick={handleSave} disabled={pending || name.trim() === "" || hasNegative}>
            {isEdit ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
