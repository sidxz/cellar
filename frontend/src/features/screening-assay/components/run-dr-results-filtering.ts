import { doseRange, findInterceptValue, formatInterceptDisplay } from "../lib/intercept-label";
import { meetsRule } from "../lib/melt-hits";
import type { CurveClass, InterceptSpec } from "../types";
import type { CompoundCurveRow } from "./run-dr-results-transforms";
import { doseUnitScale, isConvertibleDoseUnit, normalizeDoseUnit } from "./run-dr-results-view";

export type RunCurveClassFilter = CurveClass | "unclassified";
export type PotencyComparison = "lt" | "lte" | "gt" | "gte";

export interface RunPotencyFilter {
  spec: InterceptSpec | null;
  primary: boolean;
  operator: PotencyComparison;
  threshold: number;
  /** The unit the threshold was entered in, independent of later display-unit changes. */
  unit: string;
}

export function matchesRunViewFilters(
  row: CompoundCurveRow,
  classes: readonly RunCurveClassFilter[],
  potency: RunPotencyFilter | null,
): boolean {
  if (classes.length > 0 && !classes.includes(row.curve_class ?? "unclassified")) return false;
  if (!potency) return true;
  const nativeUnit = normalizeDoseUnit(row.fitted_unit);
  const filterUnit = normalizeDoseUnit(potency.unit);
  if (
    nativeUnit !== filterUnit &&
    (!isConvertibleDoseUnit(nativeUnit) || !isConvertibleDoseUnit(filterUnit))
  )
    return false;

  const intercept = potency.spec
    ? findInterceptValue(row.intercept_values, potency.spec)
    : row.intercept_values?.[0];
  const display = formatInterceptDisplay({
    value: intercept?.value ?? (potency.primary ? row.fitted_value : null),
    at_bound: intercept?.at_bound,
    qualifier: intercept?.qualifier,
    primary: potency.primary,
    curve_class: row.curve_class,
    ...doseRange(row.data_points),
  });
  const { value, qualifier } = display.reported;
  if (value == null || qualifier === "nd") return false;

  // Use the existing bound-aware comparison: a censored result matches only when every
  // value it could represent meets the threshold, rather than comparing its sorting sentinel.
  return meetsRule(
    value * doseUnitScale(row.fitted_unit, potency.unit),
    { readout_name: "Potency", operator: potency.operator, value: potency.threshold },
    qualifier,
  );
}
