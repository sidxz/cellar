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

// ---------------------------------------------------------------------------
// ConditionDefinitionDialog — handles both add and edit modes.
// Form state is controlled by the parent (3 fields, kept there as useState).
// ---------------------------------------------------------------------------

export interface ConditionDefinitionDialogProps {
  mode: "add" | "edit";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Controlled form fields
  cdName: string;
  setCdName: (v: string) => void;
  cdDataType: string;
  setCdDataType: (v: string) => void;
  cdUnit: string;
  setCdUnit: (v: string) => void;
  isSaving: boolean;
  onSave: () => void;
  onCancel: () => void;
}

export function ConditionDefinitionDialog({
  mode,
  open,
  onOpenChange,
  cdName,
  setCdName,
  cdDataType,
  setCdDataType,
  cdUnit,
  setCdUnit,
  isSaving,
  onSave,
  onCancel,
}: ConditionDefinitionDialogProps) {
  const isAdd = mode === "add";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isAdd ? "Add Condition Definition" : "Edit Condition Definition"}
          </DialogTitle>
          <DialogDescription>
            {isAdd
              ? "Define an experimental condition that varies between runs."
              : "Update fields on this condition. Only available while the protocol is in draft."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Name</Label>
            <Input
              value={cdName}
              onChange={(e) => setCdName(e.target.value)}
              placeholder={isAdd ? "e.g. Cell Passage, Temperature" : undefined}
            />
          </div>
          <div className="space-y-1">
            <Label>Data Type</Label>
            <Select value={cdDataType} onValueChange={setCdDataType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="text">Text</SelectItem>
                <SelectItem value="numeric">Numeric</SelectItem>
                <SelectItem value="pick_list">Pick List</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Unit</Label>
            <Input
              value={cdUnit}
              onChange={(e) => setCdUnit(e.target.value)}
              placeholder={isAdd ? "e.g. °C, hrs" : undefined}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button disabled={!cdName.trim() || isSaving} onClick={onSave}>
            {isSaving ? (isAdd ? "Adding..." : "Saving...") : isAdd ? "Add" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
