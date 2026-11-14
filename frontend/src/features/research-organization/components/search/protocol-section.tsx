"use client";

import { ProtocolOptionLabel } from "@/features/screening-assay";
import { TargetChips } from "@/features/screening-assay/components/target-chips";
import {
  type ProtocolSummary,
  useProtocol,
  useProtocolSummaries,
} from "@/features/screening-assay/hooks/use-protocols";
import {
  CURVE_CLASS_LABELS,
  PROTOCOL_TYPE_LABELS,
  type Protocol,
  type ProtocolType,
} from "@/features/screening-assay/types";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
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
import { formatRelativeDay } from "@/shared/lib/format-date";
import { cn } from "@/shared/lib/utils";
import { Check, ChevronsUpDown, Minus, Plus, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import {
  CURVE_CLASS_OPTIONS,
  POTENCY_UM_OPTION_ID,
  type WhereOption,
  buildActivityWhereOptions,
  buildAnyProtocolWhereOptions,
  parseWhereOptionId,
  whereConditionOptionId,
} from "../../lib/activity-where-options";
import type {
  ActivityCriterion,
  ActivityWhereCondition,
  PropertyOperator,
  RunScope,
} from "../../types";
import { RunScopePicker } from "./run-scope-picker";
import { LATEST_UNDER_CONDITION_SPLIT, SplitPicker, withRunScope } from "./split-picker";

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

/** Format a date-only "last run on" value as a relative-ish suffix ("today",
 *  "3d ago", "Apr 20"), keeping the picker scannable. `null` → "no runs".
 *  Delegates the day-granular relative formatting to the shared helper. */
function formatLastRun(iso: string | null): string {
  if (!iso) return "no runs";
  // formatRelativeDay returns "" for an unparseable value — fall back to the raw
  // string so a malformed date is still shown rather than blanked.
  return formatRelativeDay(iso) || iso;
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
  // No value until the chemist types one: a seeded "< 0" made every new
  // potency row match nothing (and the live count flash 0).
  return { source: "dr_curve", readout_definition_id: "", operator: "lt" };
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
  /** What the assay can be filtered on (IC50, % inhibition, …). */
  endpoints: string[];
  selected: boolean;
  onPick: () => void;
}

/** Endpoints a protocol's results can be filtered on — the labels the
 *  activity-condition picker offers, minus the generic Curve Class entry. */
function endpointLabels(protocol: Protocol): string[] {
  return buildActivityWhereOptions(protocol)
    .filter((o) => o.group !== "curve_class")
    .map((o) => o.label);
}

function ProtocolRow({ protocol, endpoints, selected, onPick }: ProtocolRowProps) {
  const isArchived = protocol.status === "retired" || protocol.status === "archived";
  // Build a haystack so Command's filter can hit name + all targets + status.
  const targets = protocol.targets ?? [];
  const value = [
    protocol.id,
    protocol.code,
    protocol.name,
    ...(protocol.aliases ?? []),
    targets.map((t) => t.name).join(" "),
    protocol.status,
  ]
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
            <span className={cn("min-w-0 text-sm", isArchived && "text-muted-foreground italic")}>
              <ProtocolOptionLabel code={protocol.code} name={protocol.name} wrap />
            </span>
            {isArchived && (
              <span className="rounded-full border border-muted-foreground/20 px-1.5 text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">
                {protocol.status}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
            {targets.length > 0 && <TargetChips targets={targets} />}
            <span>
              {PROTOCOL_TYPE_LABELS[protocol.protocol_type as ProtocolType] ??
                protocol.protocol_type}
            </span>
            <span aria-hidden>·</span>
            <span className="tabular-nums">
              {protocol.run_count} run{protocol.run_count === 1 ? "" : "s"}
            </span>
            <span aria-hidden>·</span>
            <span>last {formatLastRun(protocol.last_run_date ?? null)}</span>
            {endpoints.length > 0 && (
              <>
                <span aria-hidden>·</span>
                {/* Thermal-shift protocols carry a dozen readouts; four is
                    enough to recognise the assay, the title has the rest. */}
                <span className="text-foreground/70" title={endpoints.join(", ")}>
                  {endpoints.slice(0, 4).join(", ")}
                  {endpoints.length > 4 && ` +${endpoints.length - 4}`}
                </span>
              </>
            )}
          </div>
          {protocol.description && (
            <p className="truncate text-xs text-muted-foreground/80" title={protocol.description}>
              {protocol.description}
            </p>
          )}
        </div>
      </div>
    </CommandItem>
  );
}

// ─── Activity where rows (multiple ANDed conditions) ───────────────────────

interface WhereListProps {
  where: ActivityWhereCondition[];
  options: WhereOption[];
  anyProtocol?: boolean;
  onChange: (next: ActivityWhereCondition[]) => void;
}

function WhereList({ where, options, anyProtocol = false, onChange }: WhereListProps) {
  function update(i: number, next: ActivityWhereCondition) {
    onChange(where.map((w, idx) => (idx === i ? next : w)));
  }
  function remove(i: number) {
    onChange(where.filter((_, idx) => idx !== i));
  }
  function add() {
    // On an any-protocol row, a fresh {source:"dr_curve", readout_definition_id:""}
    // is indistinguishable from the legacy saved "potency" shape — seed from
    // the first catalog option instead so the new row actually resolves to
    // what it displays.
    const firstOption = anyProtocol ? options[0] : undefined;
    const parsed = firstOption ? parseWhereOptionId(firstOption.id) : null;
    if (parsed) {
      onChange([
        ...where,
        parsed.source === "curve_class"
          ? { ...parsed, operator: "eq", curve_classes: [] }
          : { ...parsed, operator: "lt" },
      ]);
      return;
    }
    onChange([...where, defaultWhereCondition()]);
  }

  return (
    <div className="space-y-1">
      {where.length === 0 ? (
        <button
          type="button"
          onClick={add}
          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 transition-colors"
        >
          <Plus className="h-3 w-3" />
          Add activity condition
        </button>
      ) : (
        <>
          {where.map((cond, i) => (
            <WhereRow
              key={i}
              cond={cond}
              isFirst={i === 0}
              options={options}
              anyProtocol={anyProtocol}
              onChange={(next) => update(i, next)}
              onRemove={() => remove(i)}
            />
          ))}
          <button
            type="button"
            onClick={add}
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 transition-colors"
          >
            <Plus className="h-3 w-3" />
            Add another condition
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
  anyProtocol: boolean;
  onChange: (next: ActivityWhereCondition) => void;
  onRemove: () => void;
}

function WhereRow({ cond, isFirst, options, anyProtocol, onChange, onRemove }: WhereRowProps) {
  // The picker emits a stable option id; the row stores the (source,
  // readout-def, intercept_key) triple plus an operator and value.
  const fieldValue = whereConditionOptionId(cond, anyProtocol);
  const isBetween = cond.operator === "between";
  const isCurveClass = cond.source === "curve_class";
  // Legacy saved searches carry the pre-catalog "potency in µM" option id,
  // which no longer appears in the built option list — synthesize a
  // disabled entry so the Select still shows a label instead of blank.
  const legacyPotency =
    fieldValue === POTENCY_UM_OPTION_ID && !options.some((o) => o.id === fieldValue);

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {/* Conjunction label — first row says "where", subsequent rows say "and" */}
      <span className="text-sm text-muted-foreground shrink-0 w-24">
        {isFirst ? "Endpoint" : "and"}
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
              readout_name: parsed.readout_name,
              unit: parsed.unit,
              normalization: parsed.normalization ?? undefined,
              operator: cond.operator === "eq" || isCurveClass ? "lt" : cond.operator,
              curve_classes: undefined,
            });
          }
        }}
      >
        <SelectTrigger className="h-8 w-56 max-w-full text-sm shrink-0">
          <SelectValue placeholder="select readout…" />
        </SelectTrigger>
        <SelectContent>
          <WhereOptionList options={options} legacyPotency={legacyPotency} />
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

function WhereOptionList({
  options,
  legacyPotency = false,
}: {
  options: WhereOption[];
  legacyPotency?: boolean;
}) {
  if (options.length === 0 && !legacyPotency) {
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
      {legacyPotency && (
        <SelectItem value={POTENCY_UM_OPTION_ID} disabled>
          Potency (primary fit) — legacy
        </SelectItem>
      )}
      {dr.length > 0 && (
        <>
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/50">
            Dose-response
          </div>
          {dr.map((o) => (
            <SelectItem key={o.id} value={o.id}>
              {o.label}
              {o.unit && !o.id.startsWith("any:") ? ` (${o.unit})` : ""}
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
              {o.unit && !o.id.startsWith("any:") ? ` (${o.unit})` : ""}
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
  /** Full protocol records (with readout_definitions) — feeds the
   *  any-protocol where-option catalog. */
  fullProtocols: Protocol[];
  isFirst: boolean;
  showConjunction?: boolean;
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
  /** An earlier row names the same protocol with a different run filter or
   *  split — the search can't tell which runs feed this protocol's columns. */
  conflictsWithEarlierRow?: boolean;
  onShowAllProjectsChange: (next: boolean) => void;
  onConjunctionChange: (conj: ProtocolConjunction) => void;
  onChange: (c: ActivityCriterion) => void;
  /** Omitted for the only assay — the section's own × removes it. */
  onRemove?: () => void;
}

/** True when an earlier row names the same protocol with a different run
 *  filter or split (the backend can't plan that protocol's columns). */
export function conflictsWithEarlierRow(criteria: ActivityCriterion[], index: number): boolean {
  const row = criteria[index];
  if (!row.protocol_id) return false;
  const settings = (c: ActivityCriterion) =>
    JSON.stringify([
      c.run_scope?.mode === "any" ? undefined : (c.run_scope ?? undefined),
      c.split ?? undefined,
    ]);
  return criteria
    .slice(0, index)
    .some((c) => c.protocol_id === row.protocol_id && settings(c) !== settings(row));
}

/** The criterion after choosing protocol ``next`` (null = any protocol).
 *
 *  The where-option vocabulary differs between a specific protocol and "any",
 *  so crossing that line resets the where-list. Run scope is per-protocol and
 *  drops on "any"; hand-picked runs and the split belong to the old protocol
 *  and always drop. */
export function pickProtocolCriterion(
  criterion: ActivityCriterion,
  next: string | null,
): ActivityCriterion {
  const crossed = (criterion.protocol_id === null) !== (next === null);
  const changed = criterion.protocol_id !== next;
  const runScope =
    next === null || (changed && criterion.run_scope?.mode === "specific")
      ? undefined
      : criterion.run_scope;
  return {
    ...criterion,
    protocol_id: next,
    where: crossed ? [] : criterion.where,
    run_scope: runScope,
    split: changed ? undefined : criterion.split,
    readout_definition_id: undefined,
    source: undefined,
  };
}

function ActivityRow({
  index,
  criterion,
  conjunction,
  protocols,
  fullProtocols,
  isFirst,
  showConjunction = false,
  hasProjectScope,
  showAllProjects,
  isPristine = false,
  conflictsWithEarlierRow = false,
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

  const endpointsById = useMemo(
    () => new Map(fullProtocols.map((p) => [p.id, endpointLabels(p)])),
    [fullProtocols],
  );

  // Pin a "Recently run" group at the top once the list is large enough.
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
  const isAnyProtocol = criterion.protocol_id === null;

  const whereOptions = useMemo(
    () =>
      isAnyProtocol
        ? buildAnyProtocolWhereOptions(fullProtocols)
        : buildActivityWhereOptions(protocol),
    [isAnyProtocol, fullProtocols, protocol],
  );

  // null = "Any protocol" (chosen); "" = nothing chosen yet.
  const hasProtocol = criterion.protocol_id !== "";

  function pickProtocol(next: string | null) {
    onChange(pickProtocolCriterion(criterion, next));
    setProtocolOpen(false);
  }
  // Pristine rows don't surface validation — the row is a passive
  // "always-visible empty row" placeholder. Only flag invalid once the
  // user has committed (real row from +Add or saved-search load).
  const protocolInvalid = !hasProtocol && !isPristine;
  // The where-clause is optional: a protocol-only criterion is a valid
  // "any compound screened in this protocol/scope" presence filter.
  const whereList = readWhere(criterion);

  return (
    <fieldset
      aria-label={`Assay ${index + 1}`}
      className="min-w-0 space-y-2 rounded-lg border border-border/70 bg-muted/15 p-3"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-muted-foreground">Assay {index + 1}</span>
        {!isFirst && showConjunction && (
          <Select
            value={conjunction}
            onValueChange={(v) => onConjunctionChange(v as ProtocolConjunction)}
          >
            <SelectTrigger aria-label={`Join assay ${index + 1}`} className="h-7 w-20 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="and">and</SelectItem>
              <SelectItem value="or">or</SelectItem>
            </SelectContent>
          </Select>
        )}
        {onRemove && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="ml-auto size-6 text-muted-foreground hover:text-destructive"
            onClick={onRemove}
            aria-label={`Remove assay ${index + 1}`}
            title={`Remove assay ${index + 1}`}
          >
            <X className="size-3.5" />
          </Button>
        )}
      </div>
      <div className="flex min-w-0 items-center gap-2">
        {/* Protocol picker (rich rows: status dot + name + target + run stats) */}
        <Popover open={protocolOpen} onOpenChange={setProtocolOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                "flex h-8 min-w-0 flex-1 items-center justify-between gap-1.5 rounded-md border border-input bg-transparent px-2 text-sm shadow-xs",
                !hasProtocol && "text-muted-foreground",
                protocolInvalid && "border-destructive",
              )}
              aria-invalid={protocolInvalid}
            >
              {isAnyProtocol ? (
                <span className="truncate">Any protocol</span>
              ) : selectedProtocol ? (
                <span className="flex min-w-0 items-center gap-1.5">
                  <span
                    className={cn(
                      "h-2 w-2 rounded-full shrink-0",
                      protocolStatusColor(selectedProtocol.status),
                    )}
                    aria-hidden
                  />
                  <span className="truncate">
                    <ProtocolOptionLabel
                      code={selectedProtocol.code}
                      name={selectedProtocol.name}
                    />
                  </span>
                </span>
              ) : (
                <span className="truncate">Choose protocol…</span>
              )}
              <ChevronsUpDown className="h-3 w-3 shrink-0 opacity-50" />
            </button>
          </PopoverTrigger>
          {/* As wide as the field and as tall as the screen allows, so full
              protocol names fit and more of the list is visible at once. */}
          <PopoverContent
            className="flex max-h-(--radix-popover-content-available-height) w-[max(28rem,var(--radix-popover-trigger-width))] max-w-[calc(100vw-2rem)] flex-col p-0"
            align="start"
            collisionPadding={16}
          >
            <Command
              className="min-h-0"
              filter={(value, search) => {
                // Match by name + target + status; case-insensitive substring.
                const haystack = value.toLowerCase();
                const needle = search.toLowerCase().trim();
                if (!needle) return 1;
                return haystack.includes(needle) ? 1 : 0;
              }}
            >
              <CommandInput placeholder="Search protocols, targets…" className="h-8 text-sm" />
              <CommandList className="max-h-none min-h-0 flex-1">
                <CommandEmpty>No protocols found.</CommandEmpty>

                <CommandGroup>
                  <CommandItem
                    value="any protocol"
                    onSelect={() => pickProtocol(null)}
                    className="flex items-center gap-2 py-1.5"
                  >
                    <Check
                      className={cn(
                        "h-3.5 w-3.5 shrink-0",
                        isAnyProtocol ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <span className="text-sm">Any protocol</span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      any measured intercept or readout
                    </span>
                  </CommandItem>
                </CommandGroup>
                <CommandSeparator />

                {hasRecents && (
                  <>
                    <CommandGroup heading="Recently run">
                      {recents.map((p) => (
                        <ProtocolRow
                          key={p.id}
                          protocol={p}
                          endpoints={endpointsById.get(p.id) ?? []}
                          selected={criterion.protocol_id === p.id}
                          onPick={() => pickProtocol(p.id)}
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
                      endpoints={endpointsById.get(p.id) ?? []}
                      selected={criterion.protocol_id === p.id}
                      onPick={() => pickProtocol(p.id)}
                    />
                  ))}
                </CommandGroup>
              </CommandList>

              {/* Pinned below the list so the toggles stay in sight. */}
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
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {hasProtocol && (
        <div className="space-y-3">
          {/* Filters first (runs, then endpoints), display last (split only
              groups the result columns; it never changes which compounds
              match). Runs are per-protocol only; "Any protocol" has none. */}
          {criterion.protocol_id !== null && (
            <RunScopePicker
              protocolId={criterion.protocol_id}
              value={criterion.run_scope}
              onChange={(next: RunScope | undefined) =>
                onChange({ ...criterion, ...withRunScope(criterion.split, next) })
              }
              latestDisabledReason={
                criterion.split?.by === "condition" ? LATEST_UNDER_CONDITION_SPLIT : undefined
              }
            />
          )}

          {/* where — optional, multiple. Empty list ⇒ presence filter
              ("compounds screened in this protocol/scope"). */}
          <WhereList
            where={whereList}
            options={whereOptions}
            anyProtocol={isAnyProtocol}
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

          {criterion.protocol_id !== null && (
            <>
              {/* split — optional side-by-side columns per run or condition */}
              <SplitPicker
                conditions={protocol?.condition_definitions ?? []}
                split={criterion.split}
                runScope={criterion.run_scope}
                onChange={(next) => onChange({ ...criterion, ...next })}
              />
              {conflictsWithEarlierRow && (
                <p className="text-xs text-destructive">
                  This protocol already has a different run filter or split above.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {protocolInvalid && <p className="text-xs text-destructive">Choose a protocol.</p>}
    </fieldset>
  );
}

// ─── Section ────────────────────────────────────────────────────────────────

export interface ProtocolSectionProps {
  criteria: ActivityCriterion[];
  conjunctions: ProtocolConjunction[];
  /** Selected projects from the search panel — scopes the picker list when non-empty. */
  projectIds: string[];
  /** Full protocol records (with readout_definitions) — feeds the any-protocol catalog. */
  protocols: Protocol[];
  onChange: (criteria: ActivityCriterion[], conjunctions: ProtocolConjunction[]) => void;
}

export function ProtocolSection({
  criteria,
  conjunctions,
  projectIds,
  protocols,
  onChange,
}: ProtocolSectionProps) {
  // Section-level "Show all (across projects)" — flipping in one picker
  // affects all rows so chemists don't toggle it per row when comparing
  // two protocols. Resets implicitly whenever the selected projects change.
  const [showAllProjects, setShowAllProjects] = useState(false);
  // Pristine row: when criteria is empty we render one passive
  // placeholder row with the protocol picker ready, so the most common
  // search shape (`project + protocol + …`) is one click away instead of two.
  // It has no remove of its own — the section's × removes the whole section.
  const showPristine = criteria.length === 0;
  const hasProjectScope = projectIds.length > 0;
  // Renamed from `protocols` to avoid shadowing the `protocols: Protocol[]`
  // prop (full records) — this is the lighter ProtocolSummary[] list used
  // by the picker only.
  const { data: protocolSummaries } = useProtocolSummaries(projectIds, {
    includeAll: showAllProjects,
  });

  const [customLogic, setCustomLogic] = useState(false);
  const joins = criteria.length > 1 ? conjunctions.slice(1) : conjunctions;
  const uniformMode =
    joins.length > 0 && joins.every((join) => join === "and")
      ? "all"
      : joins.every((join) => join === "or")
        ? "any"
        : "custom";
  const matchMode = customLogic || uniformMode === "custom" ? "custom" : uniformMode;
  const addTerm = useCallback(() => {
    onChange(
      [...criteria, defaultActivityCriterion()],
      [...conjunctions, matchMode === "all" ? "and" : "or"],
    );
  }, [criteria, conjunctions, matchMode, onChange]);

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
      <h3 className="text-sm font-semibold">Assay activity</h3>
      <p className="text-xs text-muted-foreground">
        An assay alone matches tested compounds. Add activity conditions to narrow by endpoints,
        such as IC50 &lt; 10 µM.
      </p>
      {criteria.length > 1 && (
        <div className="space-y-1.5 rounded-lg bg-primary/5 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium">Find compounds that</span>
            <Select
              value={matchMode}
              onValueChange={(value) => {
                setCustomLogic(value === "custom");
                if (value !== "custom")
                  onChange(
                    criteria,
                    criteria.map(() => (value === "all" ? "and" : "or")),
                  );
              }}
            >
              <SelectTrigger aria-label="Assay matching" className="h-8 w-44 bg-background text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Match any assay</SelectItem>
                <SelectItem value="all">Match all assays</SelectItem>
                <SelectItem value="custom">Custom logic</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-muted-foreground">
            {matchMode === "all"
              ? "Must meet the conditions in every assay below."
              : matchMode === "any"
                ? "Must meet the conditions in at least one assay below."
                : "Choose AND / OR on each card. Consecutive OR assays form a group; groups are joined by AND. Review the draft summary before searching."}
          </p>
        </div>
      )}

      {/* Pristine placeholder row — passive until the user picks a protocol. */}
      {showPristine && (
        <div className="space-y-3">
          <ActivityRow
            index={0}
            criterion={defaultActivityCriterion()}
            conjunction="or"
            protocols={protocolSummaries ?? []}
            fullProtocols={protocols}
            isFirst
            isPristine
            hasProjectScope={hasProjectScope}
            showAllProjects={showAllProjects}
            onShowAllProjectsChange={setShowAllProjects}
            onConjunctionChange={() => {
              /* Conjunction is hidden on the first row; pristine never has siblings */
            }}
            onChange={commitPristine}
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
            conflictsWithEarlierRow={conflictsWithEarlierRow(criteria, i)}
            conjunction={conjunctions[i] ?? "or"}
            protocols={protocolSummaries ?? []}
            fullProtocols={protocols}
            isFirst={i === 0}
            showConjunction={matchMode === "custom"}
            hasProjectScope={hasProjectScope}
            showAllProjects={showAllProjects}
            onShowAllProjectsChange={setShowAllProjects}
            onConjunctionChange={(conj) => updateConjunction(i, conj)}
            onChange={(updated) => updateTerm(i, updated)}
            // The only assay has no × of its own: the section's × removes it.
            onRemove={criteria.length > 1 ? () => removeTerm(i) : undefined}
          />
        ))}
      </div>

      {/* After the last assay, where the eye is once one is finished — a
          counter-screen or selectivity assay is added after the primary. */}
      {criteria.length > 0 && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-xs text-primary"
          onClick={addTerm}
        >
          <Plus className="size-3.5" /> Add another assay
        </Button>
      )}
    </div>
  );
}
