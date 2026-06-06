"use client";

import { Badge } from "@/shared/components/ui/badge";
import { cn } from "@/shared/lib/utils";
import type { TargetRef } from "../types";

interface TargetChipsProps {
  targets: TargetRef[] | null | undefined;
  /** Max chips to render before collapsing the remainder into a "+N" chip. */
  max?: number;
  className?: string;
}

/**
 * Compact, read-only target chips for grids and detail cards. Renders one
 * `Badge` per target up to `max`, collapsing the overflow into a single "+N"
 * chip whose tooltip lists the hidden names. Shows an em-dash when empty.
 */
export function TargetChips({ targets, max = 3, className }: TargetChipsProps) {
  if (!targets || targets.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  const shown = targets.slice(0, max);
  const hidden = targets.slice(max);

  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {shown.map((t) => (
        <Badge key={t.id} variant="secondary" className="font-normal text-[10px]" title={t.name}>
          {t.name}
        </Badge>
      ))}
      {hidden.length > 0 && (
        <Badge
          variant="outline"
          className="font-normal text-[10px] text-muted-foreground"
          title={hidden.map((t) => t.name).join(", ")}
        >
          +{hidden.length}
        </Badge>
      )}
    </div>
  );
}
