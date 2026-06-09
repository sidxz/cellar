"use client";

import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { ConditionDefinition } from "../types";

interface ConditionFieldsProps {
  /** Condition definitions to render one input each (declared + any extras). */
  defs: ConditionDefinition[];
  /** name → bare value (no unit suffix). */
  values: Record<string, string>;
  /** Called with the definition name and the new bare value. */
  onChange: (name: string, value: string) => void;
  disabled?: boolean;
}

/**
 * Renders one input per condition definition: a Select for pick-list types, a
 * numeric/text Input otherwise, with the declared unit shown in the label.
 * Holds bare values (the unit is appended at save time) so the same component
 * serves both the New Run dialog and the run-detail conditions editor.
 */
export function ConditionFields({ defs, values, onChange, disabled }: ConditionFieldsProps) {
  return (
    <>
      {defs.map((cd) => {
        const value = values[cd.name] ?? "";
        const labelText = cd.unit ? `${cd.name} (${cd.unit})` : cd.name;
        const pickListValues = cd.pick_list_values ?? [];
        const isPickList = cd.data_type === "pick_list" && pickListValues.length > 0;
        const isNumeric = cd.data_type === "numeric";
        return (
          <div key={cd.id} className="grid gap-1">
            <Label className="text-xs">{labelText}</Label>
            {isPickList ? (
              <Select
                value={value || "__none__"}
                onValueChange={(v) => onChange(cd.name, v === "__none__" ? "" : v)}
                disabled={disabled}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">(not recorded)</SelectItem>
                  {pickListValues.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                type={isNumeric ? "number" : "text"}
                inputMode={isNumeric ? "decimal" : undefined}
                placeholder={isNumeric ? (cd.unit ? `e.g. 10 (${cd.unit})` : "e.g. 10") : undefined}
                value={value}
                onChange={(e) => onChange(cd.name, e.target.value)}
                disabled={disabled}
              />
            )}
          </div>
        );
      })}
    </>
  );
}
