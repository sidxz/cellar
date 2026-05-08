"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { CHART_AXIS, CHART_COLORS, GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { Plot, getPlotlyGlobal } from "@/shared/lib/plotly";
import { cn } from "@/shared/lib/utils";
import { Download, ImageIcon } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useClassifyDoseResponse, useRefitDoseResponse } from "../hooks/use-refit-dose-response";
import {
  CURVE_FIT_POINTS,
  PLOT_MARKER,
  X_AXIS_FALLBACK_MAX_RATIO,
  X_AXIS_FALLBACK_MIN_RATIO,
  X_AXIS_FLOOR,
  X_AXIS_MAX_RATIO,
  X_AXIS_MIN_RATIO,
  generate4PLPoints,
} from "../lib/dose-response-display";
import { PERCENT_FIT_RANGES } from "../lib/readout-constants";
import {
  CURVE_CLASS_LABELS,
  CURVE_TYPE_LABELS,
  type CurveClass,
  type CurveType,
  type DoseResponseConfig,
  type DoseResponseCurve,
} from "../types";

// ─── Types ────────────────────────────────────────────────────────────────────

interface DoseResponseChartProps {
  curves: DoseResponseCurve[];
  className?: string;
  isInteractive?: boolean;
  /** Protocol's dose-response config for the readout being plotted. When
   *  provided, the per-curve Fit Constraints accordion seeds its
   *  Free/Range/Lock toggles from these values — so a user who set Top ∈
   *  [85, 110] at the protocol level sees Range pre-selected here, instead
   *  of a misleading "Free". Per-curve edits remain independent overrides. */
  protocolConfig?: DoseResponseConfig | null;
  /** Normalization of the Y readout (looked up from
   *  ``protocol.readout_definitions`` by the parent). Used to decide
   *  whether seeding CDD's [85,110]/[-10,10]/[0.9,1.1] defaults makes
   *  sense — those bounds are only meaningful for percent-scale
   *  readouts. Pass null/undefined to disable seeding. */
  yReadoutNormalization?: string | null;
}

type ParamMode = "free" | "range" | "lock";

interface CurveConstraints {
  // Top: Free leaves the optimizer alone; Range bounds it inside [min, max];
  // Lock pins it to a single value. Mutually exclusive with the protocol's
  // own constraint when sent — see refit_dose_response.py for resolution.
  // null in *Min/*Max/*Value means "user has not entered a value" — refit
  // is gated until the active mode's required fields are populated.
  topMode: ParamMode;
  topValue: number | null;
  topMin: number | null;
  topMax: number | null;
  bottomMode: ParamMode;
  bottomValue: number | null;
  bottomMin: number | null;
  bottomMax: number | null;
  hillSlope: string;
  hillCustomRange: boolean;
  hillMin: number | null;
  hillMax: number | null;
}

function parseInputOrNull(s: string): number | null {
  if (s.trim() === "") return null;
  const v = Number.parseFloat(s);
  return Number.isFinite(v) ? v : null;
}

function isRangeValid(min: number | null, max: number | null): boolean {
  return min != null && max != null && Number.isFinite(min) && Number.isFinite(max) && min < max;
}

function constraintsValid(c: CurveConstraints): boolean {
  if (c.topMode === "lock" && (c.topValue == null || !Number.isFinite(c.topValue))) return false;
  if (c.topMode === "range" && !isRangeValid(c.topMin, c.topMax)) return false;
  if (c.bottomMode === "lock" && (c.bottomValue == null || !Number.isFinite(c.bottomValue)))
    return false;
  if (c.bottomMode === "range" && !isRangeValid(c.bottomMin, c.bottomMax)) return false;
  if (c.hillCustomRange && !isRangeValid(c.hillMin, c.hillMax)) return false;
  return true;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * A curve has no meaningful sigmoid to draw when classified Inactive or
 * the fit produced degenerate parameters. ``ec50_at_bound`` curves are
 * still rendered (with an amber warning badge) so the user can see the
 * data and the extrapolated fit; only truly inactive / zero curves are
 * suppressed here.
 */
function isDegenerateFit(curve: DoseResponseCurve): boolean {
  return (
    curve.curve_class === "inactive" ||
    !Number.isFinite(curve.fitted_value) ||
    curve.fitted_value <= 0 ||
    curve.hill_slope === 0
  );
}

/** Plotly-friendly wrapper around the shared 4PL evaluator. Kept as a
 *  thin function so existing callers don't need to thread the curve
 *  destructure through ``generate4PLPoints``. */
function generate4PLCurve(
  curve: DoseResponseCurve,
  xMin: number,
  xMax: number,
): { x: number[]; y: number[] } {
  const { x, y } = generate4PLPoints(curve, xMin, xMax, CURVE_FIT_POINTS + 1);
  return { x, y };
}

/** Extract (concentration, response) pairs from raw_data / excluded_points */
function extractPoints(points: Array<Record<string, unknown>> | null): {
  x: number[];
  y: number[];
  reasons: (string | null)[];
} {
  if (!points || points.length === 0) return { x: [], y: [], reasons: [] };
  const xs: number[] = [];
  const ys: number[] = [];
  const reasons: (string | null)[] = [];
  for (const pt of points) {
    const conc = pt.concentration ?? pt.x;
    const resp = pt.response ?? pt.y;
    if (typeof conc === "number" && typeof resp === "number") {
      xs.push(conc);
      ys.push(resp);
      reasons.push(typeof pt.reason === "string" ? pt.reason : null);
    }
  }
  return { x: xs, y: ys, reasons };
}

/** Group points by concentration, return mean ± SD arrays for error bars */
function computeReplicateStats(
  x: number[],
  y: number[],
): {
  meanX: number[];
  meanY: number[];
  sdY: number[];
  replicateX: number[];
  replicateY: number[];
} {
  if (x.length === 0) {
    return { meanX: [], meanY: [], sdY: [], replicateX: [], replicateY: [] };
  }

  // Group by concentration (use string key to avoid float equality issues)
  const groups = new Map<string, { conc: number; responses: number[] }>();
  for (let i = 0; i < x.length; i++) {
    const key = x[i].toPrecision(10);
    if (!groups.has(key)) groups.set(key, { conc: x[i], responses: [] });
    groups.get(key)?.responses.push(y[i]);
  }

  const meanX: number[] = [];
  const meanY: number[] = [];
  const sdY: number[] = [];
  const replicateX: number[] = [];
  const replicateY: number[] = [];

  for (const { conc, responses } of groups.values()) {
    const mean = responses.reduce((a, b) => a + b, 0) / responses.length;
    meanX.push(conc);
    meanY.push(mean);

    if (responses.length > 1) {
      const variance =
        responses.reduce((sum, v) => sum + (v - mean) ** 2, 0) / (responses.length - 1);
      sdY.push(Math.sqrt(variance));
    } else {
      sdY.push(0);
    }

    // Individual replicates for scatter layer
    if (responses.length > 1) {
      for (const resp of responses) {
        replicateX.push(conc);
        replicateY.push(resp);
      }
    }
  }

  return { meanX, meanY, sdY, replicateX, replicateY };
}

/** R² color class */
function rSquaredColor(r2: number): string {
  if (r2 >= 0.9) return "text-green-400";
  if (r2 >= 0.8) return "text-yellow-400";
  return "text-destructive";
}

/** Whether a Y-axis normalization belongs to the percent-scale family that
 *  CDD's [85,110]/[-10,10]/[0.9,1.1] defaults are calibrated for. */
function isPercentNormalization(norm: string | null | undefined): boolean {
  return (
    norm === "percent_inhibition" || norm === "percent_activation" || norm === "percent_control"
  );
}

/** Pure helper: derive the per-curve UI defaults from the protocol's config
 *  and the Y readout's normalization. Hoisted out of the component so its
 *  identity is stable across renders — letting useCallback's exhaustive-deps
 *  list its actual inputs (protocolConfig, yReadoutNormalization) instead of
 *  swallowing the warning. */
function defaultConstraintsFor(
  curve: DoseResponseCurve,
  protocolConfig: DoseResponseConfig | null | undefined,
  yReadoutNormalization: string | null | undefined,
): CurveConstraints {
  const cfg = protocolConfig;
  const isPercentY = isPercentNormalization(yReadoutNormalization);
  const topMode: ParamMode =
    cfg?.top_constraint != null
      ? "lock"
      : cfg?.top_constraint_min != null || cfg?.top_constraint_max != null
        ? "range"
        : "free";
  const bottomMode: ParamMode =
    cfg?.bottom_constraint != null
      ? "lock"
      : cfg?.bottom_constraint_min != null || cfg?.bottom_constraint_max != null
        ? "range"
        : "free";
  const hillCustomRange = cfg?.hill_slope_min != null || cfg?.hill_slope_max != null;
  return {
    topMode,
    topValue: cfg?.top_constraint ?? curve.top,
    topMin: cfg?.top_constraint_min ?? (isPercentY ? PERCENT_FIT_RANGES.topMin : null),
    topMax: cfg?.top_constraint_max ?? (isPercentY ? PERCENT_FIT_RANGES.topMax : null),
    bottomMode,
    bottomValue: cfg?.bottom_constraint ?? curve.bottom,
    bottomMin: cfg?.bottom_constraint_min ?? (isPercentY ? PERCENT_FIT_RANGES.bottomMin : null),
    bottomMax: cfg?.bottom_constraint_max ?? (isPercentY ? PERCENT_FIT_RANGES.bottomMax : null),
    hillSlope: cfg?.hill_slope_constraint ?? "unconstrained",
    hillCustomRange,
    hillMin: cfg?.hill_slope_min ?? (isPercentY ? PERCENT_FIT_RANGES.hillMin : null),
    hillMax: cfg?.hill_slope_max ?? (isPercentY ? PERCENT_FIT_RANGES.hillMax : null),
  };
}

const TRACE_COLORS = GROUP_PALETTE.slice(0, 8);

const CURVE_CLASS_OPTIONS: CurveClass[] = ["full", "partial", "bell_shaped", "inactive"];

const HILL_SLOPE_OPTIONS: { value: string; label: string }[] = [
  { value: "unconstrained", label: "Unconstrained" },
  { value: "negative_only", label: "Negative only" },
  { value: "positive_only", label: "Positive only" },
  { value: "fixed_at_one", label: "Fixed at 1" },
];

// ─── Interactive single-curve controls ────────────────────────────────────────

interface CurveControlsProps {
  curve: DoseResponseCurve;
  excludedIndices: Set<number>;
  constraints: CurveConstraints;
  onConstraintChange: (next: Partial<CurveConstraints>) => void;
  onReset: () => void;
  isPending: boolean;
}

function CurveControls({
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

// ─── Summary card with interactive curve class badge ─────────────────────────

interface SummaryCardProps {
  curve: DoseResponseCurve;
  excludedCount: number;
  totalPoints: number;
  isInteractive: boolean;
  onClassify: (curveId: string, curveClass: string) => void;
  isClassifying: boolean;
}

/** Map fit-quality warning codes to user-facing labels. */
const FIT_WARNING_LABELS: Record<string, string> = {
  ec50_at_bound: "Hit dose-range bound — IC50 unreliable",
  ec50_outside_dose_range: "IC50 outside tested doses",
  low_r_squared: "Low R²",
};

function SummaryCard({
  curve,
  excludedCount,
  totalPoints,
  isInteractive,
  onClassify,
  isClassifying,
}: SummaryCardProps) {
  const [showClassify, setShowClassify] = useState(false);
  const includedCount = totalPoints - excludedCount;

  const warnings = curve.fit_quality_warnings ?? [];
  const isExtrapolated = warnings.includes("ec50_at_bound");
  const notFitted = isDegenerateFit(curve);

  return (
    <Card key={curve.id} className="py-4">
      <CardHeader className="pb-0">
        <CardTitle className="text-sm font-mono">
          {curve.registration_number ??
            curve.molecule_name ??
            CURVE_TYPE_LABELS[curve.curve_type as CurveType] ??
            curve.curve_type}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-2 space-y-1">
        <p className="text-sm font-mono">
          {CURVE_TYPE_LABELS[curve.curve_type as CurveType] ?? curve.curve_type}
          {" = "}
          {Number(curve.fitted_value.toPrecision(4))} {curve.fitted_unit}
          {isExtrapolated && <span className="ml-1 text-amber-600 text-xs">(extrapolated)</span>}
        </p>
        {curve.intercept_values && curve.intercept_values.length > 1 && (
          <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-muted-foreground pt-0.5">
            {curve.intercept_values.slice(1).map((iv, idx) => {
              const label =
                iv.spec.label ??
                `${iv.spec.kind.toUpperCase()}${iv.spec.level.toString().replace(/\.0$/, "")}`;
              if (iv.at_bound || !Number.isFinite(iv.value)) {
                return (
                  <span
                    key={idx}
                    className="rounded border px-1.5 py-0.5 text-amber-600"
                    title="Curve does not reach this response level"
                  >
                    {label} = at bound
                  </span>
                );
              }
              return (
                <span key={idx} className="rounded border px-1.5 py-0.5">
                  {label} = {Number(iv.value.toPrecision(4))} {curve.fitted_unit}
                  {iv.confidence_interval_low != null && iv.confidence_interval_high != null && (
                    <span className="ml-1 opacity-70">
                      [{iv.confidence_interval_low.toPrecision(3)}–
                      {iv.confidence_interval_high.toPrecision(3)}]
                    </span>
                  )}
                </span>
              );
            })}
          </div>
        )}
        <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
          <span className={cn("font-medium", rSquaredColor(curve.r_squared))}>
            R² = {curve.r_squared.toFixed(3)}
          </span>
          <span className="font-mono">Hill = {curve.hill_slope.toFixed(2)}</span>
          <span className="font-mono">Top = {curve.top.toFixed(1)}%</span>
          <span className="font-mono">Bottom = {curve.bottom.toFixed(1)}%</span>
          {curve.confidence_interval_low != null && curve.confidence_interval_high != null && (
            <span className="font-mono">
              CI: {curve.confidence_interval_low.toPrecision(3)}–
              {curve.confidence_interval_high.toPrecision(3)} {curve.fitted_unit}
            </span>
          )}
          {isInteractive && (
            <span className="text-muted-foreground">
              {includedCount}/{totalPoints} pts
            </span>
          )}
          {curve.curve_class && !isInteractive && (
            <Badge variant="outline" className="text-xs">
              {CURVE_CLASS_LABELS[curve.curve_class as CurveClass] ?? curve.curve_class}
            </Badge>
          )}
          {curve.curve_class && isInteractive && (
            <div className="relative">
              <Badge
                variant="outline"
                className="text-xs cursor-pointer hover:bg-accent transition-colors"
                onClick={() => setShowClassify((v) => !v)}
              >
                {CURVE_CLASS_LABELS[curve.curve_class as CurveClass] ?? curve.curve_class}
                <span className="ml-1 opacity-60">▾</span>
              </Badge>
              {showClassify && (
                <div className="absolute left-0 top-full z-10 mt-1 w-36 rounded-md border bg-popover shadow-md">
                  {CURVE_CLASS_OPTIONS.map((cc) => (
                    <button
                      key={cc}
                      type="button"
                      disabled={isClassifying}
                      className={cn(
                        "flex w-full items-center px-3 py-1.5 text-xs hover:bg-accent transition-colors",
                        curve.curve_class === cc && "font-medium text-primary",
                      )}
                      onClick={() => {
                        onClassify(curve.id, cc);
                        setShowClassify(false);
                      }}
                    >
                      {CURVE_CLASS_LABELS[cc]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        {(warnings.length > 0 || notFitted) && (
          <div className="flex flex-wrap gap-1 pt-1">
            {notFitted && (
              <Badge
                variant="outline"
                className="text-xs border-muted-foreground/40 bg-muted text-muted-foreground"
                title="The fit produced degenerate parameters (inactive or unfit)."
              >
                Curve not fitted (inactive or degenerate)
              </Badge>
            )}
            {warnings.map((code) => (
              <Badge
                key={code}
                variant="outline"
                className="text-xs border-amber-400/60 bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
                title={code}
              >
                ⚠️ {FIT_WARNING_LABELS[code] ?? code}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Main component ────────────────────────────────────────────────────────────

export function DoseResponseChart({
  curves,
  className,
  isInteractive = false,
  protocolConfig = null,
  yReadoutNormalization = null,
}: DoseResponseChartProps) {
  // ── Interactive state ───────────────────────────────────────────────────────
  const { mutate: refit, isPending: isRefitting } = useRefitDoseResponse();
  const { mutate: classify, isPending: isClassifying } = useClassifyDoseResponse();

  // Edit mode toggle — prevents accidental point exclusion
  const [editMode, setEditMode] = useState(false);

  // Display toggles
  const [showCI, setShowCI] = useState(true);
  const [showCrossHair, setShowCrossHair] = useState(true);
  const [showPlateaus, setShowPlateaus] = useState(false);

  // excluded indices per curve id — tracked separately from curve.excluded_points
  // so local UI state stays until query invalidation refreshes the curve
  const [excludedMap, setExcludedMap] = useState<Record<string, Set<number>>>({});

  // constraints per curve id
  const [constraintsMap, setConstraintsMap] = useState<Record<string, CurveConstraints>>({});

  // debounce refs per curve id
  const debounceRefs = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // ref for Plotly export (downloadImage)
  const plotContainerRef = useRef<HTMLDivElement>(null);

  // Seed per-curve UI from the protocol's config when provided so the
  // accordion reflects what the protocol is actually doing — a user who
  // set Top ∈ [85, 110] at the protocol level should see Range here, not
  // a misleading "Free". Editing a per-curve value sends an explicit
  // override; "Reset" clears the override and resnaps to these defaults.
  // CDD's [85,110]/[-10,10]/[0.9,1.1] only make sense for percent-scale
  // readouts (% inhibition / activation / control). For raw signal,
  // Z-score, NONE, etc., we leave range fields empty so the user must
  // explicitly choose ranges instead of inheriting bogus percent bounds.
  const getConstraints = useCallback(
    (curve: DoseResponseCurve): CurveConstraints =>
      constraintsMap[curve.id] ??
      defaultConstraintsFor(curve, protocolConfig, yReadoutNormalization),
    [constraintsMap, protocolConfig, yReadoutNormalization],
  );

  const getExcluded = useCallback(
    (curveId: string): Set<number> => excludedMap[curveId] ?? new Set(),
    [excludedMap],
  );

  const callRefit = useCallback(
    (curve: DoseResponseCurve, excluded: Set<number>, constraints: CurveConstraints) => {
      // Send `override_<param>` so the backend treats this curve's settings
      // as authoritative for that param (Free included). Only the values
      // for the active mode ship — the rest go null.
      refit({
        curveId: curve.id,
        input: {
          excluded_point_indices: Array.from(excluded),
          hill_slope_constraint:
            constraints.hillSlope !== "unconstrained" ? constraints.hillSlope : null,
          override_top: true,
          top_constraint: constraints.topMode === "lock" ? constraints.topValue : null,
          top_constraint_min: constraints.topMode === "range" ? constraints.topMin : null,
          top_constraint_max: constraints.topMode === "range" ? constraints.topMax : null,
          override_bottom: true,
          bottom_constraint: constraints.bottomMode === "lock" ? constraints.bottomValue : null,
          bottom_constraint_min: constraints.bottomMode === "range" ? constraints.bottomMin : null,
          bottom_constraint_max: constraints.bottomMode === "range" ? constraints.bottomMax : null,
          override_hill: true,
          hill_slope_min: constraints.hillCustomRange ? constraints.hillMin : null,
          hill_slope_max: constraints.hillCustomRange ? constraints.hillMax : null,
        },
      });
    },
    [refit],
  );

  const handleConstraintChange = useCallback(
    (curve: DoseResponseCurve, patch: Partial<CurveConstraints>) => {
      const current = getConstraints(curve);
      const next = { ...current, ...patch };
      setConstraintsMap((prev) => ({ ...prev, [curve.id]: next }));

      if (debounceRefs.current[curve.id]) {
        clearTimeout(debounceRefs.current[curve.id]);
      }
      // Only fire refit when the active mode's required values are
      // populated and consistent — otherwise we'd ship NaN/null to the
      // backend and provoke a 500.
      if (!constraintsValid(next)) return;
      debounceRefs.current[curve.id] = setTimeout(() => {
        callRefit(curve, getExcluded(curve.id), next);
      }, 500);
    },
    [getConstraints, getExcluded, callRefit],
  );

  const handleReset = useCallback(
    (curve: DoseResponseCurve) => {
      setExcludedMap((prev) => ({ ...prev, [curve.id]: new Set() }));
      setConstraintsMap((prev) => ({
        ...prev,
        [curve.id]: defaultConstraintsFor(curve, protocolConfig, yReadoutNormalization),
      }));
      // Reset = clear per-curve overrides, fall back to protocol's config.
      refit({ curveId: curve.id, input: { excluded_point_indices: [] } });
    },
    [refit, protocolConfig, yReadoutNormalization],
  );

  const handleClassify = useCallback(
    (curveId: string, curveClass: string) => {
      classify({ curveId, input: { curve_class: curveClass } });
    },
    [classify],
  );

  // ── Early return ────────────────────────────────────────────────────────────
  if (curves.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-dashed p-12 text-sm text-muted-foreground">
        No dose-response curves available.
      </div>
    );
  }

  // ── Build Plotly traces ─────────────────────────────────────────────────────
  // PlotTrace / PlotShape / PlotAnnotation: the project doesn't depend on
  // @types/plotly.js (react-plotly.js's wrapper here uses PlotProps with
  // Record<string, unknown>). We mirror that shape for trace/shape/annotation
  // builders so call sites don't need `any`.
  type PlotTrace = Record<string, unknown>;
  type PlotShape = Record<string, unknown>;
  type PlotAnnotation = Record<string, unknown>;
  const traces: PlotTrace[] = [];

  // Track trace index → (curveId, pointIndex within included array) for click handling
  // Each included-points trace gets a traceIndex so we can map clicks back.
  const traceIndexToCurve: Array<{ curveId: string; type: "included" | "excluded" }> = [];

  for (let i = 0; i < curves.length; i++) {
    const curve = curves[i];
    const color = TRACE_COLORS[i % TRACE_COLORS.length];
    const group = `curve-${curve.id}`;
    const curveTypeLabel = CURVE_TYPE_LABELS[curve.curve_type as CurveType] ?? curve.curve_type;
    // Prefer the canonical registration number (CV-NNNNN) for trace labels
    // — analysts identify compounds by reg id, not free-text name. Fall back
    // to the molecule name only when the curve carries no reg id.
    const compoundLabel = curve.registration_number ?? curve.molecule_name ?? null;
    const label = compoundLabel ? `${compoundLabel} (${curveTypeLabel})` : curveTypeLabel;

    // Merge server excluded_points back into raw_data for interactive mode:
    // In interactive mode we manage exclusions locally.
    // Displayed included = raw_data filtered by local excludedMap
    // Displayed excluded = server excluded_points + locally excluded from raw_data
    const serverIncluded = extractPoints(curve.raw_data);
    const serverExcluded = extractPoints(curve.excluded_points);
    const localExcluded = getExcluded(curve.id);

    let includedX: number[];
    let includedY: number[];
    let manualExcludedX: number[];
    let manualExcludedY: number[];
    let autoExcludedX: number[];
    let autoExcludedY: number[];

    if (isInteractive) {
      includedX = serverIncluded.x.filter((_, idx) => !localExcluded.has(idx));
      includedY = serverIncluded.y.filter((_, idx) => !localExcluded.has(idx));
      // locally excluded from raw_data -> treat as manual
      manualExcludedX = serverIncluded.x.filter((_, idx) => localExcluded.has(idx));
      manualExcludedY = serverIncluded.y.filter((_, idx) => localExcluded.has(idx));
      // server excluded -> split by reason
      autoExcludedX = serverExcluded.x.filter(
        (_, idx) => serverExcluded.reasons[idx] === "auto_3sigma",
      );
      autoExcludedY = serverExcluded.y.filter(
        (_, idx) => serverExcluded.reasons[idx] === "auto_3sigma",
      );
      manualExcludedX = [
        ...manualExcludedX,
        ...serverExcluded.x.filter((_, idx) => serverExcluded.reasons[idx] !== "auto_3sigma"),
      ];
      manualExcludedY = [
        ...manualExcludedY,
        ...serverExcluded.y.filter((_, idx) => serverExcluded.reasons[idx] !== "auto_3sigma"),
      ];
    } else {
      includedX = serverIncluded.x;
      includedY = serverIncluded.y;
      autoExcludedX = serverExcluded.x.filter(
        (_, idx) => serverExcluded.reasons[idx] === "auto_3sigma",
      );
      autoExcludedY = serverExcluded.y.filter(
        (_, idx) => serverExcluded.reasons[idx] === "auto_3sigma",
      );
      manualExcludedX = serverExcluded.x.filter(
        (_, idx) => serverExcluded.reasons[idx] !== "auto_3sigma",
      );
      manualExcludedY = serverExcluded.y.filter(
        (_, idx) => serverExcluded.reasons[idx] !== "auto_3sigma",
      );
    }

    // Filter out NaN/non-positive values: log10 explodes on them and
    // `fitted_value` may be NaN/0 for degenerate fits.
    const finiteFitted = Number.isFinite(curve.fitted_value) && curve.fitted_value > 0;
    const allX = [
      ...serverIncluded.x,
      ...serverExcluded.x,
      ...(finiteFitted ? [curve.fitted_value] : []),
    ].filter((v) => Number.isFinite(v) && v > 0);
    let xMin: number;
    let xMax: number;
    if (allX.length > 0) {
      xMin = Math.max(Math.min(...allX) * X_AXIS_MIN_RATIO, X_AXIS_FLOOR);
      xMax = Math.max(...allX) * X_AXIS_MAX_RATIO;
    } else if (finiteFitted) {
      xMin = Math.max(curve.fitted_value * X_AXIS_FALLBACK_MIN_RATIO, X_AXIS_FLOOR);
      xMax = curve.fitted_value * X_AXIS_FALLBACK_MAX_RATIO;
    } else {
      // No usable scale info — pick a generic µM-range default rather
      // than feeding NaN into Plotly's log axis.
      xMin = 0.001;
      xMax = 1000;
    }

    // Compute replicate stats for error bars
    const { meanX, meanY, sdY, replicateX, replicateY } = computeReplicateStats(
      includedX,
      includedY,
    );
    const hasReplicates = replicateX.length > 0;

    // Individual replicate scatter (semi-transparent, behind means) — only when replicates exist
    if (hasReplicates) {
      traces.push({
        type: "scatter",
        mode: "markers",
        name: `${label} replicates`,
        legendgroup: group,
        x: replicateX,
        y: replicateY,
        marker: {
          color,
          size: PLOT_MARKER.REPLICATE_SIZE,
          symbol: "circle",
          opacity: PLOT_MARKER.REPLICATE_OPACITY,
        },
        showlegend: false,
        hoverinfo: "skip",
      });
    }

    // Included data points (mean values with error bars when replicates exist)
    const displayX = hasReplicates ? meanX : includedX;
    const displayY = hasReplicates ? meanY : includedY;

    if (displayX.length > 0) {
      const traceIdx = traces.length;
      traceIndexToCurve[traceIdx] = { curveId: curve.id, type: "included" };
      traces.push({
        type: "scatter",
        mode: "markers",
        name: label,
        legendgroup: group,
        x: displayX,
        y: displayY,
        marker: {
          color,
          size: isInteractive ? PLOT_MARKER.POINT_SIZE_INTERACTIVE : PLOT_MARKER.POINT_SIZE_STATIC,
          symbol: "circle",
          line: isInteractive ? { color: "rgba(255,255,255,0.3)", width: 1 } : undefined,
        },
        ...(hasReplicates && {
          error_y: {
            type: "data",
            array: sdY,
            visible: true,
            color,
            thickness: 1.5,
            width: 4,
          },
        }),
        showlegend: true,
        hovertemplate: editMode
          ? "x: %{x:.4g}<br>y: %{y:.4g}<br><i>click to exclude</i><extra></extra>"
          : "x: %{x:.4g}<br>y: %{y:.4g}<extra></extra>",
      });
    }

    // Manually excluded points (x marker)
    if (manualExcludedX.length > 0) {
      const traceIdx = traces.length;
      traceIndexToCurve[traceIdx] = { curveId: curve.id, type: "excluded" };
      traces.push({
        type: "scatter",
        mode: "markers",
        name: `${label} (excluded)`,
        legendgroup: group,
        x: manualExcludedX,
        y: manualExcludedY,
        marker: {
          color,
          size: PLOT_MARKER.EXCLUDED_SIZE,
          symbol: "x",
          opacity: PLOT_MARKER.MANUAL_EXCLUDED_OPACITY,
        },
        showlegend: false,
        hovertemplate: editMode
          ? "x: %{x:.4g}<br>y: %{y:.4g}<br><i>click to include</i><extra></extra>"
          : "x: %{x:.4g}<br>y: %{y:.4g}<extra></extra>",
      });
    }

    // Auto-excluded points (diamond marker, 3σ outliers)
    if (autoExcludedX.length > 0) {
      traces.push({
        type: "scatter",
        mode: "markers",
        name: `${label} (auto-excluded)`,
        legendgroup: group,
        x: autoExcludedX,
        y: autoExcludedY,
        marker: {
          color,
          size: PLOT_MARKER.EXCLUDED_SIZE,
          symbol: "diamond",
          opacity: PLOT_MARKER.AUTO_EXCLUDED_OPACITY,
        },
        showlegend: false,
        hovertemplate:
          "x: %{x:.4g}<br>y: %{y:.4g}<br><i>Auto-excluded (3\u03c3 outlier)</i><extra></extra>",
      });
    }

    // Fitted 4PL sigmoid line (non-clickable). Skip for inactive / failed
    // fits — there's no meaningful sigmoid to draw, just data points.
    const skipFitLine = isDegenerateFit(curve);
    if (!skipFitLine) {
      const { x: lineX, y: lineY } = generate4PLCurve(curve, xMin, xMax);
      traces.push({
        type: "scatter",
        mode: "lines",
        name: `${label} fit`,
        legendgroup: group,
        x: lineX,
        y: lineY,
        line: { color, width: 2 },
        showlegend: includedX.length === 0,
        hoverinfo: "skip",
      });
    }

    // Confidence interval band (shaded area between CI low/high EC50 curves)
    if (
      !skipFitLine &&
      showCI &&
      curve.confidence_interval_low != null &&
      curve.confidence_interval_high != null
    ) {
      const ciLowCurve = { ...curve, fitted_value: curve.confidence_interval_low };
      const ciHighCurve = { ...curve, fitted_value: curve.confidence_interval_high };
      const { x: ciX, y: ciLowY } = generate4PLCurve(ciLowCurve, xMin, xMax);
      const { y: ciHighY } = generate4PLCurve(ciHighCurve, xMin, xMax);

      // Upper bound
      traces.push({
        type: "scatter",
        mode: "lines",
        x: ciX,
        y: ciHighY,
        line: { width: 0 },
        legendgroup: group,
        showlegend: false,
        hoverinfo: "skip",
      });
      // Lower bound (fill to upper)
      traces.push({
        type: "scatter",
        mode: "lines",
        x: ciX,
        y: ciLowY,
        line: { width: 0 },
        fill: "tonexty",
        fillcolor: `${color}15`,
        legendgroup: group,
        showlegend: false,
        hoverinfo: "skip",
      });
    }
  }

  // ── Plotly click handler ────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handlePlotClick = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (event: any) => {
      if (!isInteractive || !editMode) return;
      const pt = event?.points?.[0];
      if (!pt) return;

      const traceIdx: number = pt.curveNumber;
      const pointIdx: number = pt.pointIndex;
      const traceInfo = traceIndexToCurve[traceIdx];
      if (!traceInfo) return;

      const { curveId, type } = traceInfo;
      const curve = curves.find((c) => c.id === curveId);
      if (!curve) return;

      const currentExcluded = new Set(getExcluded(curveId));

      if (type === "included") {
        // Find the actual index in the original raw_data array
        // (accounting for already-excluded points shifting display indices)
        const localExcluded = getExcluded(curveId);
        let displayIdx = 0;
        let originalIdx = -1;
        for (let k = 0; k < (curve.raw_data?.length ?? 0); k++) {
          if (!localExcluded.has(k)) {
            if (displayIdx === pointIdx) {
              originalIdx = k;
              break;
            }
            displayIdx++;
          }
        }
        if (originalIdx >= 0) {
          currentExcluded.add(originalIdx);
        }
      } else {
        // excluded trace — find the original index in the raw_data that maps to this display point
        // The excluded trace shows: locally excluded from raw_data first, then server excluded_points.
        // We only support toggling locally excluded points back (server excluded_points are read-only in UI).
        const localExcluded = getExcluded(curveId);
        const locallyExcludedIndices = Array.from(localExcluded);
        if (pointIdx < locallyExcludedIndices.length) {
          const originalIdx = locallyExcludedIndices[pointIdx];
          currentExcluded.delete(originalIdx);
        }
        // If pointIdx >= locallyExcludedIndices.length → server-excluded point, ignore click
      }

      setExcludedMap((prev) => ({ ...prev, [curveId]: currentExcluded }));
      const constraints = getConstraints(curve);
      callRefit(curve, currentExcluded, constraints);
    },
    [isInteractive, editMode, curves, getExcluded, getConstraints, callRefit, traceIndexToCurve],
  );

  // Build overlay shapes and annotations based on toggle state
  const shapes: PlotShape[] = [];
  const annotations: PlotAnnotation[] = [];
  for (let i = 0; i < curves.length; i++) {
    const curve = curves[i];
    const color = TRACE_COLORS[i % TRACE_COLORS.length];
    const midY = (curve.top + curve.bottom) / 2;
    const ec50 = curve.fitted_value;
    const unitLabel = curve.fitted_unit ? ` ${curve.fitted_unit}` : "";
    const degenerate = isDegenerateFit(curve);

    // Cross-hair: dotted lines + marker + label at (EC50, midpoint).
    // Suppress for inactive/degenerate fits — the EC50 isn't meaningful.
    if (showCrossHair && !degenerate) {
      shapes.push({
        type: "line",
        xref: "paper",
        x0: 0,
        x1: 1,
        yref: "y",
        y0: midY,
        y1: midY,
        line: { color, width: 1, dash: "dot" },
        opacity: 0.4,
      });
      shapes.push({
        type: "line",
        xref: "x",
        x0: ec50,
        x1: ec50,
        yref: "paper",
        y0: 0,
        y1: 1,
        line: { color, width: 1, dash: "dot" },
        opacity: 0.4,
      });
      traces.push({
        type: "scatter",
        mode: "markers",
        x: [ec50],
        y: [midY],
        marker: {
          color: CHART_COLORS.warning,
          size: 10,
          line: { color: CHART_COLORS.error, width: 2 },
          symbol: "circle",
        },
        showlegend: false,
        hovertemplate: `${CURVE_TYPE_LABELS[curve.curve_type as CurveType] ?? curve.curve_type} = ${ec50.toPrecision(3)}${unitLabel}<extra></extra>`,
      });
      annotations.push({
        x: Math.log10(ec50),
        y: midY,
        xref: "x",
        yref: "y",
        text: `<b>${ec50.toPrecision(3)}${unitLabel}</b>`,
        showarrow: true,
        arrowhead: 2,
        arrowsize: 0.8,
        arrowcolor: CHART_COLORS.error,
        ax: 0,
        ay: -35,
        font: { color: CHART_COLORS.error, size: 11 },
      });
    }

    // Additional intercepts (e.g. IC90 alongside the primary IC50). The first
    // entry of intercept_values is the primary (already drawn above as the
    // cross-hair); slice(1) gives the extras. Skip at-bound / non-finite —
    // the curve doesn't reach that response level so a vertical line would
    // be misleading. Different dash style ("longdash" vs the primary's "dot")
    // keeps the primary visually distinct.
    if (
      showCrossHair &&
      !degenerate &&
      curve.intercept_values &&
      curve.intercept_values.length > 1
    ) {
      for (const iv of curve.intercept_values.slice(1)) {
        if (iv.at_bound || !Number.isFinite(iv.value)) continue;
        const yLevel =
          iv.spec.basis === "relative_percent"
            ? curve.bottom + iv.spec.level * (curve.top - curve.bottom)
            : iv.spec.level;
        const label =
          iv.spec.label ??
          `${iv.spec.kind.toUpperCase()}${iv.spec.level.toString().replace(/\.0$/, "")}`;
        shapes.push({
          type: "line",
          xref: "x",
          x0: iv.value,
          x1: iv.value,
          yref: "paper",
          y0: 0,
          y1: 1,
          line: { color, width: 1, dash: "longdash" },
          opacity: 0.45,
        });
        traces.push({
          type: "scatter",
          mode: "markers",
          x: [iv.value],
          y: [yLevel],
          marker: {
            color,
            size: 8,
            line: { color: CHART_AXIS.tick, width: 1 },
            symbol: "diamond",
          },
          showlegend: false,
          hovertemplate: `${label} = ${iv.value.toPrecision(3)}${unitLabel}<extra></extra>`,
        });
        annotations.push({
          x: Math.log10(iv.value),
          y: yLevel,
          xref: "x",
          yref: "y",
          text: `<b>${label}</b>`,
          showarrow: false,
          font: { color, size: 10 },
          xanchor: "left",
          yanchor: "bottom",
          xshift: 4,
          yshift: 2,
        });
      }
    }

    // Plateau lines: horizontal dashed at top and bottom asymptotes
    if (showPlateaus && !degenerate) {
      shapes.push({
        type: "line",
        xref: "paper",
        x0: 0,
        x1: 1,
        yref: "y",
        y0: curve.top,
        y1: curve.top,
        line: { color, width: 1, dash: "dash" },
        opacity: 0.3,
      });
      shapes.push({
        type: "line",
        xref: "paper",
        x0: 0,
        x1: 1,
        yref: "y",
        y0: curve.bottom,
        y1: curve.bottom,
        line: { color, width: 1, dash: "dash" },
        opacity: 0.3,
      });
      annotations.push({
        x: 1,
        y: curve.top,
        xref: "paper",
        yref: "y",
        text: `Top: ${curve.top.toFixed(1)}%`,
        showarrow: false,
        font: { color, size: 9 },
        xanchor: "right",
      });
      annotations.push({
        x: 1,
        y: curve.bottom,
        xref: "paper",
        yref: "y",
        text: `Bottom: ${curve.bottom.toFixed(1)}%`,
        showarrow: false,
        font: { color, size: 9 },
        xanchor: "right",
      });
    }
  }

  const layout = {
    height: 350,
    autosize: true,
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: CHART_AXIS.tick },
    xaxis: {
      title: {
        text: curves[0]?.fitted_unit ? `Concentration (${curves[0].fitted_unit})` : "Concentration",
      },
      type: "log" as const,
      gridcolor: "rgba(113,113,122,0.2)",
      zerolinecolor: "rgba(113,113,122,0.3)",
    },
    yaxis: {
      title: { text: "Response (%)" },
      gridcolor: "rgba(113,113,122,0.2)",
      zerolinecolor: "rgba(113,113,122,0.3)",
    },
    legend: {
      orientation: "h" as const,
      y: -0.2,
      font: { color: CHART_AXIS.tick },
    },
    shapes,
    annotations,
    margin: { t: 20, b: 60, l: 60, r: 20 },
    clickmode: editMode ? "event" : undefined,
    dragmode: editMode ? false : "zoom",
  };

  const config = {
    displayModeBar: false,
    responsive: true,
    modeBarButtonsToRemove: ["lasso2d", "select2d"] as string[],
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* Controls bar */}
      <div className="flex items-center gap-4 flex-wrap">
        {isInteractive && (
          <Button
            variant={editMode ? "default" : "outline"}
            size="sm"
            onClick={() => setEditMode((v) => !v)}
          >
            {editMode ? "Done Editing" : "Edit Points"}
          </Button>
        )}
        {editMode && (
          <span className="text-xs text-muted-foreground">
            Click data points to exclude/include them.
          </span>
        )}
        {!editMode && (
          <>
            <div className="flex items-center gap-3 ml-auto text-xs text-muted-foreground">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <Checkbox
                  checked={showCrossHair}
                  onCheckedChange={(v) => setShowCrossHair(v === true)}
                />
                {CURVE_TYPE_LABELS[curves[0]?.curve_type as CurveType] ?? "Fitted"} marker
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <Checkbox checked={showCI} onCheckedChange={(v) => setShowCI(v === true)} />
                95% CI band
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <Checkbox
                  checked={showPlateaus}
                  onCheckedChange={(v) => setShowPlateaus(v === true)}
                />
                Top/Bottom
              </label>
            </div>
            <div className="flex items-center gap-1.5 ml-4 border-l pl-4 border-border">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => {
                  const plotEl = plotContainerRef.current?.querySelector(
                    ".js-plotly-plot",
                  ) as HTMLElement | null;
                  if (plotEl) {
                    getPlotlyGlobal()?.downloadImage?.(plotEl, {
                      format: "png",
                      width: 1200,
                      height: 600,
                      filename: "dose-response",
                    });
                  }
                }}
              >
                <ImageIcon className="mr-1 h-3.5 w-3.5" />
                PNG
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => {
                  const plotEl = plotContainerRef.current?.querySelector(
                    ".js-plotly-plot",
                  ) as HTMLElement | null;
                  if (plotEl) {
                    getPlotlyGlobal()?.downloadImage?.(plotEl, {
                      format: "svg",
                      width: 1200,
                      height: 600,
                      filename: "dose-response",
                    });
                  }
                }}
              >
                <Download className="mr-1 h-3.5 w-3.5" />
                SVG
              </Button>
            </div>
          </>
        )}
      </div>

      <div ref={plotContainerRef}>
        <Plot
          data={traces}
          layout={layout}
          config={config}
          style={{ width: "100%" }}
          useResizeHandler
          onClick={editMode ? handlePlotClick : undefined}
        />
      </div>

      {/* Per-curve constraint controls (interactive only) */}
      {isInteractive && curves.length > 0 && (
        <div className="space-y-3">
          {curves.map((curve) => (
            <CurveControls
              key={curve.id}
              curve={curve}
              excludedIndices={getExcluded(curve.id)}
              constraints={getConstraints(curve)}
              onConstraintChange={(patch) => handleConstraintChange(curve, patch)}
              onReset={() => handleReset(curve)}
              isPending={isRefitting}
            />
          ))}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {curves.map((curve) => {
          const totalPoints = (curve.raw_data?.length ?? 0) + (curve.excluded_points?.length ?? 0);
          const localExcluded = getExcluded(curve.id);
          return (
            <SummaryCard
              key={curve.id}
              curve={curve}
              excludedCount={localExcluded.size}
              totalPoints={totalPoints}
              isInteractive={isInteractive}
              onClassify={handleClassify}
              isClassifying={isClassifying}
            />
          );
        })}
      </div>
    </div>
  );
}
