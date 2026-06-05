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
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
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
    av.intercept_aggregates.find((a) => a.spec.kind === ik.kind && a.spec.level === ik.level) ??
    null
  );
}

/** Exponent N such that 1 unit = 10⁻ᴺ M.
 *  pX = -log10(value × 10⁻ᴺ) = N − log10(value). */
function unitToMolarExponent(unit: string | null | undefined): number {
  if (!unit) return 6; // assume µM — the dominant unit on this codebase
  switch (unit.trim().toLowerCase()) {
    case "m":
      return 0;
    case "mm":
      return 3;
    case "um":
    case "µm":
    case "μm":
      return 6;
    case "nm":
      return 9;
    case "pm":
      return 12;
    case "fm":
      return 15;
    default:
      return 6;
  }
}

/** Chemist-facing label for the log-domain summary: pIC50 / pEC90 / etc.
 *  For aggregate spec `{kind: "primary"}`, falls back to `av.curve_type`
 *  (e.g. "ic50" → "pIC50"). Returns "pX" only as a last-resort. */
function pXLabel(
  aggregateSpec: { kind: string; level?: number } | null,
  fallbackCurveType: string | null,
): string {
  if (aggregateSpec && aggregateSpec.kind !== "primary" && aggregateSpec.level != null) {
    const lvl =
      aggregateSpec.level % 1 === 0 ? String(aggregateSpec.level) : aggregateSpec.level.toFixed(1);
    return `p${aggregateSpec.kind.toUpperCase()}${lvl}`;
  }
  if (fallbackCurveType) return `p${fallbackCurveType.toUpperCase()}`;
  return "pX";
}

/** Format the fold-range as `×N` — integer when ≥10, one decimal otherwise.
 *  Matches the inline chip's compact, scannable form. */
function formatFoldRange(foldRange: number): string {
  return foldRange >= 10 ? `×${Math.round(foldRange)}` : `×${foldRange.toFixed(1)}`;
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
  const fullSpec = spec !== null && "basis" in spec ? (spec as InterceptSpec) : null;
  const iv = fullSpec ? findInterceptValue(av.intercept_values, fullSpec) : undefined;

  const value = aggregate?.selected_value ?? iv?.value ?? (isPrimary ? av.value : null);
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
    wireQualifier && wireQualifier !== "=" && display.kind === "scalar" ? `${wireQualifier} ` : "";
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

  // ---- Inline aggregate summary lines (muted, below the headline) ----
  // Chemistry convention: papers report `IC50 = X ± Y µM (n=N)` or
  // `pIC50 = X ± Y`. Showing both right under the headline lets a chemist
  // copy-paste into a presentation without opening the per-run drill-in.
  //
  // Skip these lines when the headline isn't a scalar (an ND / `>max`
  // cell has nothing to summarize) or when this is a single-run cell.
  const stats = aggregate?.aggregate_stats;
  const isScalarHeadline = display.kind === "scalar";
  const showAggregateLines =
    runCount >= 2 && stats !== null && stats !== undefined && isScalarHeadline;
  const isAggregateMode = mode === "gmean" || mode === "mean";

  // In gmean/mean modes the headline already IS the geometric mean (with the
  // ×N chip in the decoration); the gmean line would be a redundant restate.
  // In Latest / Best R² modes the headline is a single picked value, so the
  // gmean line surfaces the spread context the chemist needs to trust it.
  const showGmeanLine =
    showAggregateLines &&
    !isAggregateMode &&
    stats?.geometric_mean != null &&
    stats?.fold_range != null;

  const showPxLine =
    showAggregateLines && stats?.log_value_mean != null && stats?.log_value_sd != null;

  const gmeanLine = showGmeanLine ? (
    <div className="font-mono text-[10px] text-muted-foreground tabular-nums">
      gmean {stats!.geometric_mean!.toPrecision(3)} · {formatFoldRange(stats!.fold_range!)}
    </div>
  ) : null;

  const pxLine = showPxLine ? (
    <div className="font-mono text-[10px] text-muted-foreground tabular-nums">
      {pXLabel(aggregate?.spec ?? null, av.curve_type)}{" "}
      {(unitToMolarExponent(av.unit) - stats!.log_value_mean!).toFixed(2)} ±{" "}
      {stats!.log_value_sd!.toFixed(2)}
    </div>
  ) : null;

  // Stack the headline + muted lines vertically only when there's something
  // to stack — single-run / non-scalar cells keep their original one-line
  // shape so the grid stays scannable.
  const stackedBody =
    gmeanLine || pxLine ? (
      <div className="flex flex-col gap-0.5 items-start">
        {cellBody}
        {gmeanLine}
        {pxLine}
      </div>
    ) : (
      cellBody
    );

  if (!hasDrillIn) {
    return stackedBody;
  }

  // Multi-run drill-in via Popover (click-to-open; HoverCard isn't in
  // this codebase). Trigger wraps the entire stacked body so clicking
  // anywhere in the cell opens the per-run table.
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="cursor-pointer rounded p-0 text-left hover:bg-muted/30"
          aria-label="Show run history"
        >
          {stackedBody}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-3" align="start">
        <RunHistoryTooltip av={av} interceptKey={ik} unit={av.unit ?? "uM"} />
      </PopoverContent>
    </Popover>
  );
}
