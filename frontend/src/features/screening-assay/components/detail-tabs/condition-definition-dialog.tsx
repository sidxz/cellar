"use client";

import { PickListValuesInput } from "@/shared/components/pick-list-values-input";
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
import { UnitPicker } from "@/shared/components/unit-picker";
import { isFixedValueValid } from "../../lib/conditions";
import { ConditionValueInput } from "../condition-fields";

// ---------------------------------------------------------------------------
// ConditionDefinitionDialog — handles both add and edit modes.
// Form state is controlled by the parent (5 fields, kept there as useState).
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
  cdValues: string[];
  setCdValues: (v: string[]) => void;
  cdFixedValue: string;
  setCdFixedValue: (v: string) => void;
  /** False on a published protocol: a fixed value is then set with Correct details. */
  allowFixedValue: boolean;
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
  cdValues,
  setCdValues,
  cdFixedValue,
  setCdFixedValue,
  allowFixedValue,
  isSaving,
  onSave,
  onCancel,
}: ConditionDefinitionDialogProps) {
  const isAdd = mode === "add";
  // The backend refuses a pick list with no values.
  const fixedValid = isFixedValueValid({
    data_type: cdDataType,
    pick_list_values: cdValues,
    fixed_value: cdFixedValue,
  });
  const canSave =
    !!cdName.trim() && (cdDataType !== "pick_list" || cdValues.length > 0) && fixedValid;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isAdd ? "Add Condition Definition" : "Edit Condition Definition"}
          </DialogTitle>
          <DialogDescription>
            {isAdd
              ? "Define an experimental condition. Fix its value when it defines the protocol."
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
            <UnitPicker value={cdUnit} onChange={setCdUnit} />
          </div>
          {cdDataType === "pick_list" && (
            <div className="space-y-1">
              <Label>Values</Label>
              <PickListValuesInput values={cdValues} onChange={setCdValues} />
            </div>
          )}
          {!allowFixedValue ? (
            <p className="text-xs text-muted-foreground">
              Add the condition, then set its fixed value with Correct details.
            </p>
          ) : (
            <div className="space-y-1">
              <Label>Fixed for this protocol (optional)</Label>
              <ConditionValueInput
                def={{ data_type: cdDataType, unit: cdUnit, pick_list_values: cdValues }}
                value={cdFixedValue}
                onChange={setCdFixedValue}
                noneLabel="(varies per run)"
                aria-label="Fixed for this protocol"
              />
              {!fixedValid && (
                <p className="text-xs text-destructive">
                  {cdDataType === "numeric" ? "Must be a number." : "Must be one of the values."}
                </p>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button disabled={!canSave || isSaving} onClick={onSave}>
            {isSaving ? (isAdd ? "Adding..." : "Saving...") : isAdd ? "Add" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
