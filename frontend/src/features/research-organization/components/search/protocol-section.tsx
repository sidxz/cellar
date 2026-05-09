"use client";

import { useCallback, useMemo, useState } from "react";
import { Check, ChevronsUpDown, Minus, Plus } from "lucide-react";
import { Input } from "@/shared/components/ui/input";
import { Checkbox } from "@/shared/components/ui/checkbox";
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
  CommandSeparator,
} from "@/shared/components/ui/command";
import { cn } from "@/shared/lib/utils";
import {
  useProtocol,
  useProtocolSummaries,
  type ProtocolSummary,
} from "@/features/screening-assay/hooks/use-protocols";
import { CURVE_TYPE_LABELS } from "@/features/screening-assay/types";
import type {
  ActivityCriterion,
  ActivityWhereCondition,
  PropertyOperator,
  RunScope,
} from "../../types";
import { RunScopePicker } from "./run-scope-picker";

// ─── Constants ──────────────────────────────────────────────────────────────

const PROPERTY_OPERATORS: { value: PropertyOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "between", label: "between" },
];

// ─── Protocol picker helpers ────────────────────────────────────────────────

/** Status dot — green when active, amber when draft, grey otherwise (archived/retired). */
function protocolStatusColor(status: string): string {
  if (status === "active") return "bg-emerald-500";
  if (status === "draft") return "bg-amber-500";
  return "bg-muted-foreground/40";
}

/** Format ISO date as a relative-ish suffix ("today", "3d ago", "Apr 20").
 *  Keeps the picker scannable without taking too much horizontal space. */
function formatLastRun(iso: string | null): string {
  if (!iso) return "no runs";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.floor((today.getTime() - d.getTime()) / 86400000);
  if (diffDays <= 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 14) return `${diffDays}d ago`;
  if (diffDays < 60) return `${Math.floor(diffDays / 7)}w ago`;
  // Older — show calendar date.
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: today.getFullYear() === d.getFullYear() ? undefined : "numeric" });
}

/** How many recently-used protocols to pin at the top of the list. */
const RECENTS_LIMIT = 5;
const RECENTS_MIN_TOTAL = 8; // only pin a recents group if the list is at least this long

/** Extract available curve types from a protocol's readout definitions. */
function getProtocolCurveTypes(protocol: import("@/features/screening-assay/types").Protocol | undefined): { value: string; label: string }[] {
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
  return { type: "activity", protocol_id: "", where: [] };
}

function defaultWhereCondition(): ActivityWhereCondition {
  return { operator: "lt", value: 0 };
}

/** Read where[] from a criterion, normalizing the legacy inline shape into
 *  a single-element list so the UI only has to think in one model. */
function readWhere(c: ActivityCriterion): ActivityWhereCondition[] {
  if (Array.isArray(c.where)) return c.where;
  if (c.curve_type || c.readout_definition_id) {
    const cond: ActivityWhereCondition = {
      operator: c.operator ?? "lt",
    };
    if (c.curve_type) cond.curve_type = c.curve_type;
    if (c.readout_definition_id) cond.readout_definition_id = c.readout_definition_id;
    if (c.value !== undefined) cond.value = c.value;
    return [cond];
  }
  return [];
}

/** Strip empty / incomplete where rows before sending to the backend. */
function pruneWhere(where: ActivityWhereCondition[]): ActivityWhereCondition[] {
  return where.filter((w) => {
    if (!w.curve_type && !w.readout_definition_id) return false;
    if (w.operator === "between") {
      return w.min !== undefined && w.max !== undefined;
    }
    return w.value !== undefined && !Number.isNaN(w.value);
  });
}

// ─── Protocol picker row ────────────────────────────────────────────────────

interface ProtocolRowProps {
  protocol: ProtocolSummary;
  selected: boolean;
  onPick: () => void;
}

function ProtocolRow({ protocol, selected, onPick }: ProtocolRowProps) {
  const isArchived = protocol.status === "retired" || protocol.status === "archived";
  // Build a haystack so Command's filter can hit name + target + status.
  const value = [
    protocol.id,
    protocol.name,
    protocol.target_name ?? "",
    protocol.status,
  ]
    .join(" ")
    .toLowerCase();

  return (
    <CommandItem value={value} onSelect={onPick} className="text-sm py-1.5">
      <div className="flex w-full min-w-0 items-start gap-2">
        <Check
          className={cn(
            "mt-1 h-3 w-3 shrink-0",
            selected ? "opacity-100" : "opacity-0",
          )}
        />
        <span
          className={cn(
            "mt-1.5 h-2 w-2 rounded-full shrink-0",
            protocolStatusColor(protocol.status),
          )}
          aria-hidden
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                "line-clamp-2 text-sm",
                isArchived && "text-muted-foreground italic",
              )}
            >
              {protocol.name}
            </span>
            {isArchived && (
              <span className="rounded-full border border-muted-foreground/20 px-1.5 text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">
                {protocol.status}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {protocol.target_name && (
              <span className="rounded-sm bg-muted px-1.5 py-0.5 text-foreground/70">
                {protocol.target_name}
              </span>
            )}
            <span className="tabular-nums">
              {protocol.run_count} run{protocol.run_count === 1 ? "" : "s"}
            </span>
            <span aria-hidden>·</span>
            <span>last {formatLastRun(protocol.last_run_date)}</span>
          </div>
        </div>
      </div>
    </CommandItem>
  );
}

// ─── Activity where rows (multiple ANDed conditions) ───────────────────────

interface CurveTypeOption {
  value: string;
  label: string;
}

interface NumericReadout {
  id: string;
  name: string;
  unit?: string | null;
}

interface WhereListProps {
  where: ActivityWhereCondition[];
  curveTypeOptions: CurveTypeOption[];
  numericReadouts: NumericReadout[];
  onChange: (next: ActivityWhereCondition[]) => void;
}

function WhereList({
  where,
  curveTypeOptions,
  numericReadouts,
  onChange,
}: WhereListProps) {
  function update(i: number, next: ActivityWhereCondition) {
    onChange(where.map((w, idx) => (idx === i ? next : w)));
  }
  function remove(i: number) {
    onChange(where.filter((_, idx) => idx !== i));
  }
  function add() {
    onChange([...where, defaultWhereCondition()]);
  }

  return (
    <div className="space-y-1">
      {where.length === 0 ? (
        <button
          type="button"
          onClick={add}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <Plus className="h-3 w-3" />
          add filter (optional)
        </button>
      ) : (
        <>
          {where.map((cond, i) => (
            <WhereRow
              key={i}
              cond={cond}
              isFirst={i === 0}
              curveTypeOptions={curveTypeOptions}
              numericReadouts={numericReadouts}
              onChange={(next) => update(i, next)}
              onRemove={() => remove(i)}
            />
          ))}
          <button
            type="button"
            onClick={add}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Plus className="h-3 w-3" />
            and
          </button>
        </>
      )}
    </div>
  );
}

interface WhereRowProps {
  cond: ActivityWhereCondition;
  isFirst: boolean;
  curveTypeOptions: CurveTypeOption[];
  numericReadouts: NumericReadout[];
  onChange: (next: ActivityWhereCondition) => void;
  onRemove: () => void;
}

function WhereRow({
  cond,
  isFirst,
  curveTypeOptions,
  numericReadouts,
  onChange,
  onRemove,
}: WhereRowProps) {
  const fieldValue = cond.readout_definition_id
    ? `readout:${cond.readout_definition_id}`
    : cond.curve_type ?? "";
  const isBetween = cond.operator === "between";

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {/* Conjunction label — first row says "where", subsequent rows say "and" */}
      <span className="text-sm text-muted-foreground shrink-0 w-10">
        {isFirst ? "where" : "and"}
      </span>

      {/* Field picker (curve_type or readout_definition_id) */}
      <Select
        value={fieldValue}
        onValueChange={(v) => {
          if (!v) {
            onChange({ ...cond, curve_type: undefined, readout_definition_id: undefined });
          } else if (v.startsWith("readout:")) {
            onChange({
              ...cond,
              readout_definition_id: v.slice(8),
              curve_type: undefined,
            });
          } else {
            onChange({
              ...cond,
              curve_type: v,
              readout_definition_id: undefined,
            });
          }
        }}
      >
        <SelectTrigger className="h-8 w-32 text-sm shrink-0">
          <SelectValue placeholder="select…" />
        </SelectTrigger>
        <SelectContent>
          {curveTypeOptions.length > 0 &&
            curveTypeOptions.map((ct) => (
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
        value={cond.operator}
        onValueChange={(v) => {
          const nextOp = v as PropertyOperator;
          // Switch between value <-> min/max so stale fields don't go to backend.
          if (nextOp === "between") {
            onChange({
              ...cond,
              operator: nextOp,
              value: undefined,
              min: cond.min ?? cond.value ?? undefined,
              max: cond.max ?? undefined,
            });
          } else {
            onChange({
              ...cond,
              operator: nextOp,
              value: cond.value ?? cond.min ?? undefined,
              min: undefined,
              max: undefined,
            });
          }
        }}
      >
        <SelectTrigger className="h-8 w-24 text-sm shrink-0">
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

      {/* Value (or min/max for between) */}
      {isBetween ? (
        <>
          <Input
            type="number"
            className="h-8 w-20 text-sm"
            placeholder="min"
            value={cond.min ?? ""}
            onChange={(e) =>
              onChange({
                ...cond,
                min: e.target.value === "" ? undefined : Number(e.target.value),
              })
            }
          />
          <span className="text-xs text-muted-foreground">and</span>
          <Input
            type="number"
            className="h-8 w-20 text-sm"
            placeholder="max"
            value={cond.max ?? ""}
            onChange={(e) =>
              onChange({
                ...cond,
                max: e.target.value === "" ? undefined : Number(e.target.value),
              })
            }
          />
        </>
      ) : (
        <Input
          type="number"
          className="h-8 w-20 text-sm"
          placeholder="value"
          value={cond.value ?? ""}
          onChange={(e) =>
            onChange({
              ...cond,
              value: e.target.value === "" ? undefined : Number(e.target.value),
            })
          }
        />
      )}

      {/* Remove this condition */}
      <button
        type="button"
        onClick={onRemove}
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-destructive/20 bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
        aria-label="Remove condition"
      >
        <Minus className="h-3 w-3" />
      </button>
    </div>
  );
}

// ─── Single Activity Row ──────────────────────────────────────────────────────

interface ActivityRowProps {
  index: number;
  criterion: ActivityCriterion;
  conjunction: ProtocolConjunction;
  protocols: ProtocolSummary[];
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
  const [showArchived, setShowArchived] = useState(false);
  const { data: protocol } = useProtocol(criterion.protocol_id || undefined);

  const visibleProtocols = useMemo(
    () =>
      showArchived
        ? protocols
        : protocols.filter((p) => p.status !== "retired" && p.status !== "archived"),
    [protocols, showArchived]
  );

  // Pin a "Recently used" group at the top once the list is large enough.
  // Server returns rows already sorted by last_run_date desc; use that order.
  const { recents, others, hasRecents } = useMemo(() => {
    const withRuns = visibleProtocols.filter((p) => p.last_run_date !== null);
    const shouldPin =
      visibleProtocols.length >= RECENTS_MIN_TOTAL && withRuns.length >= 2;
    if (!shouldPin) {
      return { recents: [] as ProtocolSummary[], others: visibleProtocols, hasRecents: false };
    }
    const top = withRuns.slice(0, RECENTS_LIMIT);
    const topIds = new Set(top.map((p) => p.id));
    return {
      recents: top,
      others: visibleProtocols.filter((p) => !topIds.has(p.id)),
      hasRecents: true,
    };
  }, [visibleProtocols]);

  const selectedProtocol = protocols.find((p) => p.id === criterion.protocol_id);

  const numericReadouts = protocol?.readout_definitions?.filter(
    (rd) => rd.data_type === "numeric" && !rd.dose_response_config
  ) ?? [];

  const curveTypeOptions = getProtocolCurveTypes(protocol);
  const hasProtocol = Boolean(criterion.protocol_id);
  const protocolInvalid = !hasProtocol;
  // The where-clause is optional: a protocol-only criterion is a valid
  // "any compound screened in this protocol/scope" presence filter.
  const whereList = readWhere(criterion);

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

        {/* Protocol picker (rich rows: status dot + name + target + run stats) */}
        <Popover open={protocolOpen} onOpenChange={setProtocolOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                "flex h-8 min-w-0 flex-1 items-center justify-between gap-1.5 rounded-md border border-input bg-transparent px-2 text-sm shadow-xs",
                !criterion.protocol_id && "text-muted-foreground",
                protocolInvalid && "border-destructive",
              )}
              aria-invalid={protocolInvalid}
            >
              {selectedProtocol ? (
                <span className="flex min-w-0 items-center gap-1.5">
                  <span
                    className={cn(
                      "h-2 w-2 rounded-full shrink-0",
                      protocolStatusColor(selectedProtocol.status),
                    )}
                    aria-hidden
                  />
                  <span className="truncate">{selectedProtocol.name}</span>
                </span>
              ) : (
                <span className="truncate">Choose protocol…</span>
              )}
              <ChevronsUpDown className="h-3 w-3 shrink-0 opacity-50" />
            </button>
          </PopoverTrigger>
          <PopoverContent
            className="p-0 w-[28rem] max-w-[calc(100vw-2rem)]"
            align="start"
          >
            <Command
              filter={(value, search) => {
                // Match by name + target + status; case-insensitive substring.
                const haystack = value.toLowerCase();
                const needle = search.toLowerCase().trim();
                if (!needle) return 1;
                return haystack.includes(needle) ? 1 : 0;
              }}
            >
              <CommandInput
                placeholder="Search protocols, targets…"
                className="h-8 text-sm"
              />
              <CommandList className="max-h-96">
                <CommandEmpty>No protocols found.</CommandEmpty>

                {hasRecents && (
                  <>
                    <CommandGroup heading="Recently used">
                      {recents.map((p) => (
                        <ProtocolRow
                          key={p.id}
                          protocol={p}
                          selected={criterion.protocol_id === p.id}
                          onPick={() => {
                            onChange({
                              ...criterion,
                              protocol_id: p.id,
                              readout_definition_id: undefined,
                              curve_type: undefined,
                            });
                            setProtocolOpen(false);
                          }}
                        />
                      ))}
                    </CommandGroup>
                    <CommandSeparator />
                  </>
                )}

                <CommandGroup heading={hasRecents ? "All protocols" : undefined}>
                  {others.map((p) => (
                    <ProtocolRow
                      key={p.id}
                      protocol={p}
                      selected={criterion.protocol_id === p.id}
                      onPick={() => {
                        onChange({
                          ...criterion,
                          protocol_id: p.id,
                          readout_definition_id: undefined,
                          curve_type: undefined,
                        });
                        setProtocolOpen(false);
                      }}
                    />
                  ))}
                </CommandGroup>

                <div className="flex items-center gap-2 border-t border-border px-3 py-2 text-xs text-muted-foreground">
                  <Checkbox
                    id={`protocol-show-archived-${index}`}
                    checked={showArchived}
                    onCheckedChange={(v) => setShowArchived(v === true)}
                    className="h-3.5 w-3.5"
                  />
                  <label
                    htmlFor={`protocol-show-archived-${index}`}
                    className="cursor-pointer select-none"
                  >
                    Show archived / retired
                  </label>
                </div>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {/* Sub-rows: runs (default "any") then optional where-clause. */}
      {hasProtocol && (
        <div className="ml-[70px] space-y-1.5">
          {/* runs — always visible, defaults to "Any run" when omitted */}
          <RunScopePicker
            protocolId={criterion.protocol_id}
            value={criterion.run_scope}
            onChange={(next: RunScope | undefined) =>
              onChange({ ...criterion, run_scope: next })
            }
          />

          {/* where — optional, multiple. Empty list ⇒ presence filter
              ("compounds screened in this protocol/scope"). */}
          <WhereList
            where={whereList}
            curveTypeOptions={curveTypeOptions}
            numericReadouts={numericReadouts}
            onChange={(next) => {
              // Drop legacy inline single-where fields once we manage where[].
              onChange({
                ...criterion,
                where: next,
                curve_type: undefined,
                readout_definition_id: undefined,
                operator: undefined,
                value: undefined,
              });
            }}
          />
        </div>
      )}

      {protocolInvalid && (
        <p className="ml-[70px] text-xs text-destructive">
          Choose a protocol.
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
  const { data: protocols } = useProtocolSummaries();

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
