"use client";

import { Button } from "@/shared/components/ui/button";

interface ClusterBasketBarProps {
  count: number;
  /** Display-only well-plate target for the running-count hint (e.g. 96). */
  plateTarget?: number;
  /** Number of current global Diversify representatives available to seed. */
  repCount: number;
  onAddRepPicks: () => void;
  onSave: () => void;
  onClear: () => void;
}

export function ClusterBasketBar({
  count,
  plateTarget = 96,
  repCount,
  onAddRepPicks,
  onSave,
  onClear,
}: ClusterBasketBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-muted/20 px-3 py-1.5 text-xs">
      <span className="font-medium text-foreground">Basket: {count}</span>
      {count > 0 && (
        <span className="text-muted-foreground">
          · {count} / {plateTarget} plate
        </span>
      )}
      <span className="ml-auto flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={onAddRepPicks} disabled={repCount === 0}>
          Add Diversify picks ({repCount})
        </Button>
        <Button size="sm" onClick={onSave} disabled={count === 0}>
          Save as collection
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onClear}
          disabled={count === 0}
          className="text-muted-foreground"
        >
          Clear basket
        </Button>
      </span>
    </div>
  );
}
