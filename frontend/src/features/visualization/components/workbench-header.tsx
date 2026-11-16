"use client";

import { useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import { useRun, useRunsByProtocol } from "@/features/screening-assay/hooks/use-runs";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { ArrowLeft, ChevronDown, Redo2, Undo2 } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useMemo, useState } from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import { uniqueCompounds } from "../lib/dataset";
import type { Carry } from "../lib/level-switch";
import { LEVELS, LEVEL_ORDER } from "../lib/levels";
import { conditionsText, newestFirst, runLabel } from "../lib/runs";
import { useWorkbench } from "../store/workbench-context";
import { canRedo, canUndo } from "../store/workbench-store";
import type { Dataset, DatasetSource, Level } from "../types";
import { RunPickerDialog } from "./run-picker-dialog";

const fmt = (n: number) => n.toLocaleString();

/** The runs a source loads, newest first, plus the run (run source) and every run of the
 * protocol (protocol source) they were picked from. */
export function useSourceRuns(source: DatasetSource) {
  const { data: run } = useRun(source.kind === "run" ? source.runId : undefined);
  const { data: protocolRuns } = useRunsByProtocol(
    source.kind === "protocol" ? source.protocolId : undefined,
  );
  const runs = useMemo(() => {
    if (source.kind === "run") return run ? [run] : [];
    const all = newestFirst(protocolRuns ?? []);
    const ids = source.runIds ? new Set(source.runIds) : null;
    return ids ? all.filter((r) => ids.has(r.id)) : all;
  }, [source, run, protocolRuns]);
  return { run, protocolRuns, runs };
}

/** Header row 1: back link, and the source chip whose popover lists the loaded runs. */
export function SourceBar({ source, level }: { source: DatasetSource; level: Level }) {
  const nameOf = useMemberNames();
  const [pickerOpen, setPickerOpen] = useState(false);
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

  return (
    <div className="flex min-w-0 items-center gap-3">
      <Link
        href={back.href}
        className="inline-flex shrink-0 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        {back.label}
      </Link>
      <Popover>
        <PopoverTrigger asChild>
          <Button size="sm" variant="outline" className="min-w-0">
            <span className="truncate font-medium">{name}</span>
            <span className="text-muted-foreground">· {summary}</span>
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
          initialRunIds={runs.map((r) => r.id)}
          level={level}
          open
          onOpenChange={setPickerOpen}
        />
      )}
    </div>
  );
}

/** The row-level switcher (one button per level) and what one row is at ``level``. */
export function LevelSwitcher({
  level,
  onChange,
}: {
  level: Level;
  onChange: (level: Level) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <fieldset className="inline-flex rounded-md border p-0.5">
        <legend className="sr-only">Row level</legend>
        {LEVEL_ORDER.map((l) => (
          <Button
            key={l}
            size="sm"
            variant={l === level ? "secondary" : "ghost"}
            className="h-7"
            aria-pressed={l === level}
            onClick={() => l !== level && onChange(l)}
          >
            {LEVELS[l].label}
          </Button>
        ))}
      </fieldset>
      <span className="text-xs text-muted-foreground">{LEVELS[level].caption}</span>
    </div>
  );
}

interface WorkbenchHeaderProps {
  source: DatasetSource;
  ds: Dataset;
  level: Level;
  /** Called with the plots, filters and selection size to take to ``level``. */
  onLevelChange: (level: Level, carry: Carry) => void;
  /** Export menu. */
  exportMenu?: ReactNode;
  /** "+ Add plot (n/4)" menu. */
  addPlotMenu?: ReactNode;
}

/** Two rows: the source (row 1), then grain, counts, history and the plot/export menus. */
export function WorkbenchHeader({
  source,
  ds,
  level,
  onLevelChange,
  exportMenu,
  addPlotMenu,
}: WorkbenchHeaderProps) {
  const mask = usePassMask(ds);
  const panels = useWorkbench((s) => s.panels);
  const filters = useWorkbench((s) => s.filters);
  const selected = useWorkbench((s) => s.selection.size);
  const undoable = useWorkbench(canUndo);
  const redoable = useWorkbench(canRedo);
  const undo = useWorkbench((s) => s.undo);
  const redo = useWorkbench((s) => s.redo);

  const { passing, compounds } = useMemo(() => {
    const rows: number[] = [];
    for (let i = 0; i < mask.length; i++) if (mask[i]) rows.push(i);
    return { passing: rows.length, compounds: uniqueCompounds(ds, rows).length };
  }, [ds, mask]);

  const { one, many } = LEVELS[level];
  return (
    <header className="space-y-2">
      <SourceBar source={source} level={level} />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <LevelSwitcher
          level={level}
          onChange={(next) =>
            onLevelChange(next, { panels, filters, selected, columns: ds.columns })
          }
        />
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
          {addPlotMenu}
        </div>
      </div>
    </header>
  );
}
