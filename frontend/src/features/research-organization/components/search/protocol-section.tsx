"use client";

import { useCallback, useState } from "react";
import { Check, ChevronsUpDown, Minus, Plus } from "lucide-react";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/shared/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { cn } from "@/shared/lib/utils";
import { useProtocols, useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import type { Protocol } from "@/features/screening-assay/types";
import { CURVE_TYPE_LABELS } from "@/features/screening-assay/types";
import type { ActivityCriterion, PropertyOperator } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const PROPERTY_OPERATORS: { value: PropertyOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
];

/** Extract available curve types from a protocol's readout definitions. */
function getProtocolCurveTypes(protocol: Protocol | undefined): { value: string; label: string }[] {
  if (!protocol?.readout_definitions) return [];
  const seen = new Set<string>();
  const options: { value: string; label: string }[] = [];
  for (const rd of protocol.readout_definitions) {
    const ct = rd.dose_response_config?.curve_type;
    if (ct && !seen.has(ct)) {
      seen.add(ct);
      options.push({
        value: ct,
        label: CURVE_TYPE_LABELS[ct] ?? ct.toUpperCase(),
      });
    }
  }
  return options;
}

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
  const [protocolOpen, setProtocolOpen] = useState(false);
  const { data: protocol } = useProtocol(criterion.protocol_id || undefined);

  const numericReadouts = protocol?.readout_definitions?.filter(
    (rd) => rd.data_type === "numeric" && !rd.dose_response_config
  ) ?? [];

  const curveTypeOptions = getProtocolCurveTypes(protocol);
  const hasProtocol = Boolean(criterion.protocol_id);
  const protocolInvalid = !hasProtocol;
  const selectionInvalid =
    hasProtocol && !criterion.curve_type && !criterion.readout_definition_id;

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
            <SelectTrigger className="h-8 w-[4.5rem] text-sm shrink-0">
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
        <span className="text-sm text-muted-foreground shrink-0">Protocol</span>

        {/* Protocol picker (searchable) */}
        <Popover open={protocolOpen} onOpenChange={setProtocolOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                "flex h-8 min-w-[160px] flex-1 items-center justify-between rounded-md border border-input bg-transparent px-2 text-sm shadow-xs",
                !criterion.protocol_id && "text-muted-foreground",
                protocolInvalid && "border-destructive",
              )}
              aria-invalid={protocolInvalid}
            >
              <span className="truncate">
                {criterion.protocol_id
                  ? protocols.find((p) => p.id === criterion.protocol_id)?.name ?? "Unknown"
                  : "Choose protocol…"}
              </span>
              <ChevronsUpDown className="ml-1 h-3 w-3 shrink-0 opacity-50" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-0" align="start">
            <Command>
              <CommandInput placeholder="Search protocols…" className="h-8 text-sm" />
              <CommandList>
                <CommandEmpty>No protocols found.</CommandEmpty>
                <CommandGroup>
                  {protocols
                    .filter((p) => p.status === "active")
                    .map((p) => (
                      <CommandItem
                        key={p.id}
                        value={p.name}
                        onSelect={() => {
                          onChange({
                            ...criterion,
                            protocol_id: p.id,
                            readout_definition_id: undefined,
                            curve_type: undefined,
                          });
                          setProtocolOpen(false);
                        }}
                        className="text-sm"
                      >
                        <Check
                          className={cn(
                            "mr-1.5 h-3 w-3",
                            criterion.protocol_id === p.id ? "opacity-100" : "opacity-0",
                          )}
                        />
                        {p.name}
                      </CommandItem>
                    ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {/* Sub-row: activity filter — curve type + operator + value, or readout definition */}
      {hasProtocol && (
        <div className="ml-[70px] flex items-center gap-1.5 flex-wrap">
          <span className="text-sm text-muted-foreground shrink-0">where</span>

          {/* Curve type / readout — derived from protocol's readout definitions */}
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
            <SelectTrigger
              className={cn(
                "h-8 w-28 text-sm shrink-0",
                selectionInvalid && "border-destructive",
              )}
              aria-invalid={selectionInvalid}
            >
              <SelectValue placeholder="Select…" />
            </SelectTrigger>
            <SelectContent>
              {curveTypeOptions.length > 0 && curveTypeOptions.map((ct) => (
                <SelectItem key={ct.value} value={ct.value}>
                  {ct.label}
                </SelectItem>
              ))}
              {numericReadouts.length > 0 && (
                <>
                  {curveTypeOptions.length > 0 && (
                    <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/50">
                      Readouts
                    </div>
                  )}
                  {numericReadouts.map((rd) => (
                    <SelectItem key={rd.id} value={`readout:${rd.id}`}>
                      {rd.name}
                      {rd.unit ? ` (${rd.unit})` : ""}
                    </SelectItem>
                  ))}
                </>
              )}
              {curveTypeOptions.length === 0 && numericReadouts.length === 0 && (
                <div className="px-2 py-3 text-sm text-muted-foreground text-center">
                  No curve types or readouts configured
                </div>
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
            <SelectTrigger className="h-8 w-14 text-sm shrink-0">
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
            className="h-8 w-20 text-sm"
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

      {(protocolInvalid || selectionInvalid) && (
        <p className="ml-[70px] text-xs text-destructive">
          {protocolInvalid
            ? "Choose a protocol."
            : "Choose a curve type or readout."}
        </p>
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
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Protocols
        </span>
        <button
          type="button"
          onClick={addTerm}
          className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors"
        >
          <Plus className="h-3 w-3" />
          Add
        </button>
      </div>

      {/* Empty state */}
      {criteria.length === 0 && (
        <p className="text-sm italic text-muted-foreground/50 py-1">
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
