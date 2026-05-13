"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useState } from "react";
import {
  type CurveConstraints,
  type ParamMode,
  isRangeValid,
  parseInputOrNull,
} from "../lib/curve-constraints";
import type { DoseResponseCurve } from "../types";

// ─── Constants ─────────────────────────────────────────────────────────────────

const HILL_SLOPE_OPTIONS: { value: string; label: string }[] = [
  { value: "unconstrained", label: "Unconstrained" },
  { value: "negative_only", label: "Negative only" },
  { value: "positive_only", label: "Positive only" },
  { value: "fixed_at_one", label: "Fixed at 1" },
];

// ─── PerCurveModeToggle ───────────────────────────────────────────────────────

function PerCurveModeToggle({
  mode,
  onChange,
  idPrefix,
}: {
  mode: ParamMode;
  onChange: (m: ParamMode) => void;
  idPrefix: string;
}) {
  const options: ParamMode[] = ["free", "range", "lock"];
  return (
    <div className="inline-flex rounded-md border" role="radiogroup">
      {options.map((opt) => (
        <button
          key={`${idPrefix}-${opt}`}
          type="button"
          role="radio"
          aria-checked={mode === opt}
          onClick={() => onChange(opt)}
          className={`px-2 py-0.5 text-[10px] capitalize first:rounded-l-md last:rounded-r-md ${
            mode === opt ? "bg-primary text-primary-foreground" : "bg-background hover:bg-muted"
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

// ─── CurveControls ────────────────────────────────────────────────────────────

export interface CurveControlsProps {
  curve: DoseResponseCurve;
  excludedIndices: Set<number>;
  constraints: CurveConstraints;
  onConstraintChange: (next: Partial<CurveConstraints>) => void;
  onReset: () => void;
  isPending: boolean;
}

export function CurveControls({
  curve,
  excludedIndices,
  constraints,
  onConstraintChange,
  onReset,
  isPending,
}: CurveControlsProps) {
  const [open, setOpen] = useState(false);
  const totalPoints = (curve.raw_data?.length ?? 0) + (curve.excluded_points?.length ?? 0);
  const includedCount = totalPoints - excludedIndices.size;

  const topRangeError =
    constraints.topMode === "range" && !isRangeValid(constraints.topMin, constraints.topMax);
  const topLockError =
    constraints.topMode === "lock" &&
    (constraints.topValue == null || !Number.isFinite(constraints.topValue));
  const bottomRangeError =
    constraints.bottomMode === "range" &&
    !isRangeValid(constraints.bottomMin, constraints.bottomMax);
  const bottomLockError =
    constraints.bottomMode === "lock" &&
    (constraints.bottomValue == null || !Number.isFinite(constraints.bottomValue));
  const hillRangeError =
    constraints.hillCustomRange && !isRangeValid(constraints.hillMin, constraints.hillMax);

  return (
    <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-3">
      {/* Toggle header */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setOpen((v) => !v)}
        >
          <span>{open ? "▾" : "▸"}</span>
          <span className="font-mono">
            {curve.registration_number ?? curve.molecule_name ?? "Curve"}
          </span>{" "}
          — Fit Constraints
          {isPending && (
            <span className="ml-1 h-2 w-2 rounded-full bg-primary animate-pulse inline-block" />
          )}
        </button>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>
            {includedCount}/{totalPoints} points
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={onReset}
            disabled={isPending}
          >
            Reset
          </Button>
        </div>
      </div>

      {/* Collapsible constraint panel */}
      {open && (
        <div className="space-y-2 pt-1">
          {/* Top */}
          <div className="rounded-md border bg-background p-2 space-y-1.5">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium">Top</Label>
              <PerCurveModeToggle
                mode={constraints.topMode}
                onChange={(m) => onConstraintChange({ topMode: m })}
                idPrefix={`top-${curve.id}`}
              />
            </div>
            {constraints.topMode === "lock" && (
              <>
                <Input
                  type="number"
                  className="h-7 text-xs"
                  value={constraints.topValue ?? ""}
                  onChange={(e) =>
                    onConstraintChange({ topValue: parseInputOrNull(e.target.value) })
                  }
                />
                {topLockError && (
                  <p className="text-[10px] text-destructive">Enter a numeric value.</p>
                )}
              </>
            )}
            {constraints.topMode === "range" && (
              <>
                <div className="flex items-center gap-1.5">
                  <Input
                    type="number"
                    className="h-7 text-xs"
                    placeholder="min"
                    value={constraints.topMin ?? ""}
                    onChange={(e) =>
                      onConstraintChange({ topMin: parseInputOrNull(e.target.value) })
                    }
                  />
                  <span className="text-xs text-muted-foreground">to</span>
                  <Input
                    type="number"
                    className="h-7 text-xs"
                    placeholder="max"
                    value={constraints.topMax ?? ""}
                    onChange={(e) =>
                      onConstraintChange({ topMax: parseInputOrNull(e.target.value) })
                    }
                  />
                </div>
                {topRangeError && (
                  <p className="text-[10px] text-destructive">
                    Enter both min and max with min &lt; max.
                  </p>
                )}
              </>
            )}
          </div>

          {/* Bottom */}
          <div className="rounded-md border bg-background p-2 space-y-1.5">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium">Bottom</Label>
              <PerCurveModeToggle
                mode={constraints.bottomMode}
                onChange={(m) => onConstraintChange({ bottomMode: m })}
                idPrefix={`bot-${curve.id}`}
              />
            </div>
            {constraints.bottomMode === "lock" && (
              <>
                <Input
                  type="number"
                  className="h-7 text-xs"
                  value={constraints.bottomValue ?? ""}
                  onChange={(e) =>
                    onConstraintChange({ bottomValue: parseInputOrNull(e.target.value) })
                  }
                />
                {bottomLockError && (
                  <p className="text-[10px] text-destructive">Enter a numeric value.</p>
                )}
              </>
            )}
            {constraints.bottomMode === "range" && (
              <>
                <div className="flex items-center gap-1.5">
                  <Input
                    type="number"
                    className="h-7 text-xs"
                    placeholder="min"
                    value={constraints.bottomMin ?? ""}
                    onChange={(e) =>
                      onConstraintChange({ bottomMin: parseInputOrNull(e.target.value) })
                    }
                  />
                  <span className="text-xs text-muted-foreground">to</span>
                  <Input
                    type="number"
                    className="h-7 text-xs"
                    placeholder="max"
                    value={constraints.bottomMax ?? ""}
                    onChange={(e) =>
                      onConstraintChange({ bottomMax: parseInputOrNull(e.target.value) })
                    }
                  />
                </div>
                {bottomRangeError && (
                  <p className="text-[10px] text-destructive">
                    Enter both min and max with min &lt; max.
                  </p>
                )}
              </>
            )}
          </div>

          {/* Hill Slope */}
          <div className="rounded-md border bg-background p-2 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <Label className="text-xs font-medium">Hill Slope</Label>
              <Select
                value={constraints.hillSlope}
                onValueChange={(v) => onConstraintChange({ hillSlope: v })}
              >
                <SelectTrigger className="h-7 text-xs w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HILL_SLOPE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} className="text-xs">
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <label className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={constraints.hillCustomRange}
                onChange={(e) => onConstraintChange({ hillCustomRange: e.target.checked })}
                className="h-3.5 w-3.5"
              />
              Custom range (overrides bounds)
            </label>
            {constraints.hillCustomRange && (
              <>
                <div className="flex items-center gap-1.5">
                  <Input
                    type="number"
                    step="0.1"
                    className="h-7 text-xs"
                    placeholder="min"
                    value={constraints.hillMin ?? ""}
                    onChange={(e) =>
                      onConstraintChange({ hillMin: parseInputOrNull(e.target.value) })
                    }
                  />
                  <span className="text-xs text-muted-foreground">to</span>
                  <Input
                    type="number"
                    step="0.1"
                    className="h-7 text-xs"
                    placeholder="max"
                    value={constraints.hillMax ?? ""}
                    onChange={(e) =>
                      onConstraintChange({ hillMax: parseInputOrNull(e.target.value) })
                    }
                  />
                </div>
                {hillRangeError && (
                  <p className="text-[10px] text-destructive">
                    Enter both min and max with min &lt; max.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
