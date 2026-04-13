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
import type { TextCriterion, TextOperator } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const TEXT_FIELDS = [
  { value: "any", label: "Any" },
  { value: "name", label: "Name" },
  { value: "registration_number", label: "Reg Number" },
  { value: "molecular_formula", label: "Formula" },
  { value: "inchi_key", label: "InChI Key" },
] as const;

const TEXT_OPERATORS: { value: TextOperator; label: string }[] = [
  { value: "contains", label: "Contains" },
  { value: "equals", label: "Equals" },
  { value: "starts_with", label: "Starts With" },
];

function defaultTextCriterion(): TextCriterion {
  return { type: "text", field: "name", operator: "contains", value: "" };
}

// ─── Single keyword term ────────────────────────────────────────────────────

function KeywordTerm({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: TextCriterion;
  onChange: (c: TextCriterion) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-2 mb-1.5">
      <div className="w-28">
        <Select
          value={criterion.field}
          onValueChange={(v) => onChange({ ...criterion, field: v })}
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TEXT_FIELDS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="w-28">
        <Select
          value={criterion.operator}
          onValueChange={(v) => onChange({ ...criterion, operator: v as TextOperator })}
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TEXT_OPERATORS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1">
        <Input
          className="h-7 text-xs"
          placeholder="Search text..."
          value={criterion.value}
          onChange={(e) => onChange({ ...criterion, value: e.target.value })}
        />
      </div>

      <button
        type="button"
        onClick={onRemove}
        className="text-muted-foreground/40 hover:text-destructive"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ─── Section ────────────────────────────────────────────────────────────────

interface KeywordSectionProps {
  criteria: TextCriterion[];
  onChange: (criteria: TextCriterion[]) => void;
}

export function KeywordSection({ criteria, onChange }: KeywordSectionProps) {
  function addTerm() {
    onChange([...criteria, defaultTextCriterion()]);
  }

  function updateTerm(index: number, updated: TextCriterion) {
    onChange(criteria.map((c, i) => (i === index ? updated : c)));
  }

  function removeTerm(index: number) {
    onChange(criteria.filter((_, i) => i !== index));
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Keywords
        </span>
        <button
          type="button"
          onClick={addTerm}
          className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80"
        >
          <Plus className="h-3 w-3" /> Add a term
        </button>
      </div>

      {criteria.length === 0 && (
        <p className="text-xs italic text-muted-foreground/50">
          No keyword filters.
        </p>
      )}

      <div>
        {criteria.map((c, i) => (
          <KeywordTerm
            key={`keyword-${i}`}
            criterion={c}
            onChange={(updated) => updateTerm(i, updated)}
            onRemove={() => removeTerm(i)}
          />
        ))}
      </div>
    </div>
  );
}
