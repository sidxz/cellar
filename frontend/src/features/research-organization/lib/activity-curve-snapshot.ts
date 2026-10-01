import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import type { ActivityValue } from "../types";

/**
 * Map a dose-response `ActivityValue` snapshot → the shared `CurveSnapshot`,
 * or null when the value isn't a usable DR fit (no raw points, wrong source,
 * no curve params, or no fitted value). Single source of truth for both the
 * search/SAR table cell and the SAR heatmap.
 *
 * `selected` is the scalar + label of the channel the surface is coloring by
 * (e.g. IC90). When it differs from the primary `av.value`, it's surfaced as
 * `selected_intercept` so the figure draws a distinct marker there — the
 * expanded curve then agrees with the colored column instead of always marking
 * the primary intercept.
 */
export function activityValueToCurveSnapshot(
  av: ActivityValue | undefined | null,
  selected?: { value: number | null | undefined; label: string },
): CurveSnapshot | null {
  if (
    !av ||
    !av.raw_data ||
    av.raw_data.length === 0 ||
    av.source !== "dose_response" ||
    av.curve_params == null
  ) {
    return null;
  }
  // An inactive curve reports ND (value null), yet its flat points are what
  // the chemist checks to trust the call. The figure draws inactive curves as
  // markers only (no sigmoid, no intercept line); the fit's own scalar just
  // satisfies the snapshot shape.
  const fittedValue =
    av.value ??
    (av.curve_params.curve_class === "inactive" ? av.intercept_values?.[0]?.value : null);
  if (fittedValue == null) return null;
  const selectedIntercept =
    selected?.value != null && Number.isFinite(selected.value) && selected.value !== fittedValue
      ? { value: selected.value, label: selected.label }
      : null;
  return {
    fitted_value: fittedValue,
    top: av.curve_params.top,
    bottom: av.curve_params.bottom,
    hill_slope: av.curve_params.hill_slope,
    r_squared: av.r_squared,
    curve_class: av.curve_params.curve_class ?? null,
    raw_data: av.raw_data,
    additional_curves: av.additional_curves ?? null,
    aggregate: av.aggregate ?? null,
    selected_intercept: selectedIntercept,
  };
}
