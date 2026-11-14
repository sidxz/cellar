"use client";

import { ConditionChips } from "@/features/screening-assay/components/condition-chips";
import { useRunsByProtocol } from "@/features/screening-assay/hooks/use-runs";
import { formatConditionEntries } from "@/features/screening-assay/lib/conditions";
import { RUN_STATUS_LABELS, type Run, type RunStatus } from "@/features/screening-assay/types";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { Input } from "@/shared/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { Select, SelectContent, SelectTrigger, SelectValue } from "@/shared/components/ui/select";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { cn } from "@/shared/lib/utils";
import { CheckIcon, ChevronsUpDown, X } from "lucide-react";
import { Select as SelectPrimitive } from "radix-ui";
import { useMemo, useRef, useState } from "react";
import type { RunScope, RunScopeMode } from "../../types";

// Ordered broad → narrow so the menu reads as a continuum of run-set
// restriction. Labels favor chemist-natural English ("Any run" / "Every run"
// parallel construction; "Last N days" reads more naturally than "Past N
// days"). Descriptions are rendered as a muted sub-line so the meaning is
// scannable without a hover tooltip. The wire-shape `value` strings are
// unchanged — `mode: "all"` still persists in saved searches even though
// its label is now "Every run".
const MODE_OPTIONS: {
  value: RunScopeMode;
  label: string;
  description: string;
}[] = [
  {
    value: "any",
    label: "Any run",
    description: "Match if at least one run satisfies the criterion.",
  },
  {
    value: "all",
    label: "Every run",
    description: "Match only if every run for this protocol satisfies the criterion.",
  },
  {
    value: "latest",
    label: "Latest run",
    description: "Restrict to this protocol's most recent run (by run date).",
  },
  {
    value: "past_n_days",
    label: "Last N days",
    description: "Restrict to runs from the last N days.",
  },
  {
    value: "date_range",
    label: "Date range",
    description: "Restrict to runs whose run date falls within the chosen window.",
  },
  {
    value: "specific",
    label: "Specific runs",
    description: "Restrict to a hand-picked list of runs.",
  },
];

/**
 * Mode option rendered via Radix primitives — `<SelectPrimitive.ItemText>`
 * wraps ONLY the label, which is what `<SelectValue />` reads to populate
 * the trigger. The description renders as a sibling outside ItemText so it
 * appears only in the open menu, never collapsed into the trigger row.
 * shadcn's `<SelectItem>` auto-wraps every child in ItemText, which would
 * cause the description to bleed into the trigger; using the Radix
 * primitive directly is the lowest-friction way to honor that contract
 * without patching the shared component.
 */
function ScopeOption({
  option,
  disabledReason,
}: {
  option: (typeof MODE_OPTIONS)[number];
  /** Set to disable the option; shown in place of its description. */
  disabledReason?: string;
}) {
  return (
    <SelectPrimitive.Item
      value={option.value}
      disabled={!!disabledReason}
      className={cn(
        "relative flex w-full cursor-default select-none items-start gap-2 rounded-sm py-1.5 pr-8 pl-2 text-sm outline-none",
        "focus:bg-accent focus:text-accent-foreground",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      )}
    >
      <span className="absolute right-2 top-2 flex h-3.5 w-3.5 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <CheckIcon className="h-4 w-4" />
        </SelectPrimitive.ItemIndicator>
      </span>
      <div className="flex flex-col gap-0.5">
        <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
        <span className="text-xs text-muted-foreground">
          {disabledReason ?? option.description}
        </span>
      </div>
    </SelectPrimitive.Item>
  );
}

/** Status dot driven by run.status + is_locked. */
function statusColor(status: RunStatus, isLocked: boolean): string {
  if (isLocked || status === "approved") return "bg-emerald-500";
  if (status === "rejected") return "bg-red-500";
  if (status === "completed") return "bg-amber-500";
  return "bg-muted-foreground/40";
}

/** Closed-trigger label for one picked run: the experiment date, then its
 *  first plate barcode or its notes (CSS truncates the rest). */
function runLabel(run: Run): string {
  const id = run.plate_barcodes?.[0] ?? run.notes?.trim();
  return id ? `${run.run_date} · ${id}` : run.run_date;
}

/** Condition names whose value is not the same on every run — the ones that
 *  tell runs apart (e.g. ATP 1 mM vs 10 mM), so they lead each row. */
export function differingConditionKeys(runs: Run[]): Set<string> {
  const keys = new Set(runs.flatMap((r) => formatConditionEntries(r.conditions).map((e) => e.key)));
  return new Set(
    [...keys].filter((k) => new Set(runs.map((r) => String(r.conditions?.[k] ?? ""))).size > 1),
  );
}

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

interface RunScopePickerProps {
  protocolId: string;
  value: RunScope | undefined;
  onChange: (next: RunScope | undefined) => void;
  /** Disables "Latest run" (e.g. while the protocol is split by condition). */
  latestDisabledReason?: string;
}

export function RunScopePicker({
  protocolId,
  value,
  onChange,
  latestDisabledReason,
}: RunScopePickerProps) {
  const mode: RunScopeMode = value?.mode ?? "any";
  const keepFocus = useRef(false);

  function setMode(next: RunScopeMode) {
    // The run list opens itself next (see SpecificRunPicker); stop this menu
    // from handing focus back to its trigger, which would close that list.
    keepFocus.current = next === "specific";
    if (next === "any") {
      onChange(undefined);
      return;
    }
    if (next === "latest") onChange({ mode: "latest" });
    else if (next === "all") onChange({ mode: "all" });
    else if (next === "date_range") onChange({ mode: "date_range" });
    else if (next === "past_n_days") onChange({ mode: "past_n_days", days: 30 });
    else if (next === "specific") onChange({ mode: "specific", run_ids: [] });
  }

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-sm text-muted-foreground shrink-0 w-24">Runs</span>

      <Select value={mode} onValueChange={(v) => setMode(v as RunScopeMode)}>
        <SelectTrigger className="h-8 w-36 text-sm shrink-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent
          className="min-w-[20rem]"
          onCloseAutoFocus={(e) => {
            if (keepFocus.current) e.preventDefault();
            keepFocus.current = false;
          }}
        >
          {MODE_OPTIONS.map((opt) => (
            <ScopeOption
              key={opt.value}
              option={opt}
              disabledReason={opt.value === "latest" ? latestDisabledReason : undefined}
            />
          ))}
        </SelectContent>
      </Select>

      {value?.mode === "date_range" && <DateRangeInputs value={value} onChange={onChange} />}

      {value?.mode === "past_n_days" && <PastNDaysInput value={value} onChange={onChange} />}

      {value?.mode === "specific" && (
        <SpecificRunPicker
          protocolId={protocolId}
          runIds={specificRunIds(value)}
          onChange={(ids) => onChange({ mode: "specific", run_ids: ids })}
        />
      )}
    </div>
  );
}

/** Normalize legacy single-run `run_id` to the multi-select shape so the
 *  picker only has to think in one model. */
function specificRunIds(value: Extract<RunScope, { mode: "specific" }>): string[] {
  if (value.run_ids && value.run_ids.length > 0) return value.run_ids;
  if (value.run_id) return [value.run_id];
  return [];
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function DateRangeInputs({
  value,
  onChange,
}: {
  value: Extract<RunScope, { mode: "date_range" }>;
  onChange: (next: RunScope) => void;
}) {
  return (
    <>
      <Input
        type="date"
        className="h-8 w-36 text-sm"
        value={value.date_from ?? ""}
        onChange={(e) => onChange({ ...value, date_from: e.target.value || undefined })}
        aria-label="From date"
      />
      <span className="text-xs text-muted-foreground">→</span>
      <Input
        type="date"
        className="h-8 w-36 text-sm"
        value={value.date_to ?? ""}
        onChange={(e) => onChange({ ...value, date_to: e.target.value || undefined })}
        aria-label="To date"
      />
    </>
  );
}

function PastNDaysInput({
  value,
  onChange,
}: {
  value: Extract<RunScope, { mode: "past_n_days" }>;
  onChange: (next: RunScope) => void;
}) {
  return (
    <>
      <Input
        type="number"
        min={1}
        className="h-8 w-16 text-sm"
        value={value.days}
        onChange={(e) => onChange({ ...value, days: Math.max(1, Number(e.target.value) || 1) })}
        aria-label="Past N days"
      />
      <span className="text-xs text-muted-foreground">days</span>
    </>
  );
}

function SpecificRunPicker({
  protocolId,
  runIds,
  onChange,
}: {
  protocolId: string;
  runIds: string[];
  onChange: (ids: string[]) => void;
}) {
  // Opens on arrival: choosing "Specific runs" (or splitting by run) always
  // means picking runs next.
  const [open, setOpen] = useState(runIds.length === 0);
  // Flag an empty pick only once the list was closed without one, not the
  // moment the mode is chosen.
  const [touched, setTouched] = useState(false);
  const { data: runs, isLoading } = useRunsByProtocol(protocolId);
  const { data: members } = useWorkspaceMembers();

  const memberById = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of members ?? []) map.set(m.user_id, m.name || m.email);
    return map;
  }, [members]);

  // Newest experiment first — by run date, the same date "Latest run" uses;
  // upload time only breaks ties between runs from the same day.
  const sortedRuns = useMemo(
    () =>
      [...(runs ?? [])].sort(
        (a, b) => b.run_date.localeCompare(a.run_date) || b.created_at.localeCompare(a.created_at),
      ),
    [runs],
  );
  const differing = useMemo(() => differingConditionKeys(sortedRuns), [sortedRuns]);

  const selectedSet = useMemo(() => new Set(runIds), [runIds]);
  const selectedRuns = useMemo(
    () => sortedRuns.filter((r) => selectedSet.has(r.id)),
    [sortedRuns, selectedSet],
  );

  function toggle(id: string) {
    if (selectedSet.has(id)) {
      onChange(runIds.filter((rid) => rid !== id));
    } else {
      onChange([...runIds, id]);
    }
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) setTouched(true);
  }

  const triggerLabel = (() => {
    if (selectedRuns.length === 0) return "Choose one or more runs…";
    if (selectedRuns.length === 1) return runLabel(selectedRuns[0]);
    return `${selectedRuns.length} runs selected`;
  })();
  const invalid = touched && runIds.length === 0;

  return (
    <>
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex h-8 min-w-0 flex-1 items-center justify-between gap-1.5 rounded-md border border-input bg-transparent px-2 text-sm shadow-xs",
              selectedRuns.length === 0 && "text-muted-foreground",
              invalid && "border-destructive",
            )}
            aria-invalid={invalid}
          >
            {selectedRuns.length === 1 ? (
              <span className="flex min-w-0 items-center gap-1.5">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full shrink-0",
                    statusColor(selectedRuns[0].status, selectedRuns[0].is_locked),
                  )}
                  aria-hidden
                />
                <span className="truncate">{triggerLabel}</span>
              </span>
            ) : (
              <span className="truncate">{triggerLabel}</span>
            )}
            <ChevronsUpDown className="h-3 w-3 shrink-0 opacity-50" />
          </button>
        </PopoverTrigger>
        {/* As wide as the field and as tall as the screen allows: runs are
            told apart by their conditions and notes, which need the room. */}
        <PopoverContent
          className="flex max-h-(--radix-popover-content-available-height) w-[max(28rem,var(--radix-popover-trigger-width))] max-w-[calc(100vw-2rem)] flex-col p-0"
          align="start"
          collisionPadding={16}
        >
          <Command className="min-h-0">
            <CommandInput
              placeholder="Search by date, condition, scientist, barcode, notes…"
              className="h-8 text-sm"
            />
            <CommandList className="max-h-none min-h-0 flex-1">
              <CommandEmpty>
                {isLoading ? "Loading runs…" : "No runs for this protocol."}
              </CommandEmpty>
              <CommandGroup>
                {sortedRuns.map((run) => (
                  <RunOption
                    key={run.id}
                    run={run}
                    operatorName={memberById.get(run.operator) ?? "Unknown user"}
                    differing={differing}
                    checked={selectedSet.has(run.id)}
                    onToggle={() => toggle(run.id)}
                  />
                ))}
              </CommandGroup>
            </CommandList>
            {/* Footer — quick selection clears + count */}
            <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted-foreground">
              <span>
                {runIds.length} of {sortedRuns.length} selected
              </span>
              {runIds.length > 0 && (
                <button
                  type="button"
                  onClick={() => onChange([])}
                  className="inline-flex items-center gap-1 hover:text-foreground transition-colors"
                >
                  <X className="h-3 w-3" />
                  clear
                </button>
              )}
            </div>
          </Command>
        </PopoverContent>
      </Popover>
      {invalid && (
        <p className="basis-full pl-[6.375rem] text-xs text-destructive">Pick at least one run.</p>
      )}
    </>
  );
}

/** One run in the picker. Line 1 carries what sets the run apart (date and
 *  the conditions that differ between runs, then size); line 2 the who and
 *  what (status when not approved, scientist, notes, plates). */
function RunOption({
  run,
  operatorName,
  differing,
  checked,
  onToggle,
}: {
  run: Run;
  operatorName: string;
  differing: Set<string>;
  checked: boolean;
  onToggle: () => void;
}) {
  const conditions = formatConditionEntries(run.conditions);
  // Conditions that differ between runs lead, so the chip cap never hides them.
  const leading = Object.fromEntries(
    [...conditions]
      .sort((a, b) => Number(differing.has(b.key)) - Number(differing.has(a.key)))
      .map((e) => [e.key, e.value]),
  );
  const approved = run.is_locked || run.status === "approved";
  const statusLabel = RUN_STATUS_LABELS[run.status] ?? run.status;
  const barcodes = run.plate_barcodes?.join(", ");
  const details = [approved ? null : statusLabel, operatorName, run.notes?.trim(), barcodes]
    .filter(Boolean)
    .join(" · ");
  const haystack = [
    run.run_date,
    statusLabel,
    details,
    ...conditions.map((e) => `${e.key} ${e.value}`),
  ]
    .join(" ")
    .toLowerCase();

  return (
    <CommandItem
      value={`${run.id} ${haystack}`}
      // Keep the popover open so the chemist can pick
      // multiple runs without re-opening it each time.
      onSelect={onToggle}
      className="items-start py-2 text-sm"
    >
      <Checkbox
        checked={checked}
        tabIndex={-1}
        className="mt-0.5 h-3.5 w-3.5 shrink-0 pointer-events-none"
        aria-hidden
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={cn("h-2 w-2 shrink-0 rounded-full", statusColor(run.status, run.is_locked))}
            aria-hidden
          />
          <span className="shrink-0 font-mono text-xs">{run.run_date}</span>
          <ConditionChips conditions={leading} emptyFallback={null} className="min-w-0" />
          <span className="ml-auto shrink-0 whitespace-nowrap text-xs text-muted-foreground tabular-nums">
            {plural(run.molecule_count ?? 0, "cpd")}
            {/* Summary-imported runs have no plates — "0 plates" is noise. */}
            {run.plate_count > 0 && ` · ${plural(run.plate_count, "plate")}`}
          </span>
        </div>
        <p className="line-clamp-2 break-words text-xs text-muted-foreground">{details}</p>
      </div>
    </CommandItem>
  );
}
