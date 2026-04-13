"use client";

import { useCallback } from "react";
import { Minus, Plus } from "lucide-react";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useProtocols, useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import type { Protocol } from "@/features/screening-assay/types";
import type { ActivityCriterion, PropertyOperator } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const PROPERTY_OPERATORS: { value: PropertyOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
];

const CURVE_TYPE_OPTIONS = [
  { value: "ic50", label: "IC50" },
  { value: "ec50", label: "EC50" },
  { value: "ki", label: "Ki" },
  { value: "kd", label: "Kd" },
] as const;

export type ProtocolConjunction = "and" | "or";

function defaultActivityCriterion(): ActivityCriterion {
  return { type: "activity", protocol_id: "", operator: "lt", value: 0 };
}

// ─── Single Activity Row ──────────────────────────────────────────────────────

interface ActivityRowProps {
  index: number;
  criterion: ActivityCriterion;
  conjunction: ProtocolConjunction;
  protocols: Protocol[];
  isFirst: boolean;
  onConjunctionChange: (conj: ProtocolConjunction) => void;
  onChange: (c: ActivityCriterion) => void;
  onRemove: () => void;
}

function ActivityRow({
  index,
  criterion,
  conjunction,
  protocols,
  isFirst,
  onConjunctionChange,
  onChange,
  onRemove,
}: ActivityRowProps) {
  const { data: protocol } = useProtocol(criterion.protocol_id || undefined);

  const numericReadouts = protocol?.readout_definitions?.filter(
    (rd) => rd.data_type === "numeric"
  ) ?? [];

  const hasProtocol = Boolean(criterion.protocol_id);

  return (
    <div className="space-y-1">
      {/* Main row: [remove] [and/or] In [Specific Protocol] [protocol select] */}
      <div className="flex items-center gap-1.5">
        {/* Remove button */}
        <button
          type="button"
          onClick={onRemove}
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-destructive/20 bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
          aria-label="Remove criterion"
        >
          <Minus className="h-3 w-3" />
        </button>

        {/* Conjunction (hidden for first row) */}
        {!isFirst ? (
          <Select
            value={conjunction}
            onValueChange={(v) => onConjunctionChange(v as ProtocolConjunction)}
          >
            <SelectTrigger className="h-7 w-[4.5rem] text-xs shrink-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="and">and</SelectItem>
              <SelectItem value="or">or</SelectItem>
            </SelectContent>
          </Select>
        ) : (
          <span className="w-[4.5rem] shrink-0" />
        )}

        {/* "In" label */}
        <span className="text-xs text-muted-foreground shrink-0">Protocol</span>

        {/* Protocol picker */}
        <Select
          value={criterion.protocol_id || undefined}
          onValueChange={(v) =>
            onChange({
              ...criterion,
              protocol_id: v,
              readout_definition_id: undefined,
              curve_type: undefined,
            })
          }
        >
          <SelectTrigger className="h-7 min-w-[160px] flex-1 text-xs">
            <SelectValue placeholder="Choose protocol…" />
          </SelectTrigger>
          <SelectContent>
            {protocols
              .filter((p) => p.status === "active")
              .map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>

      {/* Sub-row: activity filter — curve type + operator + value, or readout definition */}
      {hasProtocol && (
        <div className="ml-[70px] flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground shrink-0">where</span>

          {/* Curve type (IC50/EC50/Ki/Kd) — mutually exclusive with readout definition */}
          <Select
            value={criterion.readout_definition_id ? `readout:${criterion.readout_definition_id}` : (criterion.curve_type ?? "")}
            onValueChange={(v) => {
              if (!v) {
                onChange({ ...criterion, curve_type: undefined, readout_definition_id: undefined });
              } else if (v.startsWith("readout:")) {
                onChange({ ...criterion, readout_definition_id: v.slice(8), curve_type: undefined });
              } else {
                onChange({ ...criterion, curve_type: v, readout_definition_id: undefined });
              }
            }}
          >
            <SelectTrigger className="h-7 w-24 text-xs shrink-0">
              <SelectValue placeholder="IC50" />
            </SelectTrigger>
            <SelectContent>
              {CURVE_TYPE_OPTIONS.map((ct) => (
                <SelectItem key={ct.value} value={ct.value}>
                  {ct.label}
                </SelectItem>
              ))}
              {numericReadouts.length > 0 && (
                <>
                  <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/50">
                    Readouts
                  </div>
                  {numericReadouts.map((rd) => (
                    <SelectItem key={rd.id} value={`readout:${rd.id}`}>
                      {rd.name}
                      {rd.unit ? ` (${rd.unit})` : ""}
                    </SelectItem>
                  ))}
                </>
              )}
            </SelectContent>
          </Select>

          {/* Operator */}
          <Select
            value={criterion.operator}
            onValueChange={(v) =>
              onChange({ ...criterion, operator: v as PropertyOperator })
            }
          >
            <SelectTrigger className="h-7 w-14 text-xs shrink-0">
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

          {/* Value */}
          <Input
            type="number"
            className="h-7 w-20 text-xs"
            placeholder="value"
            value={criterion.value ?? ""}
            onChange={(e) =>
              onChange({
                ...criterion,
                value: e.target.value ? Number(e.target.value) : 0,
              })
            }
          />
        </div>
      )}
    </div>
  );
}

// ─── Section ────────────────────────────────────────────────────────────────

export interface ProtocolSectionProps {
  criteria: ActivityCriterion[];
  conjunctions: ProtocolConjunction[];
  onChange: (criteria: ActivityCriterion[], conjunctions: ProtocolConjunction[]) => void;
}

export function ProtocolSection({ criteria, conjunctions, onChange }: ProtocolSectionProps) {
  const { data: protocols } = useProtocols();

  const addTerm = useCallback(() => {
    onChange(
      [...criteria, defaultActivityCriterion()],
      [...conjunctions, "or"],
    );
  }, [criteria, conjunctions, onChange]);

  const updateTerm = useCallback(
    (index: number, updated: ActivityCriterion) => {
      onChange(criteria.map((c, i) => (i === index ? updated : c)), conjunctions);
    },
    [criteria, conjunctions, onChange]
  );

  const removeTerm = useCallback(
    (index: number) => {
      onChange(
        criteria.filter((_, i) => i !== index),
        conjunctions.filter((_, i) => i !== index),
      );
    },
    [criteria, conjunctions, onChange]
  );

  const updateConjunction = useCallback(
    (index: number, conj: ProtocolConjunction) => {
      onChange(criteria, conjunctions.map((c, i) => (i === index ? conj : c)));
    },
    [criteria, conjunctions, onChange]
  );

  return (
    <div className="space-y-2">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Protocols
        </span>
        <button
          type="button"
          onClick={addTerm}
          className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors"
        >
          <Plus className="h-3 w-3" />
          Add a term
        </button>
      </div>

      {/* Empty state */}
      {criteria.length === 0 && (
        <p className="text-xs italic text-muted-foreground/50 py-1">
          No protocol filters. Click &ldquo;+ Add a term&rdquo; to filter by assay activity.
        </p>
      )}

      {/* Criteria rows */}
      <div className="space-y-3">
        {criteria.map((c, i) => (
          <ActivityRow
            key={`activity-${i}`}
            index={i}
            criterion={c}
            conjunction={conjunctions[i] ?? "or"}
            protocols={protocols ?? []}
            isFirst={i === 0}
            onConjunctionChange={(conj) => updateConjunction(i, conj)}
            onChange={(updated) => updateTerm(i, updated)}
            onRemove={() => removeTerm(i)}
          />
        ))}
      </div>
    </div>
  );
}
