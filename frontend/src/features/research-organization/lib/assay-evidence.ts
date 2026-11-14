import {
  formatInterceptDisplay,
  maxDoseFromRawData,
} from "@/features/screening-assay/lib/intercept-label";
import type { ActivityValue, InterceptKey } from "../types";
import { type AggregationMode, wireToAggregationMode } from "./use-aggregation-mode";

export function activityEndpoint(
  av: ActivityValue,
  spec: InterceptKey | null,
  isPrimary: boolean,
  fallbackMode: AggregationMode,
) {
  const aggregate = av.intercept_aggregates?.find((a) =>
    spec ? a.spec.kind === spec.kind && a.spec.level === spec.level : a.spec.kind === "primary",
  );
  const iv = spec
    ? av.intercept_values?.find((v) => v.spec.kind === spec.kind && v.spec.level === spec.level)
    : undefined;
  // A resolved null is meaningful: never fall back to a representative fit.
  const value = aggregate ? aggregate.selected_value : (iv?.value ?? (isPrimary ? av.value : null));
  const qualifier = aggregate ? aggregate.selected_qualifier : isPrimary ? av.qualifier : null;
  const mode = av.selection_rule ? wireToAggregationMode(av.selection_rule) : fallbackMode;
  const display = formatInterceptDisplay({
    value,
    at_bound: aggregate ? false : iv?.at_bound,
    curve_class: aggregate ? null : av.curve_params?.curve_class,
    max_dose: maxDoseFromRawData(av.raw_data),
    runCount: av.run_count ?? 1,
    mode,
    foldRange: aggregate?.aggregate_stats?.fold_range,
    disagreement: aggregate?.disagreement_flag ?? av.disagreement_flag,
  });
  if (qualifier === "nd" || qualifier === "excluded") {
    const text = qualifier === "nd" ? "ND" : "Excluded";
    Object.assign(display, {
      kind: "nd",
      primary: text,
      text,
      sortValue: null,
      tooltip:
        qualifier === "nd"
          ? "ND = Not Determined. No reportable endpoint."
          : "Excluded from the reported result.",
    });
  }
  if ((qualifier === ">" || qualifier === "<") && display.kind === "scalar") {
    const text = `${qualifier} ${display.primary}`;
    Object.assign(display, {
      kind: "qualifier",
      primary: text,
      text,
      warning: true,
      sortValue: qualifier === ">" ? Number.POSITIVE_INFINITY : value,
      tooltip: "Reported concentration bound; this is not an exact endpoint.",
    });
  }
  return { aggregate, value, qualifier, display, mode };
}

/** Whether a value's unit is the one its column header already states, so the
 *  cell can leave it out. "uM", "μM" (Greek mu) and "µM" (micro sign) match. */
export function sameUnit(a: string | null | undefined, b: string | null | undefined): boolean {
  const canonical = (u: string | null | undefined) => u?.trim().replace(/^[uμ]/, "µ") ?? "";
  return !!a && canonical(a) === canonical(b);
}

export function molarFactor(unit: string | null): number | null {
  const factors: Record<string, number> = {
    m: 1,
    mm: 1e-3,
    um: 1e-6,
    µm: 1e-6,
    μm: 1e-6,
    nm: 1e-9,
    pm: 1e-12,
    fm: 1e-15,
  };
  return unit ? (factors[unit.trim().toLowerCase()] ?? null) : null;
}

export function selectivityRatio(
  target: { av?: ActivityValue; spec: InterceptKey | null; isPrimary: boolean },
  counter: { av?: ActivityValue; spec: InterceptKey | null; isPrimary: boolean },
  mode: AggregationMode,
): { value: number | null; reason: string } {
  if (!target.av || !counter.av) return { value: null, reason: "Missing assay result" };
  const a = activityEndpoint(target.av, target.spec, target.isPrimary, mode);
  const b = activityEndpoint(counter.av, counter.spec, counter.isPrimary, mode);
  if (
    a.value == null ||
    b.value == null ||
    [a, b].some(
      (x) =>
        x.display.kind !== "scalar" ||
        (x.qualifier && x.qualifier !== "=") ||
        x.value == null ||
        x.value <= 0 ||
        !Number.isFinite(x.value),
    )
  ) {
    return { value: null, reason: "Requires two positive, unqualified endpoints" };
  }
  const af = molarFactor(target.av.unit);
  const bf = molarFactor(counter.av.unit);
  if (af == null || bf == null)
    return { value: null, reason: "Missing or incompatible concentration units" };
  const value = (b.value * bf) / (a.value * af);
  return Number.isFinite(value)
    ? { value, reason: "Counter / target, converted to the same concentration unit" }
    : { value: null, reason: "Ratio outside numeric range" };
}
