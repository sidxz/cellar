"use client";

import { CollectionTypeIcon } from "@/features/research-organization/components/collection/collection-type-icon";
import type { CollectionType } from "@/features/research-organization/types";
import { cn } from "@/shared/lib/utils";
import type { CollectionCoverage } from "../types";

const fmt = (n: number) => n.toLocaleString("en-US");

/**
 * Compact, single-line coverage readout for the run summary header — the dense
 * sibling of `CoverageBar` (which stays the full-width treatment on the protocol
 * Overview tab). Renders the collection icon + name, a short inline progress
 * bar, the `covered/total · pct%` figure, and — when members remain unscreened
 * and `onViewGap` is supplied — a "N remaining" link that opens the gap dialog.
 */
export function CoverageChip({
  coverage,
  onViewGap,
  className,
}: {
  coverage: CollectionCoverage;
  onViewGap?: () => void;
  className?: string;
}) {
  const { name, type, covered, total, fraction } = coverage;
  const empty = total === 0 || fraction === null;
  const pct = empty ? 0 : Math.round((fraction ?? 0) * 100);
  const remaining = Math.max(0, total - covered);

  return (
    <span
      className={cn("inline-flex min-w-0 items-center gap-2 text-xs", className)}
      title={empty ? `${name} — empty` : `${name}: ${fmt(covered)} / ${fmt(total)} · ${pct}%`}
    >
      <CollectionTypeIcon type={type as CollectionType} className="shrink-0" />
      <span className="truncate font-medium">{name}</span>
      {empty ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        <>
          <span className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-muted">
            <span
              className="block h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </span>
          <span className="shrink-0 tabular-nums text-muted-foreground">
            {fmt(covered)}/{fmt(total)} · {pct}%
          </span>
          {onViewGap && remaining > 0 && (
            <button
              type="button"
              onClick={onViewGap}
              className="shrink-0 text-primary underline-offset-4 hover:underline"
            >
              {fmt(remaining)} remaining
            </button>
          )}
        </>
      )}
    </span>
  );
}
