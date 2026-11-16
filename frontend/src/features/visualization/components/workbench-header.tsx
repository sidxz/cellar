"use client";

import { useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import { useRun, useRunsByProtocol } from "@/features/screening-assay/hooks/use-runs";
import type { Run } from "@/features/screening-assay/types";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { Switch } from "@/shared/components/ui/switch";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { ArrowLeft, ChevronDown, Plus, Redo2, Undo2, X } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useId, useMemo, useState } from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import {
  isCrossProtocol,
  isTestedInAll,
  testedCount,
  testedInAllFilters,
  testedKey,
} from "../lib/cross-protocol";
import { column, uniqueCompounds } from "../lib/dataset";
import type { Carry } from "../lib/level-switch";
import { LEVELS, LEVEL_ORDER } from "../lib/levels";
import { conditionsText, newestFirst, runLabel } from "../lib/runs";
import { useWorkbench, useWorkbenchStore } from "../store/workbench-context";
import { canRedo, canUndo } from "../store/workbench-store";
import type { ComparedProtocol, Dataset, DatasetSource, Level } from "../types";
import { AddProtocolDialog } from "./add-protocol-dialog";
import { RunPickerDialog } from "./run-picker-dialog";

const fmt = (n: number) => n.toLocaleString();
/** Protocols a view can compare with its own. */
const MAX_COMPARED = 4;
const LEVEL_LOCKED =
  "Comparing protocols works at the Compounds level only — remove the added protocols to switch.";

/** What the workbench shows: a source at a row level. */
export type View = { source: DatasetSource; level: Level };

/** ``all`` runs newest first, only ``runIds`` when named. */
function chosenRuns(all: readonly Run[] | undefined, runIds?: string[]): Run[] {
  const sorted = newestFirst(all ?? []);
  const ids = runIds && new Set(runIds);
  return ids ? sorted.filter((r) => ids.has(r.id)) : sorted;
}

/** The runs a source loads, newest first, plus the run (run source) and every run of the
 * protocol (protocol source) they were picked from. */
export function useSourceRuns(source: DatasetSource) {
  const { data: run } = useRun(source.kind === "run" ? source.runId : undefined);
  const { data: protocolRuns } = useRunsByProtocol(
    source.kind === "protocol" ? source.protocolId : undefined,
  );
  const runs = useMemo(() => {
    if (source.kind === "run") return run ? [run] : [];
    return chosenRuns(protocolRuns, source.runIds);
  }, [source, run, protocolRuns]);
  return { run, protocolRuns, runs };
}

/** A protocol's chip: its name and runs, opening the list of those runs with "Change runs…"
 * (``onRunsChange`` gets the runs picked, undefined = every run). */
function RunsChip({
  name,
  summary,
  runs,
  protocolId,
  runIds,
  level,
  onRunsChange,
}: {
  name: string;
  summary: string;
  runs: Run[];
  protocolId?: string;
  runIds?: string[];
  level: Level;
  onRunsChange: (runIds: string[] | undefined) => void;
}) {
  const nameOf = useMemberNames();
  const [pickerOpen, setPickerOpen] = useState(false);
  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button size="sm" variant="outline" className="min-w-0">
            <span className="truncate font-medium">{name}</span>
            <span className="text-muted-foreground">{` · ${summary}`}</span>
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[28rem] p-2">
          <ul className="max-h-72 space-y-1 overflow-auto text-sm">
            {runs.map((r) => (
              <li key={r.id} className="flex items-center gap-2 rounded px-1.5 py-1">
                <span className="whitespace-nowrap">{runLabel(r, nameOf)}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  {conditionsText(r)}
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {r.plate_count} {r.plate_count === 1 ? "plate" : "plates"}
                </span>
                <StatusBadge status={r.status} />
              </li>
            ))}
          </ul>
          {protocolId && (
            <div className="border-t pt-2">
              <Button size="sm" variant="outline" onClick={() => setPickerOpen(true)}>
                Change runs…
              </Button>
            </div>
          )}
        </PopoverContent>
      </Popover>
      {pickerOpen && protocolId && (
        <RunPickerDialog
          protocolId={protocolId}
          initialRunIds={runIds}
          level={level}
          open
          onOpenChange={setPickerOpen}
          onConfirm={onRunsChange}
        />
      )}
    </>
  );
}

/** A compared protocol: its chip (runs, compounds tested in it) and ✕. */
function ComparedChip({
  entry,
  level,
  ds,
  onRunsChange,
  onRemove,
}: {
  entry: ComparedProtocol;
  level: Level;
  ds?: Dataset;
  onRunsChange: (runIds: string[] | undefined) => void;
  onRemove: () => void;
}) {
  const { data: protocol } = useProtocol(entry.protocolId);
  const { data: all } = useRunsByProtocol(entry.protocolId);
  const runs = useMemo(() => chosenRuns(all, entry.runIds), [all, entry.runIds]);
  const name = protocol?.name ?? "…";
  const tested =
    ds && column(ds, testedKey(entry.protocolId))
      ? ` · ${fmt(testedCount(ds, entry.protocolId))} of ${fmt(ds.row_count)} compounds tested`
      : "";
  return (
    <span className="inline-flex min-w-0 items-center">
      <RunsChip
        name={name}
        summary={`${runs.length} of ${all?.length ?? "…"} runs${tested}`}
        runs={runs}
        protocolId={entry.protocolId}
        runIds={entry.runIds}
        level={level}
        onRunsChange={onRunsChange}
      />
      <Button
        size="icon"
        variant="ghost"
        className="h-8 w-8"
        aria-label={`Remove ${name}`}
        title={`Remove ${name}`}
        onClick={onRemove}
      >
        <X className="h-4 w-4" />
      </Button>
    </span>
  );
}

/** Header row 1: back link, the source chip whose popover lists the loaded runs, and (for a
 * protocol) one chip per compared protocol plus "Add protocol". ``onChange`` gets the new
 * source; ``ds`` (once loaded) gives each compared protocol's tested count. */
export function SourceBar({
  source,
  level,
  ds,
  onChange,
}: {
  source: DatasetSource;
  level: Level;
  ds?: Dataset;
  onChange: (source: DatasetSource) => void;
}) {
  const [adding, setAdding] = useState(false);
  const { run, protocolRuns, runs } = useSourceRuns(source);
  const protocolId = source.kind === "protocol" ? source.protocolId : run?.protocol_id;
  const { data: protocol } = useProtocol(protocolId);

  const name = protocol?.name ?? "…";
  const back =
    source.kind === "run"
      ? { href: `/assays/runs/${source.runId}`, label: run ? `Run ${run.run_date}` : "Run" }
      : { href: `/assays/protocols/${source.protocolId}`, label: name };
  const summary =
    source.kind === "run"
      ? `run ${run?.run_date ?? "…"}`
      : `${runs.length} of ${protocolRuns?.length ?? "…"} runs`;
  const compare = source.kind === "protocol" ? (source.compare ?? []) : [];
  const setCompare = (next: ComparedProtocol[]) =>
    source.kind === "protocol" && onChange({ ...source, compare: next.length ? next : undefined });
  const addReason =
    level !== "compounds"
      ? "Switch to Compounds to compare protocols"
      : compare.length >= MAX_COMPARED
        ? `Up to ${MAX_COMPARED + 1} protocols`
        : null;

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
      <Link
        href={back.href}
        className="inline-flex shrink-0 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        {back.label}
      </Link>
      <RunsChip
        name={name}
        summary={summary}
        runs={runs}
        protocolId={protocolId}
        runIds={source.kind === "run" ? [source.runId] : source.runIds}
        level={level}
        onRunsChange={(runIds) =>
          protocolId &&
          onChange(
            source.kind === "protocol"
              ? { ...source, runIds }
              : { kind: "protocol", protocolId, runIds },
          )
        }
      />
      {compare.map((c) => (
        <ComparedChip
          key={c.protocolId}
          entry={c}
          level={level}
          ds={ds}
          onRunsChange={(runIds) =>
            setCompare(
              compare.map((x) =>
                x === c ? { protocolId: c.protocolId, ...(runIds && { runIds }) } : x,
              ),
            )
          }
          onRemove={() => setCompare(compare.filter((x) => x !== c))}
        />
      ))}
      {source.kind === "protocol" && (
        <Button
          size="sm"
          variant="ghost"
          // Hoverable while disabled, so the title says why.
          className="disabled:pointer-events-auto"
          disabled={addReason !== null}
          title={addReason ?? undefined}
          onClick={() => setAdding(true)}
        >
          <Plus className="h-4 w-4" />
          Add protocol
        </Button>
      )}
      {adding && source.kind === "protocol" && (
        <AddProtocolDialog
          open
          onOpenChange={setAdding}
          exclude={[source.protocolId, ...compare.map((c) => c.protocolId)]}
          onAdd={(c) => setCompare([...compare, c])}
        />
      )}
    </div>
  );
}

/** The row-level switcher (one button per level) and what one row is at ``level``. While
 * ``source`` compares protocols, only Compounds can be chosen. */
export function LevelSwitcher({
  level,
  source,
  onChange,
}: {
  level: Level;
  source: DatasetSource;
  onChange: (level: Level) => void;
}) {
  const locked = source.kind === "protocol" && Boolean(source.compare?.length);
  return (
    <div className="flex items-center gap-2">
      <fieldset className="inline-flex rounded-md border p-0.5">
        <legend className="sr-only">Row level</legend>
        {LEVEL_ORDER.map((l) => {
          const off = locked && l !== "compounds";
          return (
            <Button
              key={l}
              size="sm"
              variant={l === level ? "secondary" : "ghost"}
              // Hoverable while disabled, so the title says why.
              className="h-7 disabled:pointer-events-auto"
              aria-pressed={l === level}
              disabled={off}
              title={off ? LEVEL_LOCKED : undefined}
              onClick={() => l !== level && onChange(l)}
            >
              {LEVELS[l].label}
            </Button>
          );
        })}
      </fieldset>
      <span className="text-xs text-muted-foreground">{LEVELS[level].caption}</span>
    </div>
  );
}

/** "Only compounds tested in both / in all n protocols": rail filters keeping "Tested" on
 * each compared protocol's tested column, added or removed as one undo step. */
function TestedInAllSwitch({ ds }: { ds: Dataset }) {
  const filters = useWorkbench((s) => s.filters);
  const setFilters = useWorkbench((s) => s.setFilters);
  const id = useId();
  const n = ds.protocols?.length ?? 0;
  const toggle = (on: boolean) => {
    const tested = testedInAllFilters(ds);
    const keys = new Set(tested.map((f) => f.key));
    const rest = filters.filter((f) => !(f.kind === "category" && keys.has(f.key)));
    setFilters(on ? [...rest, ...tested] : rest);
  };
  return (
    <div className="flex items-center gap-2 text-sm">
      <Switch id={id} checked={isTestedInAll(filters, ds)} onCheckedChange={toggle} />
      <label htmlFor={id}>
        {n === 2 ? "Only compounds tested in both" : `Only compounds tested in all ${n} protocols`}
      </label>
    </div>
  );
}

interface WorkbenchHeaderProps {
  source: DatasetSource;
  ds: Dataset;
  level: Level;
  /** Called with the next source and level and the plots, filters and selection to take. */
  onViewChange: (next: View, carry: Carry) => void;
  /** Export menu. */
  exportMenu?: ReactNode;
  /** "+ Add plot (n/4)" menu. */
  addPlotMenu?: ReactNode;
  /** "Add columns" menu (chemistry column sets), quieter than Add plot. */
  addColumnsMenu?: ReactNode;
  /** The saved view's name and its Save controls, at the end of row 1. */
  viewControls?: ReactNode;
}

/** Two rows: the source and the saved view's controls (row 1), then grain, counts, history
 * and the export, column and plot menus. */
export function WorkbenchHeader({
  source,
  ds,
  level,
  onViewChange,
  exportMenu,
  addPlotMenu,
  addColumnsMenu,
  viewControls,
}: WorkbenchHeaderProps) {
  const mask = usePassMask(ds);
  const store = useWorkbenchStore();
  const undoable = useWorkbench(canUndo);
  const redoable = useWorkbench(canRedo);
  const undo = useWorkbench((s) => s.undo);
  const redo = useWorkbench((s) => s.redo);

  const { passing, compounds } = useMemo(() => {
    const rows: number[] = [];
    for (let i = 0; i < mask.length; i++) if (mask[i]) rows.push(i);
    return { passing: rows.length, compounds: uniqueCompounds(ds, rows).length };
  }, [ds, mask]);

  // Read when the view changes, so selecting rows doesn't re-render the header.
  const take = (): Carry => {
    const { panels, filters, selection } = store.getState();
    return { panels, filters, selectedIds: [...selection], columns: ds.columns };
  };

  const { one, many } = LEVELS[level];
  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="min-w-0 flex-1">
          <SourceBar
            source={source}
            level={level}
            ds={ds}
            onChange={(next) => onViewChange({ source: next, level }, take())}
          />
        </div>
        {viewControls}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <LevelSwitcher
          level={level}
          source={source}
          onChange={(next) => onViewChange({ source, level: next }, take())}
        />
        {isCrossProtocol(ds) && <TestedInAllSwitch ds={ds} />}
        <span className="h-4 w-px bg-border" />
        <span className="tabular-nums">
          {`${fmt(passing)} / ${fmt(ds.row_count)} ${ds.row_count === 1 ? one : many}`}
          {/* At Compounds the rows are the compounds. */}
          {level !== "compounds" &&
            ` · ${fmt(compounds)} ${compounds === 1 ? "compound" : "compounds"}`}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            aria-label="Undo"
            title="Undo"
            disabled={!undoable}
            onClick={undo}
          >
            <Undo2 className="h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            aria-label="Redo"
            title="Redo"
            disabled={!redoable}
            onClick={redo}
          >
            <Redo2 className="h-4 w-4" />
          </Button>
          {exportMenu}
          {addColumnsMenu}
          {addPlotMenu}
        </div>
      </div>
    </header>
  );
}
