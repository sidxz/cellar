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
import { Trash2 } from "lucide-react";
import {
  PROPERTY_FIELDS,
  PROPERTY_OPERATORS,
  REF_TYPE_OPTIONS,
  TEXT_FIELDS,
  TEXT_OPERATORS,
} from "../../lib/search-query-config";
import type {
  KeywordListCriterion,
  PropertyCriterion,
  PropertyOperator,
  RefType,
  RunDateCriterion,
  TextCriterion,
  TextOperator,
} from "../../types";

export function TextCriterionRow({
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
        <Select value={criterion.field} onValueChange={(v) => onChange({ ...criterion, field: v })}>
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

export function PropertyCriterionRow({
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
        <Select value={criterion.field} onValueChange={(v) => onChange({ ...criterion, field: v })}>
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
              // Reset value fields when switching to/from between
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

export function RunDateCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: RunDateCriterion;
  onChange: (c: RunDateCriterion) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-end gap-2">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">From</Label>
        <Input
          className="h-9"
          type="date"
          value={criterion.date_from ?? ""}
          onChange={(e) => onChange({ ...criterion, date_from: e.target.value || undefined })}
        />
      </div>
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">To</Label>
        <Input
          className="h-9"
          type="date"
          value={criterion.date_to ?? ""}
          onChange={(e) => onChange({ ...criterion, date_to: e.target.value || undefined })}
        />
      </div>
      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

export function KeywordListCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: KeywordListCriterion;
  onChange: (c: KeywordListCriterion) => void;
  onRemove: () => void;
}) {
  const rawText = criterion.values.join("\n");

  function handleTextChange(text: string) {
    const parsed = text
      .split(/[,\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    onChange({ ...criterion, values: parsed });
  }

  return (
    <div className="flex items-start gap-2">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Identifier Type</Label>
        <Select
          value={criterion.ref_type}
          onValueChange={(v) => onChange({ ...criterion, ref_type: v as RefType })}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {REF_TYPE_OPTIONS.map((r) => (
              <SelectItem key={r.value} value={r.value}>
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex-1">
        <Label className="text-xs text-muted-foreground">
          Values ({criterion.values.length} identifier{criterion.values.length !== 1 ? "s" : ""})
        </Label>
        <textarea
          className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring h-20 font-mono text-xs resize-y"
          placeholder="One per line, or comma-separated..."
          value={rawText}
          onChange={(e) => handleTextChange(e.target.value)}
        />
      </div>
      <Button variant="ghost" size="icon" className="mt-5 h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}
