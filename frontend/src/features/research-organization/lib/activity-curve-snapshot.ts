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
  // The sigmoid sits at the fit's own midpoint (`curve_params.fitted_value`): the cell's value
  // is the reported one, a bound ("> 100") or none (n.d.). A snapshot stored before the field
  // existed falls back to the reported value; an inactive curve's ND to its first intercept,
  // since its flat points are what the chemist checks to trust the call.
  const fittedValue =
    av.curve_params.fitted_value ??
    av.value ??
    (av.curve_params.curve_class === "inactive" ||
    av.curve_params.curve_class === "active_all_doses"
      ? av.intercept_values?.[0]?.value
      : null);
  if (fittedValue == null) return null;
  // Colored by the primary itself (its reported value): no second marker.
  const selectedIntercept =
    selected?.value != null && Number.isFinite(selected.value) && selected.value !== av.value
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
    // With their stored qualifiers: no line goes at a censored or n.d. headline.
    intercept_values: av.intercept_values ?? null,
    additional_curves: av.additional_curves ?? null,
    aggregate: av.aggregate ?? null,
    selected_intercept: selectedIntercept,
  };
}
