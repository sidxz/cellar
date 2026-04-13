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
import { useProtocols, useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import type { ActivityCriterion, PropertyOperator } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const PROPERTY_OPERATORS: { value: PropertyOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
];

const CURVE_TYPE_OPTIONS = [
  { value: "ic50", label: "IC50" },
  { value: "ec50", label: "EC50" },
  { value: "ki", label: "Ki" },
  { value: "kd", label: "Kd" },
] as const;

function defaultActivityCriterion(): ActivityCriterion {
  return { type: "activity", protocol_id: "", operator: "lt", value: 0 };
}

// ─── Single activity term ───────────────────────────────────────────────────

function ActivityTerm({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: ActivityCriterion;
  onChange: (c: ActivityCriterion) => void;
  onRemove: () => void;
}) {
  const { data: protocols } = useProtocols();
  const { data: protocol } = useProtocol(criterion.protocol_id || undefined);

  return (
    <div className="flex items-end gap-2 flex-wrap">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Protocol</Label>
        <Select
          value={criterion.protocol_id || undefined}
          onValueChange={(v) =>
            onChange({ ...criterion, protocol_id: v, readout_definition_id: undefined, curve_type: undefined })
          }
        >
          <SelectTrigger className="h-9">
            <SelectValue placeholder="Select protocol..." />
          </SelectTrigger>
          <SelectContent>
            {protocols
              ?.filter((p) => p.status === "active")
              .map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>

      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Readout / Curve</Label>
        <Select
          value={criterion.readout_definition_id ?? criterion.curve_type ?? undefined}
          onValueChange={(v) => {
            const isCurve = CURVE_TYPE_OPTIONS.some((ct) => ct.value === v);
            if (isCurve) {
              onChange({ ...criterion, curve_type: v, readout_definition_id: undefined });
            } else {
              onChange({ ...criterion, readout_definition_id: v, curve_type: undefined });
            }
          }}
        >
          <SelectTrigger className="h-9">
            <SelectValue placeholder="Select..." />
          </SelectTrigger>
          <SelectContent>
            {protocol?.readout_definitions
              ?.filter((rd) => rd.data_type === "numeric")
              .map((rd) => (
                <SelectItem key={rd.id} value={rd.id}>
                  {rd.name}{rd.unit ? ` (${rd.unit})` : ""}
                </SelectItem>
              ))}
            {CURVE_TYPE_OPTIONS.map((ct) => (
              <SelectItem key={ct.value} value={ct.value}>
                {ct.label} (curve)
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Operator</Label>
        <Select
          value={criterion.operator}
          onValueChange={(v) => onChange({ ...criterion, operator: v as PropertyOperator })}
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

      <div className="w-28">
        <Label className="text-xs text-muted-foreground">Value</Label>
        <Input
          className="h-9"
          type="number"
          placeholder="Value"
          value={criterion.value ?? ""}
          onChange={(e) =>
            onChange({ ...criterion, value: e.target.value ? Number(e.target.value) : 0 })
          }
        />
      </div>

      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

// ─── Section ────────────────────────────────────────────────────────────────

interface ProtocolSectionProps {
  criteria: ActivityCriterion[];
  onChange: (criteria: ActivityCriterion[]) => void;
}

export function ProtocolSection({ criteria, onChange }: ProtocolSectionProps) {
  function addTerm() {
    onChange([...criteria, defaultActivityCriterion()]);
  }

  function updateTerm(index: number, updated: ActivityCriterion) {
    onChange(criteria.map((c, i) => (i === index ? updated : c)));
  }

  function removeTerm(index: number) {
    onChange(criteria.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Protocol Activity</Label>
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
          No protocol filters. Click "Add a term" to filter by assay activity.
        </p>
      )}

      <div className="space-y-2">
        {criteria.map((c, i) => (
          <ActivityTerm
            key={`activity-${i}`}
            criterion={c}
            onChange={(updated) => updateTerm(i, updated)}
            onRemove={() => removeTerm(i)}
          />
        ))}
      </div>
    </div>
  );
}
