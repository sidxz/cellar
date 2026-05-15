"use client";

import {
  type ProtocolSummary,
  useProtocol,
  useProtocolSummaries,
} from "@/features/screening-assay/hooks/use-protocols";
import { CURVE_CLASS_LABELS } from "@/features/screening-assay/types";
import { Badge } from "@/shared/components/ui/badge";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/shared/components/ui/command";
import { Input } from "@/shared/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { cn } from "@/shared/lib/utils";
import { Check, ChevronsUpDown, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  buildActivityWhereOptions,
  CURVE_CLASS_OPTIONS,
  parseWhereOptionId,
  type WhereOption,
  whereConditionOptionId,
} from "../../lib/activity-where-options";
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

// inline: custom date logic — "today"/"yesterday" with date-only input; shared
// formatRelativeDate works from timestamps and would not produce the same output.
/** Format ISO date as a relative-ish suffix ("today", "3d ago", "Apr 20").
 *  Keeps the picker scannable without taking too much horizontal space. */
function formatLastRun(iso: string | null): string {
  if (!iso) return "no runs";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.floor((today.getTime() - d.getTime()) / 86400000);
  if (diffDays <= 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 14) return `${diffDays}d ago`;
  if (diffDays < 60) return `${Math.floor(diffDays / 7)}w ago`;
  // Older — show calendar date.
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: today.getFullYear() === d.getFullYear() ? undefined : "numeric",
  });
}

/** How many recently-used protocols to pin at the top of the list. */
const RECENTS_LIMIT = 5;
const RECENTS_MIN_TOTAL = 8; // only pin a recents group if the list is at least this long

export type ProtocolConjunction = "and" | "or";

function defaultActivityCriterion(): ActivityCriterion {
  return { type: "activity", protocol_id: "", where: [] };
}

function defaultWhereCondition(): ActivityWhereCondition {
  // The user must pick a readout before the row is sendable; we seed
  // with an empty id and dr_curve source which is the most common choice.
  return { source: "dr_curve", readout_definition_id: "", operator: "lt", value: 0 };
}

/** Read where[] from a criterion, normalizing the inline single-where shape
 *  into a single-element list so the UI only has to think in one model. */
function readWhere(c: ActivityCriterion): ActivityWhereCondition[] {
  if (Array.isArray(c.where)) return c.where;
  if (c.readout_definition_id) {
    const cond: ActivityWhereCondition = {
      source: c.source ?? "dr_curve",
      readout_definition_id: c.readout_definition_id,
      operator: c.operator ?? "lt",
    };
    if (c.value !== undefined) cond.value = c.value;
    return [cond];
  }
  return [];
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
  const value = [protocol.id, protocol.name, protocol.target_name ?? "", protocol.status]
    .join(" ")
    .toLowerCase();

  return (
    <CommandItem value={value} onSelect={onPick} className="text-sm py-1.5">
      <div className="flex w-full min-w-0 items-start gap-2">
        <Check className={cn("mt-1 h-3 w-3 shrink-0", selected ? "opacity-100" : "opacity-0")} />
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
              className={cn("line-clamp-2 text-sm", isArchived && "text-muted-foreground italic")}
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

interface WhereListProps {
  where: ActivityWhereCondition[];
  options: WhereOption[];
  onChange: (next: ActivityWhereCondition[]) => void;
}

function WhereList({ where, options, onChange }: WhereListProps) {
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
              options={options}
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
  options: WhereOption[];
  onChange: (next: ActivityWhereCondition) => void;
  onRemove: () => void;
}

function WhereRow({ cond, isFirst, options, onChange, onRemove }: WhereRowProps) {
  // The picker emits a stable option id; the row stores the (source,
  // readout-def, intercept_key) triple plus an operator and value.
  const fieldValue = whereConditionOptionId(cond);
  const isBetween = cond.operator === "between";
  const isCurveClass = cond.source === "curve_class";

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {/* Conjunction label — first row says "where", subsequent rows say "and" */}
      <span className="text-sm text-muted-foreground shrink-0 w-10">
        {isFirst ? "where" : "and"}
      </span>

      {/* Readout-def + intercept picker (DR intercepts, numeric readouts,
          and a Curve Class entry — all derived from the protocol). */}
      <Select
        value={fieldValue}
        onValueChange={(v) => {
          if (!v) {
            onChange({ ...cond, readout_definition_id: "" });
            return;
          }
          const parsed = parseWhereOptionId(v);
          if (!parsed) return;
          // Reset operator + value/curve_classes when source category
          // changes so stale fields don't leak to the backend.
          if (parsed.source === "curve_class") {
            onChange({
              ...cond,
              ...parsed,
              operator: "eq",
              value: undefined,
              min: undefined,
              max: undefined,
              curve_classes: cond.curve_classes ?? [],
            });
          } else {
            onChange({
              ...cond,
              ...parsed,
              operator: cond.operator === "eq" || isCurveClass ? "lt" : cond.operator,
              curve_classes: undefined,
            });
          }
        }}
      >
        <SelectTrigger className="h-8 w-56 text-sm shrink-0">
          <SelectValue placeholder="select readout…" />
        </SelectTrigger>
        <SelectContent>
          <WhereOptionList options={options} />
        </SelectContent>
      </Select>

      {isCurveClass ? (
        <>
          {/* Curve-class is a categorical "is one of" filter — no operator
              dropdown, just "is" + the multi-select chip group. */}
          <span className="text-sm text-muted-foreground shrink-0">is</span>
          <CurveClassChipGroup
            value={cond.curve_classes ?? []}
            onChange={(next) =>
              onChange({
                ...cond,
                curve_classes: next,
                operator: "eq",
                value: undefined,
                min: undefined,
                max: undefined,
              })
            }
          />
        </>
      ) : (
        <>
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
        </>
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

function WhereOptionList({ options }: { options: WhereOption[] }) {
  if (options.length === 0) {
    return (
      <div className="px-2 py-3 text-sm text-muted-foreground text-center">
        No readouts configured
      </div>
    );
  }
  const dr = options.filter((o) => o.group === "dose_response");
  const numeric = options.filter((o) => o.group === "numeric_readout");
  const curve = options.filter((o) => o.group === "curve_class");
  return (
    <>
      {dr.length > 0 && (
        <>
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/50">
            Dose-response
          </div>
          {dr.map((o) => (
            <SelectItem key={o.id} value={o.id}>
              {o.label}
            </SelectItem>
          ))}
        </>
      )}
      {numeric.length > 0 && (
        <>
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/50">
            Numeric readouts
          </div>
          {numeric.map((o) => (
            <SelectItem key={o.id} value={o.id}>
              {o.label}
              {o.unit ? ` (${o.unit})` : ""}
            </SelectItem>
          ))}
        </>
      )}
      {curve.length > 0 && (
        <>
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/50">
            Curve quality
          </div>
          {curve.map((o) => (
            <SelectItem key={o.id} value={o.id}>
              {o.label}
            </SelectItem>
          ))}
        </>
      )}
    </>
  );
}

function CurveClassChipGroup({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const selected = new Set(value);
  function toggle(v: string) {
    if (selected.has(v)) onChange(value.filter((x) => x !== v));
    else onChange([...value, v]);
  }
  return (
    <div className="flex flex-wrap items-center gap-1">
      {CURVE_CLASS_OPTIONS.map((opt) => {
        const active = selected.has(opt.value);
        return (
          <Badge
            key={opt.value}
            variant={active ? "default" : "outline"}
            onClick={() => toggle(opt.value)}
            className={cn(
              "cursor-pointer select-none text-xs font-normal",
              active ? "" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {CURVE_CLASS_LABELS[opt.value] ?? opt.label}
          </Badge>
        );
      })}
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
  /** True when the search panel has at least one project selected — controls
   *  visibility of the "Show all (across projects)" toggle inside the picker. */
  hasProjectScope: boolean;
  showAllProjects: boolean;
  /**
   * Pristine = the row was auto-rendered as a placeholder (criteria was empty),
   * not user-added. We suppress the "Choose a protocol" red border + error
   * text so the chemist isn't nagged by a row they never asked to fill in.
   * Once they pick a protocol the row promotes to a real criterion via
   * `onChange` and pristine no longer applies.
   */
  isPristine?: boolean;
  onShowAllProjectsChange: (next: boolean) => void;
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
  hasProjectScope,
  showAllProjects,
  isPristine = false,
  onShowAllProjectsChange,
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
    [protocols, showArchived],
  );

  // Pin a "Recently used" group at the top once the list is large enough.
  // Server returns rows already sorted by last_run_date desc; use that order.
  const { recents, others, hasRecents } = useMemo(() => {
    const withRuns = visibleProtocols.filter((p) => p.last_run_date !== null);
    const shouldPin = visibleProtocols.length >= RECENTS_MIN_TOTAL && withRuns.length >= 2;
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

  const whereOptions = useMemo(() => buildActivityWhereOptions(protocol), [protocol]);

  const hasProtocol = Boolean(criterion.protocol_id);
  // Pristine rows don't surface validation — the row is a passive
  // "always-visible empty row" placeholder. Only flag invalid once the
  // user has committed (real row from +Add or saved-search load).
  const protocolInvalid = !hasProtocol && !isPristine;
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
          <PopoverContent className="p-0 w-[28rem] max-w-[calc(100vw-2rem)]" align="start">
            <Command
              filter={(value, search) => {
                // Match by name + target + status; case-insensitive substring.
                const haystack = value.toLowerCase();
                const needle = search.toLowerCase().trim();
                if (!needle) return 1;
                return haystack.includes(needle) ? 1 : 0;
              }}
            >
              <CommandInput placeholder="Search protocols, targets…" className="h-8 text-sm" />
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
                              source: undefined,
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
                          source: undefined,
                        });
                        setProtocolOpen(false);
                      }}
                    />
                  ))}
                </CommandGroup>

                <div className="flex flex-col gap-1.5 border-t border-border px-3 py-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
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
                  {hasProjectScope && (
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id={`protocol-show-all-${index}`}
                        checked={showAllProjects}
                        onCheckedChange={(v) => onShowAllProjectsChange(v === true)}
                        className="h-3.5 w-3.5"
                      />
                      <label
                        htmlFor={`protocol-show-all-${index}`}
                        className="cursor-pointer select-none"
                      >
                        Show all (across projects)
                      </label>
                    </div>
                  )}
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
            onChange={(next: RunScope | undefined) => onChange({ ...criterion, run_scope: next })}
          />

          {/* where — optional, multiple. Empty list ⇒ presence filter
              ("compounds screened in this protocol/scope"). */}
          <WhereList
            where={whereList}
            options={whereOptions}
            onChange={(next) => {
              // Drop the inline single-where fields once we manage where[].
              onChange({
                ...criterion,
                where: next,
                source: undefined,
                readout_definition_id: undefined,
                operator: undefined,
                value: undefined,
              });
            }}
          />
        </div>
      )}

      {protocolInvalid && <p className="ml-[70px] text-xs text-destructive">Choose a protocol.</p>}
    </div>
  );
}

// ─── Section ────────────────────────────────────────────────────────────────

export interface ProtocolSectionProps {
  criteria: ActivityCriterion[];
  conjunctions: ProtocolConjunction[];
  /** Selected projects from the search panel — scopes the picker list when non-empty. */
  projectIds: string[];
  onChange: (criteria: ActivityCriterion[], conjunctions: ProtocolConjunction[]) => void;
}

export function ProtocolSection({
  criteria,
  conjunctions,
  projectIds,
  onChange,
}: ProtocolSectionProps) {
  // Section-level "Show all (across projects)" — flipping in one picker
  // affects all rows so chemists don't toggle it per row when comparing
  // two protocols. Resets implicitly whenever the selected projects change.
  const [showAllProjects, setShowAllProjects] = useState(false);
  // Pristine row: when criteria is empty we render one passive
  // placeholder row with the protocol picker ready, so the most common
  // search shape (`project + protocol + …`) is one click away instead of two.
  // Dismissing the pristine row hides it for the rest of the session — until
  // the user adds a real row and removes it again, at which point the
  // "fresh start" intent re-shows the placeholder.
  const [pristineDismissed, setPristineDismissed] = useState(false);
  useEffect(() => {
    if (criteria.length > 0) setPristineDismissed(false);
  }, [criteria.length]);
  const showPristine = criteria.length === 0 && !pristineDismissed;
  const hasProjectScope = projectIds.length > 0;
  const { data: protocols } = useProtocolSummaries(projectIds, {
    includeAll: showAllProjects,
  });

  const addTerm = useCallback(() => {
    onChange([...criteria, defaultActivityCriterion()], [...conjunctions, "or"]);
  }, [criteria, conjunctions, onChange]);

  // Picking a protocol on the pristine placeholder row promotes it to a
  // real criterion. Until that happens the row contributes nothing to the
  // composed query (no protocol_id ⇒ filtered out by composeCriteria).
  const commitPristine = useCallback(
    (next: ActivityCriterion) => {
      onChange([next], ["or"]);
    },
    [onChange],
  );

  const updateTerm = useCallback(
    (index: number, updated: ActivityCriterion) => {
      onChange(
        criteria.map((c, i) => (i === index ? updated : c)),
        conjunctions,
      );
    },
    [criteria, conjunctions, onChange],
  );

  const removeTerm = useCallback(
    (index: number) => {
      onChange(
        criteria.filter((_, i) => i !== index),
        conjunctions.filter((_, i) => i !== index),
      );
    },
    [criteria, conjunctions, onChange],
  );

  const updateConjunction = useCallback(
    (index: number, conj: ProtocolConjunction) => {
      onChange(
        criteria,
        conjunctions.map((c, i) => (i === index ? conj : c)),
      );
    },
    [criteria, conjunctions, onChange],
  );

  return (
    <div className="space-y-2">
      {/* Section header — `+ Add` is hidden while the pristine placeholder is
          showing, so the chemist isn't presented with two ways to create their
          first row. Once they pick a protocol it reappears for adding more. */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Protocols
        </span>
        {!showPristine && (
          <button
            type="button"
            onClick={addTerm}
            className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors"
          >
            <Plus className="h-3 w-3" />
            Add
          </button>
        )}
      </div>

      {/* Empty state — only when the user has explicitly dismissed the
          pristine placeholder and there are no real rows. */}
      {criteria.length === 0 && pristineDismissed && (
        <button
          type="button"
          onClick={addTerm}
          className="text-sm italic text-muted-foreground/60 hover:text-foreground transition-colors py-1"
        >
          + Add a protocol filter
        </button>
      )}

      {/* Pristine placeholder row — passive until the user picks a protocol. */}
      {showPristine && (
        <div className="space-y-3">
          <ActivityRow
            index={0}
            criterion={defaultActivityCriterion()}
            conjunction="or"
            protocols={protocols ?? []}
            isFirst
            isPristine
            hasProjectScope={hasProjectScope}
            showAllProjects={showAllProjects}
            onShowAllProjectsChange={setShowAllProjects}
            onConjunctionChange={() => {
              /* Conjunction is hidden on the first row; pristine never has siblings */
            }}
            onChange={commitPristine}
            onRemove={() => setPristineDismissed(true)}
          />
        </div>
      )}

      {/* Real criteria rows */}
      <div className="space-y-3">
        {criteria.map((c, i) => (
          <ActivityRow
            key={`activity-${i}`}
            index={i}
            criterion={c}
            conjunction={conjunctions[i] ?? "or"}
            protocols={protocols ?? []}
            isFirst={i === 0}
            hasProjectScope={hasProjectScope}
            showAllProjects={showAllProjects}
            onShowAllProjectsChange={setShowAllProjects}
            onConjunctionChange={(conj) => updateConjunction(i, conj)}
            onChange={(updated) => updateTerm(i, updated)}
            onRemove={() => removeTerm(i)}
          />
        ))}
      </div>
    </div>
  );
}
