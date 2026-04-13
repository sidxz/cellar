"use client";

import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { PropertyCriterion } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const PROPERTY_FIELDS = [
  { value: "molecular_weight", label: "MW" },
  { value: "logp", label: "LogP" },
  { value: "tpsa", label: "TPSA" },
  { value: "hbd", label: "HBD" },
  { value: "hba", label: "HBA" },
  { value: "rotatable_bonds", label: "RotB" },
  { value: "heavy_atom_count", label: "HAC" },
  { value: "aromatic_rings", label: "AroR" },
  { value: "ring_count", label: "Rings" },
  { value: "ro5_violations", label: "Ro5" },
];

function defaultPropertyCriterion(): PropertyCriterion {
  return {
    type: "property",
    field: "molecular_weight",
    operator: "between",
    value: undefined,
    min: undefined,
    max: undefined,
  };
}

// ─── Single compact row ─────────────────────────────────────────────────────

function PropertyRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: PropertyCriterion;
  onChange: (c: PropertyCriterion) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      {/* Property select */}
      <Select
        value={criterion.field}
        onValueChange={(v) => onChange({ ...criterion, field: v })}
      >
        <SelectTrigger className="h-7 w-20 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PROPERTY_FIELDS.map((f) => (
            <SelectItem key={f.value} value={f.value} className="text-xs">
              {f.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Min input */}
      <Input
        className="h-7 w-20 text-center text-xs"
        type="number"
        placeholder="Min"
        value={criterion.min ?? ""}
        onChange={(e) =>
          onChange({
            ...criterion,
            operator: "between",
            min: e.target.value ? Number(e.target.value) : undefined,
          })
        }
      />

      {/* Dash separator */}
      <span className="text-xs text-muted-foreground select-none">–</span>

      {/* Max input */}
      <Input
        className="h-7 w-20 text-center text-xs"
        type="number"
        placeholder="Max"
        value={criterion.max ?? ""}
        onChange={(e) =>
          onChange({
            ...criterion,
            operator: "between",
            max: e.target.value ? Number(e.target.value) : undefined,
          })
        }
      />

      {/* Remove button */}
      <button
        type="button"
        onClick={onRemove}
        className="ml-1 flex items-center justify-center rounded p-0.5 transition-colors"
        aria-label="Remove property filter"
      >
        <Trash2 className="h-3.5 w-3.5 text-muted-foreground/40 hover:text-destructive transition-colors" />
      </button>
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
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Properties
        </span>
        <button
          type="button"
          onClick={addTerm}
          className="text-xs text-primary hover:text-primary/80 transition-colors flex items-center gap-0.5"
        >
          <Plus className="h-3 w-3" />
          Add a term
        </button>
      </div>

      {/* Empty state */}
      {criteria.length === 0 && (
        <p className="text-xs italic text-muted-foreground py-1">
          No property filters added.
        </p>
      )}

      {/* Rows */}
      <div className="space-y-1.5">
        {criteria.map((c, i) => (
          <PropertyRow
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
