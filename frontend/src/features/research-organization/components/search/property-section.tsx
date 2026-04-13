"use client";

import { Plus, Trash2 } from "lucide-react";
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
import type { PropertyCriterion, PropertyOperator } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const PROPERTY_FIELDS = [
  { value: "molecular_weight", label: "Molecular Weight" },
  { value: "logp", label: "LogP" },
  { value: "tpsa", label: "TPSA" },
  { value: "hbd", label: "HBD" },
  { value: "hba", label: "HBA" },
  { value: "rotatable_bonds", label: "Rotatable Bonds" },
  { value: "heavy_atom_count", label: "Heavy Atom Count" },
  { value: "aromatic_rings", label: "Aromatic Rings" },
  { value: "ring_count", label: "Ring Count" },
  { value: "ro5_violations", label: "Ro5 Violations" },
] as const;

const PROPERTY_OPERATORS: { value: PropertyOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
  { value: "between", label: "Between" },
];

function defaultPropertyCriterion(): PropertyCriterion {
  return { type: "property", field: "molecular_weight", operator: "gte", value: undefined, min: undefined, max: undefined };
}

// ─── Single property term ───────────────────────────────────────────────────

function PropertyTerm({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: PropertyCriterion;
  onChange: (c: PropertyCriterion) => void;
  onRemove: () => void;
}) {
  const isBetween = criterion.operator === "between";

  return (
    <div className="flex items-end gap-2">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Property</Label>
        <Select
          value={criterion.field}
          onValueChange={(v) => onChange({ ...criterion, field: v })}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROPERTY_FIELDS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="w-28">
        <Label className="text-xs text-muted-foreground">Operator</Label>
        <Select
          value={criterion.operator}
          onValueChange={(v) =>
            onChange({
              ...criterion,
              operator: v as PropertyOperator,
              ...(v === "between"
                ? { value: undefined, min: criterion.min, max: criterion.max }
                : { min: undefined, max: undefined, value: criterion.value }),
            })
          }
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROPERTY_OPERATORS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isBetween ? (
        <>
          <div className="w-24">
            <Label className="text-xs text-muted-foreground">Min</Label>
            <Input
              className="h-9"
              type="number"
              placeholder="Min"
              value={criterion.min ?? ""}
              onChange={(e) =>
                onChange({ ...criterion, min: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </div>
          <div className="w-24">
            <Label className="text-xs text-muted-foreground">Max</Label>
            <Input
              className="h-9"
              type="number"
              placeholder="Max"
              value={criterion.max ?? ""}
              onChange={(e) =>
                onChange({ ...criterion, max: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </div>
        </>
      ) : (
        <div className="w-28">
          <Label className="text-xs text-muted-foreground">Value</Label>
          <Input
            className="h-9"
            type="number"
            placeholder="Value"
            value={criterion.value ?? ""}
            onChange={(e) =>
              onChange({ ...criterion, value: e.target.value ? Number(e.target.value) : undefined })
            }
          />
        </div>
      )}

      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

// ─── Section ────────────────────────────────────────────────────────────────

interface PropertySectionProps {
  criteria: PropertyCriterion[];
  onChange: (criteria: PropertyCriterion[]) => void;
}

export function PropertySection({ criteria, onChange }: PropertySectionProps) {
  function addTerm() {
    onChange([...criteria, defaultPropertyCriterion()]);
  }

  function updateTerm(index: number, updated: PropertyCriterion) {
    onChange(criteria.map((c, i) => (i === index ? updated : c)));
  }

  function removeTerm(index: number) {
    onChange(criteria.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Properties</Label>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={addTerm}
        >
          <Plus className="mr-1 h-3 w-3" />
          Add a term
        </Button>
      </div>

      {criteria.length === 0 && (
        <p className="text-xs text-muted-foreground py-1">
          No property filters. Click "Add a term" to filter by molecular properties.
        </p>
      )}

      <div className="space-y-2">
        {criteria.map((c, i) => (
          <PropertyTerm
            key={`property-${i}`}
            criterion={c}
            onChange={(updated) => updateTerm(i, updated)}
            onRemove={() => removeTerm(i)}
          />
        ))}
      </div>
    </div>
  );
}
