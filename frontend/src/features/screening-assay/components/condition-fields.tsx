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
      {defs.map((cd) => (
        <div key={cd.id} className="grid gap-1">
          <Label className="text-xs">{cd.unit ? `${cd.name} (${cd.unit})` : cd.name}</Label>
          <ConditionValueInput
            def={cd}
            value={values[cd.name] ?? ""}
            onChange={(v) => onChange(cd.name, v)}
            disabled={disabled}
          />
        </div>
      ))}
    </>
  );
}

interface ConditionValueInputProps {
  def: Pick<ConditionDefinition, "data_type" | "unit" | "pick_list_values">;
  /** Bare value (no unit suffix); "" is none. */
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  /** What the empty pick-list choice reads. */
  noneLabel?: string;
  "aria-label"?: string;
}

/** One condition value: a Select for a pick list, a numeric or text Input otherwise. Serves a
 *  run's value and the protocol's fixed value alike. */
export function ConditionValueInput({
  def,
  value,
  onChange,
  disabled,
  noneLabel = "(not recorded)",
  "aria-label": ariaLabel,
}: ConditionValueInputProps) {
  const pickListValues = def.pick_list_values ?? [];
  const isNumeric = def.data_type === "numeric";
  if (def.data_type === "pick_list" && pickListValues.length > 0) {
    return (
      <Select
        value={value || "__none__"}
        onValueChange={(v) => onChange(v === "__none__" ? "" : v)}
        disabled={disabled}
      >
        <SelectTrigger aria-label={ariaLabel}>
          <SelectValue placeholder="Select..." />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">{noneLabel}</SelectItem>
          {pickListValues.map((opt) => (
            <SelectItem key={opt} value={opt}>
              {opt}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  return (
    <Input
      type={isNumeric ? "number" : "text"}
      inputMode={isNumeric ? "decimal" : undefined}
      placeholder={isNumeric ? (def.unit ? `e.g. 10 (${def.unit})` : "e.g. 10") : undefined}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      aria-label={ariaLabel}
    />
  );
}
