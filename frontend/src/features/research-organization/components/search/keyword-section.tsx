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
import type { TextCriterion, TextOperator } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const TEXT_FIELDS = [
  { value: "any", label: "Any Field" },
  { value: "name", label: "Name" },
  { value: "registration_number", label: "Registration Number" },
  { value: "molecular_formula", label: "Molecular Formula" },
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
    <div className="flex items-end gap-2">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Field</Label>
        <Select
          value={criterion.field}
          onValueChange={(v) => onChange({ ...criterion, field: v })}
        >
          <SelectTrigger className="h-9">
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

      <div className="w-32">
        <Label className="text-xs text-muted-foreground">Operator</Label>
        <Select
          value={criterion.operator}
          onValueChange={(v) => onChange({ ...criterion, operator: v as TextOperator })}
        >
          <SelectTrigger className="h-9">
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
        <Label className="text-xs text-muted-foreground">Value</Label>
        <Input
          className="h-9"
          placeholder="Search text..."
          value={criterion.value}
          onChange={(e) => onChange({ ...criterion, value: e.target.value })}
        />
      </div>

      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
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
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Keywords</Label>
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
          No keyword filters. Click "Add a term" to search by name, registration number, or formula.
        </p>
      )}

      <div className="space-y-2">
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
