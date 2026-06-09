"use client";

import { CollectionTypeIcon } from "@/features/research-organization/components/collection/collection-type-icon";
import type { CollectionType } from "@/features/research-organization/types";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import type { CollectionCoverage } from "../types";

const fmt = (n: number) => n.toLocaleString("en-US");

export function CoverageBar({
  coverage,
  onViewGap,
  runCount,
  className,
}: {
  coverage: CollectionCoverage;
  onViewGap?: () => void;
  runCount?: number;
  className?: string;
}) {
  const { name, type, covered, total, fraction } = coverage;
  const empty = total === 0 || fraction === null;
  const pct = empty ? 0 : Math.round((fraction ?? 0) * 100);
  const remaining = Math.max(0, total - covered);

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="flex min-w-0 items-center gap-1.5">
          <CollectionTypeIcon type={type as CollectionType} className="shrink-0" />
          <span className="truncate font-medium" title={name}>
            {name}
          </span>
        </span>
        {empty ? (
          <span className="text-muted-foreground" title="Collection is empty">
            —
          </span>
        ) : (
          <span className="shrink-0 tabular-nums text-muted-foreground">
            {fmt(covered)} / {fmt(total)} · {pct}%
          </span>
        )}
      </div>
      {!empty && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      {!empty && (onViewGap || runCount !== undefined) && (
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>
            {runCount !== undefined ? `across ${runCount} run${runCount === 1 ? "" : "s"}` : ""}
          </span>
          {onViewGap && remaining > 0 && (
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto p-0 text-[11px]"
              onClick={onViewGap}
            >
              {fmt(remaining)} remaining
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
