"use client";

import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { cn } from "@/shared/lib/utils";
import type { ReactNode } from "react";
import type { ResultFilter, ResultRow, WindowSummary } from "../lib/melt-results";
import { formatDelta, formatTm } from "../lib/melt-results";
import { WELL_TYPE_LABELS, type WellType } from "../types";

/** Controls stay available while the compound table is filtered or scrolled. */
export function ThermalResultsSummary({
  rows,
  windowNames,
  summaries,
  unreviewed,
  issues,
  filter,
  onFilterChange,
  onSelect,
  hitRule,
}: {
  rows: readonly ResultRow[];
  windowNames: readonly string[];
  summaries: readonly WindowSummary[];
  unreviewed: number;
  issues: number;
  filter: ResultFilter;
  onFilterChange: (filter: ResultFilter) => void;
  onSelect: (ids: string[]) => void;
  hitRule?: ReactNode;
}) {
  const references = rows.filter((r) => r.wellType === "reference");
  const controls = rows.filter((r) => !r.isSample && r.wellType !== "reference");
  const controlsByRole = new Map<string, ResultRow[]>();
  for (const row of controls)
    controlsByRole.set(row.wellType, [...(controlsByRole.get(row.wellType) ?? []), row]);
  const toggle = (value: ResultFilter) => onFilterChange(filter === value ? null : value);
  const control = (row: ResultRow) => (
    <div key={row.wellId} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
      <span className="font-medium">{row.sampleText}</span>
      {windowNames.map((name) => {
        const cell = row.cells[name];
        return (
          <span key={name} className="tabular-nums">
            {windowNames.length > 1 && <span className="text-muted-foreground">{name} </span>}
            {cell?.deltaTm != null
              ? `ΔTm ${formatDelta(cell.deltaTm)} °C`
              : cell?.tm != null
                ? `Tm ${formatTm(cell.tm)} °C`
                : "No Tm"}
            {cell?.deltaTm != null && cell.tm != null && (
              <span className="ml-1 text-xs text-muted-foreground">{`· Tm ${formatTm(cell.tm)} °C`}</span>
            )}
          </span>
        );
      })}
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-6 px-2 text-xs"
        aria-label={`View ${row.sampleText} ${(WELL_TYPE_LABELS[row.wellType as WellType] ?? row.wellType).toLowerCase()} trace at ${row.position}`}
        title={`${row.position} · ${WELL_TYPE_LABELS[row.wellType as WellType] ?? row.wellType}`}
        onClick={() => onSelect([row.wellId])}
      >
        View trace
      </Button>
    </div>
  );

  return (
    <section
      aria-label="Thermal analysis summary"
      className="grid gap-x-6 gap-y-3 rounded-lg border bg-muted/20 px-4 py-2.5 sm:grid-cols-2 xl:grid-cols-[1.1fr_1.1fr_1fr_1fr]"
    >
      <div className="min-w-0 space-y-1">
        <p className="text-xs font-medium text-muted-foreground">Reference</p>
        {references.length > 0 ? (
          <button
            type="button"
            className="text-left text-sm hover:text-primary"
            onClick={() => onSelect(references.map((r) => r.wellId))}
          >
            <span className="font-medium">
              {[...new Set(references.map((r) => r.sampleText))].join(", ")}
            </span>
            {summaries.map((s) => (
              <span key={s.window} className="ml-2 inline-block tabular-nums">
                {summaries.length > 1 && `${s.window} `}
                {s.referenceTm == null ? "No reference Tm" : `${formatTm(s.referenceTm)} °C`}
                <span className="ml-1 text-muted-foreground">{`(n=${s.referenceCount})`}</span>
              </span>
            ))}
          </button>
        ) : (
          <p className="text-sm text-amber-700 dark:text-amber-400">No reference</p>
        )}
        {summaries.some((s) => s.referenceUnreviewed) && (
          <p className="text-xs text-amber-700 dark:text-amber-400">Reference peak unreviewed</p>
        )}
        {summaries.some((s) => s.referencesDiffer) && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            References have different numbers of peaks
          </p>
        )}
      </div>
      <div className="min-w-0 space-y-1">
        <p className="text-xs font-medium text-muted-foreground">Controls</p>
        {controls.length === 0 && <p className="text-sm text-muted-foreground">Not recorded</p>}
        {[...controlsByRole].map(([role, entries]) => {
          const roleLabel = WELL_TYPE_LABELS[role as WellType] ?? role;
          return (
            <section key={role} aria-label={roleLabel} className="space-y-1">
              <p className="text-xs text-muted-foreground">{roleLabel}</p>
              {entries.slice(0, 2).map(control)}
              {entries.length > 2 && (
                <Popover>
                  <PopoverTrigger asChild>
                    <button type="button" className="text-xs text-primary hover:underline">
                      View all {roleLabel.toLowerCase()} positions ({entries.length})
                    </button>
                  </PopoverTrigger>
                  <PopoverContent className="max-h-80 w-auto max-w-[90vw] space-y-3 overflow-y-auto">
                    {entries.map(control)}
                  </PopoverContent>
                </Popover>
              )}
            </section>
          );
        })}
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">Peak review</p>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <button
            type="button"
            disabled={unreviewed === 0 && filter !== "unreviewed"}
            aria-pressed={filter === "unreviewed"}
            title="Compounds with an unreviewed peak in these transitions. Filters the table to them."
            className={cn(
              "block text-sm font-medium tabular-nums hover:text-primary disabled:text-muted-foreground",
              filter === "unreviewed" && "text-primary underline underline-offset-4",
            )}
            onClick={() => toggle("unreviewed")}
          >
            {unreviewed} unreviewed {unreviewed === 1 ? "compound" : "compounds"}
          </button>
          <button
            type="button"
            disabled={issues === 0 && filter !== "needs_review"}
            aria-pressed={filter === "needs_review"}
            className={cn(
              "text-xs tabular-nums text-muted-foreground hover:text-primary",
              issues > 0 && "text-amber-700 dark:text-amber-400",
              filter === "needs_review" && "underline underline-offset-4",
            )}
            onClick={() => toggle("needs_review")}
          >
            {issues} {issues === 1 ? "peak issue" : "peak issues"}
          </button>
        </div>
      </div>
      <div className="min-w-0 space-y-1">
        <p className="text-xs font-medium text-muted-foreground">Hit rule</p>
        {hitRule ?? <p className="text-sm text-muted-foreground">Not set</p>}
      </div>
    </section>
  );
}
