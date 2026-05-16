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
}

/**
 * Compact toolbar control for picking the multi-run aggregation rule used
 * when collapsing per-(compound, intercept) cells in the search results
 * grid. Four modes: Latest run, Geometric mean, Arithmetic mean, Best fit
 * (R²). The actual URL state + wire mapping lives in
 * {@link useAggregationMode}; this component is a pure render+callback
 * pair so it stays trivially testable.
 */
export function AggregationControl({ mode, onChange }: AggregationControlProps) {
  return (
    <div className="inline-flex items-center gap-1.5 text-xs">
      <span className="text-muted-foreground">Show:</span>
      <Select value={mode} onValueChange={(v) => onChange(v as AggregationMode)}>
        <SelectTrigger
          className="h-7 w-[10rem] text-xs"
          aria-label="Aggregation mode"
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
