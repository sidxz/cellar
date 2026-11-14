"use client";

import type { ConditionDefinition } from "@/features/screening-assay/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { cn } from "@/shared/lib/utils";
import { useRef } from "react";
import type { ColumnSplitWire, RunScope } from "../../types";

export type SplitMode = "none" | "run" | "condition";

export interface SplitChange {
  split: ColumnSplitWire | undefined;
  run_scope: RunScope | undefined;
}

/** The criterion's split and run filter after choosing a split mode.
 *
 *  - By run uses the runs picked by hand, so the run filter becomes
 *    "Specific runs" (keeping any runs already picked).
 *  - By condition needs more than one run, so "Latest run" (a single run)
 *    becomes "Any run". With one condition defined it is chosen for you. */
export function applySplit(
  mode: SplitMode,
  runScope: RunScope | undefined,
  conditions: readonly ConditionDefinition[],
): SplitChange {
  if (mode === "run") {
    return {
      split: { by: "run" },
      run_scope: runScope?.mode === "specific" ? runScope : { mode: "specific", run_ids: [] },
    };
  }
  if (mode === "condition") {
    return {
      split: { by: "condition", condition: conditions.length === 1 ? conditions[0].name : "" },
      run_scope: runScope?.mode === "latest" ? undefined : runScope,
    };
  }
  return { split: undefined, run_scope: runScope };
}

const MODES: { value: SplitMode; label: string; description: string }[] = [
  { value: "none", label: "None", description: "One value per readout, runs combined." },
  { value: "run", label: "By run", description: "One column group per run you pick." },
  {
    value: "condition",
    label: "By condition",
    description: "One column group per value of a run condition.",
  },
];

interface SplitPickerProps {
  /** The protocol's run conditions. */
  conditions: readonly ConditionDefinition[];
  split: ColumnSplitWire | undefined;
  runScope: RunScope | undefined;
  onChange: (next: SplitChange) => void;
}

/** "split" row under a protocol's run filter: optionally show the protocol's
 *  columns side by side, per hand-picked run or per condition value. */
export function SplitPicker({ conditions, split, runScope, onChange }: SplitPickerProps) {
  const mode: SplitMode = split?.by ?? "none";
  const condition = split?.by === "condition" ? split.condition : "";
  const keepFocus = useRef(false);
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-sm text-muted-foreground shrink-0 w-24">Split columns</span>
      <Select
        value={mode}
        onValueChange={(v) => {
          const next = applySplit(v as SplitMode, runScope, conditions);
          // An empty run pick opens the run list next; don't let this menu
          // hand focus back to its trigger and close that list.
          keepFocus.current = next.run_scope?.mode === "specific" && runScope?.mode !== "specific";
          onChange(next);
        }}
      >
        <SelectTrigger className="h-8 w-36 text-sm shrink-0" aria-label="Split columns">
          <SelectValue />
        </SelectTrigger>
        <SelectContent
          className="min-w-[18rem]"
          onCloseAutoFocus={(e) => {
            if (keepFocus.current) e.preventDefault();
            keepFocus.current = false;
          }}
        >
          {MODES.map((m) => {
            const unavailable = m.value === "condition" && conditions.length === 0;
            return (
              <SelectItem
                key={m.value}
                value={m.value}
                disabled={unavailable}
                description={
                  unavailable ? "This protocol defines no run conditions." : m.description
                }
              >
                {m.label}
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
      {mode === "condition" && (
        <Select
          value={condition || undefined}
          onValueChange={(name) =>
            onChange({ split: { by: "condition", condition: name }, run_scope: runScope })
          }
        >
          <SelectTrigger
            className={cn("h-8 w-48 text-sm", !condition && "border-destructive")}
            aria-label="Split condition"
            aria-invalid={!condition}
          >
            <SelectValue placeholder="Choose condition…" />
          </SelectTrigger>
          <SelectContent>
            {conditions.map((c) => (
              <SelectItem key={c.name} value={c.name}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}

/** The criterion's split after its run filter changes: splitting by run needs
 *  hand-picked runs, so leaving "Specific runs" turns that split off. */
export function withRunScope(
  split: ColumnSplitWire | undefined,
  next: RunScope | undefined,
): SplitChange {
  if (split?.by === "run" && next?.mode !== "specific")
    return { split: undefined, run_scope: next };
  return { split, run_scope: next };
}

/** Why "Latest run" is unavailable while a protocol is split by condition. */
export const LATEST_UNDER_CONDITION_SPLIT =
  "Latest run picks a single run. To see each compound's newest run per condition, set Across runs → Latest run.";
