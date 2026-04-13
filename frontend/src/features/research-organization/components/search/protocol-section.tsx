"use client";

import { useState, useCallback } from "react";
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

type Conjunction = "and" | "or";

function defaultActivityCriterion(): ActivityCriterion {
  return { type: "activity", protocol_id: "", operator: "lt", value: 0 };
}

// ─── Single Activity Row ──────────────────────────────────────────────────────

interface ActivityRowProps {
  index: number;
  criterion: ActivityCriterion;
  conjunction: Conjunction;
  protocols: Protocol[];
  isFirst: boolean;
  onConjunctionChange: (conj: Conjunction) => void;
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
            onValueChange={(v) => onConjunctionChange(v as Conjunction)}
          >
            <SelectTrigger className="h-7 w-16 text-xs shrink-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="and">and</SelectItem>
              <SelectItem value="or">or</SelectItem>
            </SelectContent>
          </Select>
        ) : (
          <span className="w-16 shrink-0" />
        )}

        {/* "In" label */}
        <span className="text-xs text-muted-foreground shrink-0">In</span>

        {/* Scope select — always "Specific Protocol" for now */}
        <Select defaultValue="specific" disabled>
          <SelectTrigger className="h-7 w-36 text-xs shrink-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="specific">Specific Protocol</SelectItem>
          </SelectContent>
        </Select>

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

      {/* Sub-row 1: (any run) (any readout definition) — indented */}
      <div className="ml-[70px] flex items-center gap-1.5">
        {/* Run selector — placeholder only */}
        <Select defaultValue="any_run" disabled>
          <SelectTrigger className="h-7 w-28 text-xs shrink-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any_run">(any run)</SelectItem>
          </SelectContent>
        </Select>

        {/* Readout definition selector */}
        <Select
          value={criterion.readout_definition_id ?? ""}
          onValueChange={(v) => {
            if (!v) {
              onChange({ ...criterion, readout_definition_id: undefined });
            } else {
              onChange({ ...criterion, readout_definition_id: v, curve_type: undefined });
            }
          }}
        >
          <SelectTrigger className="h-7 min-w-[160px] flex-1 text-xs">
            <SelectValue placeholder="(any readout definition)" />
          </SelectTrigger>
          <SelectContent>
            {numericReadouts.map((rd) => (
              <SelectItem key={rd.id} value={rd.id}>
                {rd.name}
                {rd.unit ? ` (${rd.unit})` : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Sub-row 2: curve_type + operator + value — only visible when a protocol is selected */}
      {hasProtocol && (
        <div className="ml-[70px] flex items-center gap-1.5">
          {/* Curve type */}
          <Select
            value={criterion.curve_type ?? ""}
            onValueChange={(v) => {
              if (!v) {
                onChange({ ...criterion, curve_type: undefined });
              } else {
                onChange({ ...criterion, curve_type: v, readout_definition_id: undefined });
              }
            }}
          >
            <SelectTrigger className="h-7 w-24 text-xs shrink-0">
              <SelectValue placeholder="curve type" />
            </SelectTrigger>
            <SelectContent>
              {CURVE_TYPE_OPTIONS.map((ct) => (
                <SelectItem key={ct.value} value={ct.value}>
                  {ct.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Operator */}
          <Select
            value={criterion.operator}
            onValueChange={(v) =>
              onChange({ ...criterion, operator: v as PropertyOperator })
            }
          >
            <SelectTrigger className="h-7 w-16 text-xs shrink-0">
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
            className="h-7 w-24 text-xs"
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

interface ProtocolSectionProps {
  criteria: ActivityCriterion[];
  onChange: (criteria: ActivityCriterion[]) => void;
}

export function ProtocolSection({ criteria, onChange }: ProtocolSectionProps) {
  const { data: protocols } = useProtocols();

  // Local UI state — conjunction per row (index 0 is unused but kept for alignment)
  const [conjunctions, setConjunctions] = useState<Conjunction[]>(() =>
    criteria.map(() => "and")
  );

  const syncedConjunctions = (newLength: number): Conjunction[] => {
    const copy = [...conjunctions];
    while (copy.length < newLength) copy.push("and");
    return copy.slice(0, newLength);
  };

  const addTerm = useCallback(() => {
    const newCriteria = [...criteria, defaultActivityCriterion()];
    setConjunctions(syncedConjunctions(newCriteria.length));
    onChange(newCriteria);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [criteria, conjunctions, onChange]);

  const updateTerm = useCallback(
    (index: number, updated: ActivityCriterion) => {
      onChange(criteria.map((c, i) => (i === index ? updated : c)));
    },
    [criteria, onChange]
  );

  const removeTerm = useCallback(
    (index: number) => {
      const newCriteria = criteria.filter((_, i) => i !== index);
      const newConj = conjunctions.filter((_, i) => i !== index);
      setConjunctions(newConj);
      onChange(newCriteria);
    },
    [criteria, conjunctions, onChange]
  );

  const updateConjunction = useCallback(
    (index: number, conj: Conjunction) => {
      setConjunctions((prev) => {
        const copy = [...prev];
        copy[index] = conj;
        return copy;
      });
    },
    []
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
            conjunction={conjunctions[i] ?? "and"}
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
