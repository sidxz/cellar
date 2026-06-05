"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Plus, Trash2 } from "lucide-react";
import type { CurveType, InterceptBasis, InterceptKind, InterceptSpec } from "../types";

const KIND_OPTIONS: { value: InterceptKind; label: string }[] = [
  { value: "ic", label: "IC" },
  { value: "ec", label: "EC" },
];

const BASIS_OPTIONS: { value: InterceptBasis; label: string }[] = [
  { value: "relative_percent", label: "relative (%)" },
  { value: "absolute", label: "absolute" },
];

export interface InterceptsEditorProps {
  /** Currently configured intercepts. Empty = single 50% intercept derived
   *  server-side from the curve type. */
  value: InterceptSpec[];
  onChange?: (next: InterceptSpec[]) => void;
  /** Used to seed the initial row when adding the first intercept. */
  curveType: CurveType;
  disabled?: boolean;
  /** Cap to prevent runaway UI. Default 5. */
  max?: number;
}

const MAX_INTERCEPTS_DEFAULT = 5;

function defaultKindFor(curveType: CurveType): InterceptKind {
  return curveType === "ic50" ? "ic" : "ec";
}

/**
 * Repeating-row editor for multiple "Data Calculations" intercepts
 * derived from the same Hill fit. Mirrors hit-criteria-dialog's array
 * pattern. The default 50% intercept (IC50 or EC50) is implicit on the
 * server when the list is empty — this editor only surfaces *additional*
 * intercepts, but the first row defaults to the implicit 50% intercept so
 * the user can see and adjust it.
 */
export function InterceptsEditor({
  value,
  onChange,
  curveType,
  disabled = false,
  max = MAX_INTERCEPTS_DEFAULT,
}: InterceptsEditorProps) {
  // Display mode: when value is empty, surface the implicit default so the
  // user can see what will be computed. Editing it materializes the array.
  const rows: InterceptSpec[] = value.length
    ? value
    : [
        {
          kind: defaultKindFor(curveType),
          level: 50,
          basis: "relative_percent",
        },
      ];

  const update = (next: InterceptSpec[]) => {
    if (!onChange) return;
    onChange(next);
  };

  const updateRow = (index: number, patch: Partial<InterceptSpec>) => {
    const materialized = value.length ? [...value] : [...rows];
    materialized[index] = { ...materialized[index], ...patch };
    update(materialized);
  };

  const addRow = () => {
    const materialized = value.length ? [...value] : [...rows];
    materialized.push({
      kind: defaultKindFor(curveType),
      level: 90,
      basis: "relative_percent",
    });
    update(materialized);
  };

  const removeRow = (index: number) => {
    const materialized = value.length ? [...value] : [...rows];
    materialized.splice(index, 1);
    update(materialized);
  };

  return (
    <div className="space-y-2">
      {rows.map((spec, i) => (
        <div key={i} className="flex items-end gap-2 rounded-md border bg-background p-2">
          <div className="grid gap-1 w-20">
            <Label className="text-xs">Kind</Label>
            <Select
              value={spec.kind}
              onValueChange={(v) => updateRow(i, { kind: v as InterceptKind })}
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KIND_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1 w-24">
            <Label className="text-xs">Level</Label>
            <Input
              type="number"
              value={spec.level}
              onChange={(e) =>
                updateRow(i, {
                  level: Number.isFinite(Number.parseFloat(e.target.value))
                    ? Number.parseFloat(e.target.value)
                    : spec.level,
                })
              }
              disabled={disabled}
            />
          </div>
          <div className="grid gap-1 w-44">
            <Label className="text-xs">Basis</Label>
            <Select
              value={spec.basis}
              onValueChange={(v) => updateRow(i, { basis: v as InterceptBasis })}
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BASIS_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1 flex-1">
            <Label className="text-xs">Display label</Label>
            <Input
              type="text"
              placeholder={`${spec.kind.toUpperCase()}${spec.level}`}
              value={spec.label ?? ""}
              onChange={(e) =>
                updateRow(i, {
                  label: e.target.value.trim() ? e.target.value : null,
                })
              }
              disabled={disabled}
            />
          </div>
          {!disabled && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => removeRow(i)}
              disabled={rows.length <= 1}
              title="Remove this intercept"
              className="h-9 w-9"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      ))}
      {!disabled && rows.length < max && (
        <Button type="button" variant="outline" size="sm" onClick={addRow} className="gap-1">
          <Plus className="h-3.5 w-3.5" />
          Add Data Calculation
        </Button>
      )}
    </div>
  );
}
