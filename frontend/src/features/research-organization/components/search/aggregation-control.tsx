"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  AGGREGATION_LABELS,
  AGGREGATION_MODES,
  type AggregationMode,
} from "../../lib/use-aggregation-mode";

export interface AggregationControlProps {
  mode: AggregationMode;
  onChange: (next: AggregationMode) => void;
  /**
   * When true, every active activity criterion has narrowed scope to one
   * run, so any aggregation rule is a no-op on every cell. Replace the
   * dropdown with a static muted label so chemists aren't tempted to
   * fiddle with a control that does nothing.
   */
  disabled?: boolean;
}

const DROPDOWN_TOOLTIP =
  "Each cell with multiple in-scope runs is reduced to one value using this rule. Cells with one in-scope run ignore it.";

const DISABLED_TOOLTIP =
  "You've narrowed each criterion to one run, so there's nothing to summarize. Loosen the runs filter to enable summarization.";

/**
 * Compact toolbar control for picking the multi-run aggregation rule used
 * when collapsing per-(compound, intercept) cells in the search results
 * grid. Four modes: Latest run, Geometric mean, Arithmetic mean, Best fit
 * (R²). The actual URL state + wire mapping lives in
 * {@link useAggregationMode}; this component is a pure render+callback
 * pair so it stays trivially testable.
 *
 * When `disabled` is true (the chemist has narrowed scope so every cell
 * has at most one in-scope run), the dropdown is replaced with a static
 * "Single run per compound" label that points the chemist at the runs
 * filter via tooltip.
 */
export function AggregationControl({ mode, onChange, disabled }: AggregationControlProps) {
  if (disabled) {
    return (
      <div className="inline-flex items-center gap-1.5 text-xs">
        <span className="text-muted-foreground italic" title={DISABLED_TOOLTIP}>
          Single run per compound
        </span>
      </div>
    );
  }
  return (
    <div className="inline-flex items-center gap-1.5 text-xs">
      <span className="text-muted-foreground">Summarize:</span>
      <Select value={mode} onValueChange={(v) => onChange(v as AggregationMode)}>
        <SelectTrigger
          className="h-7 w-[10rem] text-xs"
          aria-label="Aggregation mode"
          title={DROPDOWN_TOOLTIP}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {AGGREGATION_MODES.map((m) => (
            <SelectItem key={m} value={m} className="text-xs">
              {AGGREGATION_LABELS[m]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
