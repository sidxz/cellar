import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import type { ActivityValue } from "../types";

/**
 * Map a dose-response `ActivityValue` snapshot → the shared `CurveSnapshot`,
 * or null when the value isn't a usable DR fit (no raw points, wrong source,
 * no curve params, or no fitted value). Single source of truth for both the
 * search/SAR table cell and the SAR heatmap.
 */
export function activityValueToCurveSnapshot(
  av: ActivityValue | undefined | null,
): CurveSnapshot | null {
  if (
    !av ||
    !av.raw_data ||
    av.raw_data.length === 0 ||
    av.source !== "dose_response" ||
    av.curve_params == null ||
    av.value == null
  ) {
    return null;
  }
  return {
    fitted_value: av.value,
    top: av.curve_params.top,
    bottom: av.curve_params.bottom,
    hill_slope: av.curve_params.hill_slope,
    r_squared: av.r_squared,
    curve_class: av.curve_params.curve_class ?? null,
    raw_data: av.raw_data,
    additional_curves: av.additional_curves ?? null,
    aggregate: av.aggregate ?? null,
  };
}
