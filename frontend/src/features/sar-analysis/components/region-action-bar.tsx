"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";

interface RegionActionBarProps {
  regionCount: number;
  n: number;
  onNChange: (n: number) => void;
  onPickDiverse: () => void;
  picking: boolean;
  pickCount: number;
  onAddPicks: () => void;
  onAddAll: () => void;
  onRemove: () => void;
  onClear: () => void;
}

export function RegionActionBar(props: RegionActionBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="font-medium text-foreground">
        {props.regionCount} in region
      </span>
      <span className="text-border">·</span>

      <Label htmlFor="region-n" className="text-muted-foreground">
        N
      </Label>
      <Input
        id="region-n"
        type="number"
        min={1}
        max={1000}
        value={props.n}
        onChange={(e) => props.onNChange(Number(e.target.value))}
        className="h-7 w-16"
      />
      <Button
        size="sm"
        variant="outline"
        onClick={props.onPickDiverse}
        disabled={props.picking || props.regionCount === 0}
      >
        {props.picking ? "Picking…" : "Pick diverse"}
      </Button>

      <Button
        size="sm"
        onClick={props.onAddPicks}
        disabled={props.pickCount === 0}
      >
        Add picks ({props.pickCount})
      </Button>
      <Button size="sm" variant="outline" onClick={props.onAddAll}>
        Add all ({props.regionCount})
      </Button>
      <Button size="sm" variant="outline" onClick={props.onRemove}>
        Remove
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={props.onClear}
        className="text-muted-foreground"
      >
        Clear
      </Button>
    </div>
  );
}
