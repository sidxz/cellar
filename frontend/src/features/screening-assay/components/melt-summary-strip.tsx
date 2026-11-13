"use client";

import { Input } from "@/shared/components/ui/input";
import { cn } from "@/shared/lib/utils";
import { X } from "lucide-react";
import { type ReactNode, useState } from "react";
import type { ResultFilter, WindowSummary } from "../lib/melt-results";

const Note = ({ children }: { children: ReactNode }) => (
  <span className="font-medium text-amber-700 dark:text-amber-400">{children}</span>
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
  threshold,
  onThresholdChange,
  filter,
  onFilterChange,
}: {
  summary: WindowSummary;
  threshold: number;
  onThresholdChange: (t: number) => void;
  filter: ResultFilter;
  onFilterChange: (f: ResultFilter) => void;
}) {
  // The field's text while typing; a usable value applies at once, the rest on blur.
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft !== null) onThresholdChange(Number(draft));
    setDraft(null);
  };
  const toggle = { active: filter, onToggle: onFilterChange };
  const labels = [...new Set(summary.referenceLabels)].join(", ");
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
      {summary.referenceTm == null ? (
        <Note>No reference</Note>
      ) : (
        <span>
          {`Reference ${labels} ${summary.referenceTm.toFixed(1)} °C (n=${summary.referenceCount})`}
        </span>
      )}
      {summary.referencesDiffer && <Note>References disagree in step count</Note>}
      {summary.referenceUnreviewed && <Note>Reference not reviewed</Note>}
      <span aria-hidden className="text-muted-foreground">
        ·
      </span>
      <CountButton
        value="needs_review"
        count={summary.needsReview}
        tone="font-medium text-amber-700 dark:text-amber-400"
        {...toggle}
      >
        {`Needs review ${summary.needsReview}`}
      </CountButton>
      <CountButton value="provisional" count={summary.provisional} {...toggle}>
        {`Provisional ${summary.provisional}`}
      </CountButton>
      <span aria-hidden className="text-muted-foreground">
        ·
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="text-muted-foreground">|ΔTm| ≥</span>
        <Input
          type="number"
          aria-label="Shift threshold (°C)"
          min={0}
          step={0.5}
          className="h-7 w-16 px-2 text-sm tabular-nums"
          value={draft ?? threshold}
          onChange={(e) => {
            setDraft(e.target.value);
            if (Number(e.target.value) > 0) onThresholdChange(Number(e.target.value));
          }}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
          }}
        />
        <span className="text-muted-foreground">°C:</span>
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
      </span>
    </div>
  );
}
