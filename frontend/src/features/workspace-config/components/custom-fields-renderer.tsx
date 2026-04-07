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
import type { CustomFieldDefinition } from "../hooks/use-custom-fields";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FieldOverride {
  field_definition_id: string;
  is_required?: boolean | null;
  default_value?: unknown;
  is_locked?: boolean;
  pick_list_subset?: string[] | null;
}

interface Props {
  definitions: CustomFieldDefinition[];
  formOverrides?: FieldOverride[];
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  readOnly?: boolean;
}

// ---------------------------------------------------------------------------
// CustomFieldsRenderer
// ---------------------------------------------------------------------------

export function CustomFieldsRenderer({
  definitions,
  formOverrides = [],
  values,
  onChange,
  readOnly = false,
}: Props) {
  if (definitions.length === 0) return null;

  const sorted = [...definitions].sort((a, b) => a.display_order - b.display_order);

  const getOverride = (defId: string): FieldOverride | undefined =>
    formOverrides.find((o) => o.field_definition_id === defId);

  const handleChange = (name: string, value: unknown) => {
    onChange({ ...values, [name]: value });
  };

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
      {sorted.map((def) => {
        const override = getOverride(def.id);
        const isRequired = override?.is_required ?? def.is_required;
        const isLocked = override?.is_locked ?? false;
        const disabled = readOnly || isLocked;
        const rawValue = values[def.name];
        const stringValue = rawValue != null ? String(rawValue) : "";

        const pickListOptions =
          override?.pick_list_subset ?? def.pick_list_values ?? [];

        return (
          <div key={def.id} className="grid gap-1.5">
            <Label htmlFor={`cf-${def.name}`} className="text-sm">
              {def.label}
              {isRequired && (
                <span className="ml-0.5 text-destructive" aria-label="required">
                  *
                </span>
              )}
            </Label>

            {def.data_type === "picklist" ? (
              disabled ? (
                <Input
                  id={`cf-${def.name}`}
                  value={stringValue}
                  disabled
                  readOnly
                />
              ) : (
                <Select
                  value={stringValue}
                  onValueChange={(v) => handleChange(def.name, v)}
                  disabled={disabled}
                >
                  <SelectTrigger id={`cf-${def.name}`}>
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    {pickListOptions.map((opt) => (
                      <SelectItem key={opt} value={opt}>
                        {opt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )
            ) : (
              <Input
                id={`cf-${def.name}`}
                type={
                  def.data_type === "number"
                    ? "number"
                    : def.data_type === "date"
                    ? "date"
                    : "text"
                }
                value={stringValue}
                onChange={(e) => handleChange(def.name, e.target.value)}
                disabled={disabled}
                readOnly={readOnly}
                placeholder={
                  def.data_type === "file"
                    ? "File upload not supported here"
                    : def.data_type === "batch_link"
                    ? "Batch number or ID"
                    : ""
                }
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
