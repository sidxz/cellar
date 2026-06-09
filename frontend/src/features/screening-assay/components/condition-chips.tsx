"use client";

import { Badge } from "@/shared/components/ui/badge";
import { cn } from "@/shared/lib/utils";
import { type ConditionEntry, formatConditionEntries } from "../lib/conditions";

interface ConditionChipsProps {
  conditions: Record<string, unknown> | null | undefined;
  /** Max chips to render before collapsing the remainder into a "+N" chip. */
  max?: number;
  className?: string;
  /** Override the per-chip badge classes (e.g. a larger text size). */
  chipClassName?: string;
  /** Rendered when there are no conditions. Defaults to an em-dash. */
  emptyFallback?: React.ReactNode;
}

function chipLabel(e: ConditionEntry): string {
  return `${e.key}: ${e.value}`;
}

/**
 * Compact, read-only condition chips for the runs grid and the run detail
 * header. Renders one `key: value` badge per condition up to `max`, collapsing
 * the overflow into a single "+N" chip whose tooltip lists the hidden entries.
 */
export function ConditionChips({
  conditions,
  max = 3,
  className,
  chipClassName,
  emptyFallback,
}: ConditionChipsProps) {
  const entries = formatConditionEntries(conditions);
  if (entries.length === 0) {
    return <>{emptyFallback ?? <span className="text-xs text-muted-foreground">—</span>}</>;
  }

  const shown = entries.slice(0, max);
  const hidden = entries.slice(max);

  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {shown.map((e) => (
        <Badge
          key={e.key}
          variant="secondary"
          className={cn("max-w-[16rem] truncate font-normal text-[10px]", chipClassName)}
          title={chipLabel(e)}
        >
          <span className="text-muted-foreground">{e.key}:</span>
          <span className="ml-1">{e.value}</span>
        </Badge>
      ))}
      {hidden.length > 0 && (
        <Badge
          variant="outline"
          className={cn("font-normal text-[10px] text-muted-foreground", chipClassName)}
          title={hidden.map(chipLabel).join(", ")}
        >
          +{hidden.length}
        </Badge>
      )}
    </div>
  );
}
