"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";

import { CurveClassBadge } from "@/features/screening-assay/components/curve-class-badge";
import {
  findInterceptValue,
  formatInterceptDisplay,
  maxDoseFromRawData,
} from "@/features/screening-assay/lib/intercept-label";
import type { InterceptSpec } from "@/features/screening-assay/types";
import { Badge } from "@/shared/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/shared/components/ui/popover";
import { cn } from "@/shared/lib/utils";

import type { AggregationMode } from "../../lib/use-aggregation-mode";
import type { ActivityValue, InterceptKey } from "../../types";

import { RunHistoryTooltip } from "./run-history-tooltip";

export interface InterceptCellProps {
  av: ActivityValue | undefined;
  /** `null` for the primary intercept (or when spec isn't available);
   *  otherwise the keyed intercept this cell represents. */
  spec: InterceptKey | InterceptSpec | null;
  /** True when this column renders the readout's primary intercept (av.value
   *  is the fallback when spec doesn't match any keyed intercept_values). */
  isPrimary: boolean;
  mode: AggregationMode;
}

function specToKey(spec: InterceptKey | InterceptSpec | null): InterceptKey | null {
  if (spec === null) return null;
  // Both InterceptKey and InterceptSpec carry {kind, level}; pick those.
  // kind is narrowed to "ec" | "ic" on both sides so the cast is safe.
  return { kind: spec.kind, level: spec.level };
}

function findAggregate(av: ActivityValue, ik: InterceptKey | null) {
  if (!av.intercept_aggregates) return null;
  if (ik === null) {
    return av.intercept_aggregates.find((a) => a.spec.kind === "primary") ?? null;
  }
  return (
    av.intercept_aggregates.find(
      (a) => a.spec.kind === ik.kind && a.spec.level === ik.level,
    ) ?? null
  );
}

export function InterceptCell({ av, spec, isPrimary, mode }: InterceptCellProps) {
  const [open, setOpen] = useState(false);

  if (!av) return <span className="text-muted-foreground">&mdash;</span>;

  const ik = specToKey(spec);
  const aggregate = findAggregate(av, ik);
  const runCount = av.run_count ?? 1;
  const hasDrillIn = runCount >= 2 && (av.runs?.length ?? 0) > 0;

  // Existing intercept_values path (legacy + single-run cells) — kept so the
  // cell still works when intercept_aggregates is absent (older endpoints,
  // unmigrated callers). InterceptSpec carries the extra `basis` + `label`
  // fields findInterceptValue requires; bare InterceptKey doesn't, so we
  // only run the lookup when the caller handed us a full spec.
  const fullSpec =
    spec !== null && "basis" in spec ? (spec as InterceptSpec) : null;
  const iv = fullSpec
    ? findInterceptValue(av.intercept_values, fullSpec)
    : undefined;

  const value =
    aggregate?.selected_value ??
    iv?.value ??
    (isPrimary ? av.value : null);
  const qualifierFromAggregate = aggregate?.selected_qualifier;
  const display = formatInterceptDisplay({
    value,
    at_bound: iv?.at_bound,
    curve_class: av.curve_params?.curve_class,
    max_dose: maxDoseFromRawData(av.raw_data),
    runCount,
    mode,
    foldRange: aggregate?.aggregate_stats?.fold_range ?? null,
    disagreement: aggregate?.disagreement_flag ?? av.disagreement_flag ?? false,
  });

  // Wire-level qualifier prefix (matches existing renderInterceptCell
  // behavior): only prepend on scalar cells where the wire qualifier
  // disagrees with the BE's resolved one. Aggregate's selected_qualifier
  // takes precedence when present.
  const wireQualifier = qualifierFromAggregate ?? av.qualifier;
  const q =
    wireQualifier && wireQualifier !== "=" && display.kind === "scalar"
      ? `${wireQualifier} `
      : "";
  const showUnit = display.kind === "scalar" || display.kind === "qualifier";
  const unitSuffix = showUnit && av.unit ? ` ${av.unit}` : "";

  // Shared disagreement glyph — rendered in BOTH the Badge and span paths
  // so a scalar amber-warning cell still surfaces the per-run conflict
  // chemists rely on to spot reproducibility issues.
  const disagreementGlyph = aggregate?.disagreement_flag ? (
    <AlertTriangle
      className="ml-1 h-3 w-3 text-amber-500"
      aria-label="Runs disagree — open run history for per-run details"
    />
  ) : null;

  // The cell body — either Badge (warning) or plain span. Preserves
  // existing renderInterceptCell visual treatment.
  const cellBody = display.warning ? (
    <Badge
      variant="outline"
      className="text-xs border-amber-500 text-amber-700"
      title={display.tooltip}
    >
      <span className="inline-flex items-center font-mono">
        {q}
        {display.primary}
        {unitSuffix}
        {display.decoration?.runCountSubscript && (
          <sub className="ml-0.5 text-[10px] text-muted-foreground">
            {display.decoration.runCountSubscript}
          </sub>
        )}
        {display.decoration?.foldRangeChip && (
          <span className="ml-1 rounded-sm border border-amber-500/30 px-1 text-[10px] font-normal">
            {display.decoration.foldRangeChip}
          </span>
        )}
        {disagreementGlyph}
      </span>
    </Badge>
  ) : (
    <span
      className={cn(
        "inline-flex items-center font-mono text-xs",
        display.kind !== "scalar" && "text-muted-foreground",
      )}
      title={display.tooltip || undefined}
    >
      {q}
      {display.primary}
      {unitSuffix}
      {display.decoration?.runCountSubscript && (
        <sub className="ml-0.5 text-[10px] text-muted-foreground">
          {display.decoration.runCountSubscript}
        </sub>
      )}
      {display.decoration?.foldRangeChip && (
        <span className="ml-1 rounded-sm border border-muted-foreground/30 px-1 text-[10px] font-normal text-muted-foreground">
          {display.decoration.foldRangeChip}
        </span>
      )}
      {disagreementGlyph}
      {isPrimary && display.kind === "scalar" && (
        <CurveClassBadge
          curveClass={av.curve_params?.curve_class ?? null}
          compact
          renderNullAs="nothing"
        />
      )}
    </span>
  );

  if (!hasDrillIn) {
    return cellBody;
  }

  // Multi-run drill-in via Popover (click-to-open; HoverCard isn't in
  // this codebase). Trigger wraps the cell body in a button so it's
  // keyboard-accessible.
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="cursor-pointer rounded p-0 text-left hover:bg-muted/30"
          aria-label="Show run history"
        >
          {cellBody}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-3" align="start">
        <RunHistoryTooltip av={av} interceptKey={ik} unit={av.unit ?? "uM"} />
      </PopoverContent>
    </Popover>
  );
}
