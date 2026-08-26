"use client";

import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";

export interface CountChip {
  key: string;
  label: string;
  count: number;
  tone?: "destructive";
}

/** Single-active toggle chips with counts; chips with count 0 are not rendered
 * and the whole strip disappears when nothing is left. */
export function CountChips({
  chips,
  active,
  onChange,
}: {
  chips: CountChip[];
  active: string | null;
  onChange: (key: string | null) => void;
}) {
  const visible = chips.filter((c) => c.count > 0);
  if (visible.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Filter">
      {visible.map((c) => {
        const isActive = active === c.key;
        return (
          <Button
            key={c.key}
            type="button"
            size="sm"
            variant={isActive ? "default" : "outline"}
            aria-pressed={isActive}
            className={cn(
              "h-7 gap-1.5 px-2.5",
              !isActive && c.tone === "destructive" && "border-destructive/40 text-destructive",
            )}
            onClick={() => onChange(isActive ? null : c.key)}
          >
            {c.label}
            <span
              className={cn(
                "rounded-full px-1.5 text-xs tabular-nums",
                isActive ? "bg-primary-foreground/20" : "bg-muted",
              )}
            >
              {c.count}
            </span>
          </Button>
        );
      })}
    </div>
  );
}
