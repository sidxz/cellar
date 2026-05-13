/**
 * Curve-constraint types, factory, and validators.
 *
 * Pure module — no React, no DOM, safe to import anywhere including tests
 * and server components.
 */

import { PERCENT_FIT_RANGES } from "./readout-constants";
import { isPercentNormalization } from "./dose-response-math";
import type { DoseResponseConfig, DoseResponseCurve } from "../types";

// ─── Types ─────────────────────────────────────────────────────────────────────

export type ParamMode = "free" | "range" | "lock";

export interface CurveConstraints {
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

// ─── Validators ────────────────────────────────────────────────────────────────

export function parseInputOrNull(s: string): number | null {
  if (s.trim() === "") return null;
  const v = Number.parseFloat(s);
  return Number.isFinite(v) ? v : null;
}

export function isRangeValid(min: number | null, max: number | null): boolean {
  return min != null && max != null && Number.isFinite(min) && Number.isFinite(max) && min < max;
}

export function constraintsValid(c: CurveConstraints): boolean {
  if (c.topMode === "lock" && (c.topValue == null || !Number.isFinite(c.topValue))) return false;
  if (c.topMode === "range" && !isRangeValid(c.topMin, c.topMax)) return false;
  if (c.bottomMode === "lock" && (c.bottomValue == null || !Number.isFinite(c.bottomValue)))
    return false;
  if (c.bottomMode === "range" && !isRangeValid(c.bottomMin, c.bottomMax)) return false;
  if (c.hillCustomRange && !isRangeValid(c.hillMin, c.hillMax)) return false;
  return true;
}

// ─── Factory ───────────────────────────────────────────────────────────────────

/** Pure helper: derive the per-curve UI defaults from the protocol's config
 *  and the Y readout's normalization. Hoisted out of the component so its
 *  identity is stable across renders — letting useCallback's exhaustive-deps
 *  list its actual inputs (protocolConfig, yReadoutNormalization) instead of
 *  swallowing the warning. */
export function defaultConstraintsFor(
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
