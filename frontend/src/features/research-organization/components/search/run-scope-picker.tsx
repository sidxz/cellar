"use client";

import { useMemo, useState } from "react";
import { Check, ChevronsUpDown, X } from "lucide-react";
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
} from "@/shared/components/ui/command";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { cn } from "@/shared/lib/utils";
import { useRunsByProtocol } from "@/features/screening-assay/hooks/use-runs";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import type { Run, RunStatus } from "@/features/screening-assay/types";
import type { RunScope, RunScopeMode } from "../../types";

const MODE_OPTIONS: { value: RunScopeMode; label: string }[] = [
  { value: "any", label: "Any run" },
  { value: "latest", label: "Latest run" },
  { value: "all", label: "All runs" },
  { value: "date_range", label: "Date range" },
  { value: "past_n_days", label: "Past N days" },
  { value: "specific", label: "Specific run" },
];

/** Status dot driven by run.status + is_locked. */
function statusColor(status: RunStatus, isLocked: boolean): string {
  if (isLocked || status === "approved") return "bg-emerald-500";
  if (status === "rejected") return "bg-red-500";
  if (status === "completed") return "bg-amber-500";
  return "bg-muted-foreground/40";
}

// inline: custom date format — produces "2026-05-12 14:30" (ISO date + 24-h time),
// which is more compact than the shared formatDateTime "May 12, 2026, 2:30 PM".
function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = d.toISOString().slice(0, 10);
  const time = d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${date} ${time}`;
}

function runIdentifier(run: Run): string {
  if (run.plate_barcodes?.length) return run.plate_barcodes[0];
  if (run.notes && run.notes.trim().length > 0) {
    const trimmed = run.notes.trim();
    return trimmed.length > 32 ? `${trimmed.slice(0, 32)}…` : trimmed;
  }
  return `Run ${run.run_date}`;
}

function conditionsSummary(
  conditions: Record<string, unknown> | null
): string | null {
  if (!conditions) return null;
  const entries = Object.entries(conditions).filter(
    ([, v]) => v !== null && v !== ""
  );
  if (entries.length === 0) return null;
  return entries
    .slice(0, 4)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(" · ");
}

interface RunScopePickerProps {
  protocolId: string;
  value: RunScope | undefined;
  onChange: (next: RunScope | undefined) => void;
}

export function RunScopePicker({
  protocolId,
  value,
  onChange,
}: RunScopePickerProps) {
  const mode: RunScopeMode = value?.mode ?? "any";

  function setMode(next: RunScopeMode) {
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
      <span className="text-sm text-muted-foreground shrink-0 w-16">runs</span>

      <Select value={mode} onValueChange={(v) => setMode(v as RunScopeMode)}>
        <SelectTrigger className="h-8 w-32 text-sm shrink-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {MODE_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value} className="text-sm">
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {value?.mode === "date_range" && (
        <DateRangeInputs value={value} onChange={onChange} />
      )}

      {value?.mode === "past_n_days" && (
        <PastNDaysInput value={value} onChange={onChange} />
      )}

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
        onChange={(e) =>
          onChange({ ...value, date_from: e.target.value || undefined })
        }
        aria-label="From date"
      />
      <span className="text-xs text-muted-foreground">→</span>
      <Input
        type="date"
        className="h-8 w-36 text-sm"
        value={value.date_to ?? ""}
        onChange={(e) =>
          onChange({ ...value, date_to: e.target.value || undefined })
        }
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
        onChange={(e) =>
          onChange({ ...value, days: Math.max(1, Number(e.target.value) || 1) })
        }
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
  const [open, setOpen] = useState(false);
  const { data: runs, isLoading } = useRunsByProtocol(protocolId);
  const { data: members } = useWorkspaceMembers();

  const memberById = useMemo(() => {
    const map = new Map<string, string>();
    (members ?? []).forEach((m) => map.set(m.user_id, m.name || m.email));
    return map;
  }, [members]);

  const sortedRuns = useMemo(() => {
    if (!runs) return [];
    return [...runs].sort((a, b) =>
      a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0
    );
  }, [runs]);

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

  const triggerLabel = (() => {
    if (selectedRuns.length === 0) return "Choose runs…";
    if (selectedRuns.length === 1) return runIdentifier(selectedRuns[0]);
    return `${selectedRuns.length} runs selected`;
  })();
  const invalid = runIds.length === 0;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex h-8 min-w-0 flex-1 items-center justify-between gap-1.5 rounded-md border border-input bg-transparent px-2 text-sm shadow-xs",
            invalid && "border-destructive text-muted-foreground"
          )}
          aria-invalid={invalid}
        >
          {selectedRuns.length === 1 ? (
            <span className="flex min-w-0 items-center gap-1.5">
              <span
                className={cn(
                  "h-2 w-2 rounded-full shrink-0",
                  statusColor(selectedRuns[0].status, selectedRuns[0].is_locked)
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
      <PopoverContent
        className="p-0 w-[28rem] max-w-[calc(100vw-2rem)]"
        align="start"
      >
        <TooltipProvider delayDuration={250}>
          <Command>
            <CommandInput
              placeholder="Search by date, scientist, barcode, notes…"
              className="h-8 text-sm"
            />
            <CommandList className="max-h-80">
              <CommandEmpty>
                {isLoading ? "Loading runs…" : "No runs for this protocol."}
              </CommandEmpty>
              <CommandGroup>
                {sortedRuns.map((run) => {
                  const operatorName =
                    memberById.get(run.operator) ?? "Unknown user";
                  const identifier = runIdentifier(run);
                  const conditions = conditionsSummary(run.conditions);
                  const checked = selectedSet.has(run.id);
                  const haystack = [
                    run.run_date,
                    operatorName,
                    identifier,
                    run.notes ?? "",
                    ...(run.plate_barcodes ?? []),
                    conditions ?? "",
                  ]
                    .join(" ")
                    .toLowerCase();
                  return (
                    <CommandItem
                      key={run.id}
                      value={`${run.id} ${haystack}`}
                      // Keep the popover open so the chemist can pick
                      // multiple runs without re-opening it each time.
                      onSelect={() => toggle(run.id)}
                      className="text-sm py-1.5"
                    >
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className="flex w-full min-w-0 items-center gap-2">
                            <Checkbox
                              checked={checked}
                              tabIndex={-1}
                              className="h-3.5 w-3.5 shrink-0 pointer-events-none"
                              aria-hidden
                            />
                            <span
                              className={cn(
                                "h-2 w-2 rounded-full shrink-0",
                                statusColor(run.status, run.is_locked)
                              )}
                              aria-hidden
                            />
                            <span className="font-mono text-xs text-muted-foreground shrink-0 whitespace-nowrap">
                              {formatDateTime(run.created_at)}
                            </span>
                            <span className="min-w-0 flex-1 truncate">
                              {operatorName}
                            </span>
                            <span className="min-w-0 flex-1 truncate font-mono text-xs">
                              {identifier}
                            </span>
                            <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground tabular-nums">
                              {run.molecule_count} cpd
                              {run.molecule_count === 1 ? "" : "s"}
                            </span>
                          </div>
                        </TooltipTrigger>
                        <TooltipContent
                          side="bottom"
                          align="start"
                          className="max-w-sm"
                        >
                          <div className="space-y-1 text-xs">
                            <div>
                              <strong>Status:</strong> {run.status}
                              {run.is_locked ? " · locked" : ""}
                            </div>
                            {run.notes && (
                              <div>
                                <strong>Notes:</strong> {run.notes}
                              </div>
                            )}
                            {conditions && (
                              <div>
                                <strong>Conditions:</strong> {conditions}
                              </div>
                            )}
                            {run.plate_barcodes &&
                              run.plate_barcodes.length > 1 && (
                                <div>
                                  <strong>Plates:</strong>{" "}
                                  {run.plate_barcodes.join(", ")}
                                </div>
                              )}
                            <div>
                              <strong>Plates:</strong> {run.plate_count} ·{" "}
                              <strong>Compounds:</strong> {run.molecule_count}
                            </div>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </CommandItem>
                  );
                })}
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
        </TooltipProvider>
      </PopoverContent>
    </Popover>
  );
}
