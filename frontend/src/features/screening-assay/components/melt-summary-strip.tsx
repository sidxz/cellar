"use client";

import { cn } from "@/shared/lib/utils";
import { X } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import type { ResultFilter, WindowSummary } from "../lib/melt-results";

const NOTE = "font-medium text-amber-700 dark:text-amber-400";
const Note = ({ children }: { children: ReactNode }) => <span className={NOTE}>{children}</span>;
const STEP_ISSUES = "Step issues";

const Dot = () => (
  <span aria-hidden className="text-muted-foreground">
    ·
  </span>
);

/** A count that filters the grid; pressed while it is the active filter, and a
 *  second click clears it. */
function CountButton({
  value,
  active,
  count,
  tone,
  onToggle,
  children,
}: {
  value: Exclude<ResultFilter, null>;
  active: ResultFilter;
  count: number;
  tone?: string;
  onToggle: (f: ResultFilter) => void;
  children: ReactNode;
}) {
  const pressed = active === value;
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={count === 0 && !pressed}
      onClick={() => onToggle(pressed ? null : value)}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-transparent px-2 py-0.5 tabular-nums transition-colors",
        "hover:border-border hover:bg-muted disabled:pointer-events-none disabled:opacity-50",
        count > 0 && tone,
        pressed && "border-primary/40 bg-primary/10 text-foreground hover:bg-primary/15",
      )}
    >
      {children}
      {pressed && <X className="size-3" />}
    </button>
  );
}

/** The window's reference and counts; each count filters the grid. */
export function MeltSummaryStrip({
  summary,
  scope,
  perWindow,
  shown,
  onSelectReferences,
  hasRule,
  filter,
  onFilterChange,
}: {
  summary: WindowSummary;
  /** What the counts cover: the window's name, or "All windows" in Compare. */
  scope: string;
  /** Compare: each shown window's reference Tm. */
  perWindow?: readonly Pick<WindowSummary, "window" | "referenceTm">[];
  /** While a filter is on: the samples it shows, of all of them. */
  shown?: { count: number; total: number };
  /** Selects the reference positions, so their steps can be reviewed. */
  onSelectReferences?: () => void;
  /** The run's hit rule names a Tm or ΔTm readout, so hits are counted. */
  hasRule: boolean;
  filter: ResultFilter;
  onFilterChange: (f: ResultFilter) => void;
}) {
  const toggle = { active: filter, onToggle: onFilterChange };
  const labels = [...new Set(summary.referenceLabels)].join(", ");
  const reference = ["Reference", labels].filter(Boolean).join(" ");
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
      {perWindow ? (
        perWindow.every((w) => w.referenceTm == null) ? (
          <Note>No reference</Note>
        ) : (
          <span>
            {reference}
            {perWindow.map((w) => (
              <Fragment key={w.window}>
                {` · ${w.window} `}
                {w.referenceTm == null ? (
                  <Note>No reference</Note>
                ) : (
                  `${w.referenceTm.toFixed(1)} °C`
                )}
              </Fragment>
            ))}
          </span>
        )
      ) : summary.referenceTm == null ? (
        <Note>No reference</Note>
      ) : (
        <span>
          {`${reference} ${summary.referenceTm.toFixed(1)} °C (n=${summary.referenceCount})`}
        </span>
      )}
      {summary.referencesDiffer && <Note>References disagree in step count</Note>}
      {summary.referenceUnreviewed &&
        (onSelectReferences ? (
          <button
            type="button"
            className={cn(NOTE, "underline-offset-4 hover:underline")}
            title="Select the reference to review its steps"
            onClick={onSelectReferences}
          >
            Reference not reviewed
          </button>
        ) : (
          <Note>Reference not reviewed</Note>
        ))}
      <Dot />
      <span className="font-medium">{scope}</span>
      <Dot />
      <CountButton
        value="needs_review"
        count={summary.needsReview}
        tone="font-medium text-amber-700 dark:text-amber-400"
        {...toggle}
      >
        {`${STEP_ISSUES} ${summary.needsReview}`}
      </CountButton>
      <CountButton value="provisional" count={summary.provisional} {...toggle}>
        {`Provisional ${summary.provisional}`}
      </CountButton>
      {hasRule && (
        <>
          <Dot />
          <span className="inline-flex items-center gap-1.5">
            <CountButton value="hits" count={summary.hits} tone="font-medium" {...toggle}>
              {`Hits ${summary.hits}`}
            </CountButton>
            <span className="text-muted-foreground">(</span>
            <CountButton
              value="up"
              count={summary.up}
              tone="text-blue-700 dark:text-blue-300"
              {...toggle}
            >
              {`${summary.up} up`}
            </CountButton>
            <span aria-hidden className="text-muted-foreground">
              ·
            </span>
            <CountButton
              value="down"
              count={summary.down}
              tone="text-red-700 dark:text-red-300"
              {...toggle}
            >
              {`${summary.down} down`}
            </CountButton>
            <span className="text-muted-foreground">)</span>
          </span>
        </>
      )}
      {shown && (
        <span className="text-muted-foreground">{`${shown.count} of ${shown.total} samples`}</span>
      )}
    </div>
  );
}
