import type { ActivityValue } from "@/features/research-organization/types";
import type { CampaignMeasurementResponse } from "../types";
import type { DoseResponseCurveResponse } from "@/shared/lib/api/model";

/**
 * Compose an ActivityValue (the shape consumed by Search's DoseResponseCell)
 * from a campaign measurement + its matching dose-response curve. Returns
 * null for `nd` / `excluded` qualifiers (the cell should render "—").
 */
export function measurementToActivity(
  m: CampaignMeasurementResponse,
  curve: DoseResponseCurveResponse | null,
): ActivityValue | null {
  if (m.value_qualifier === "nd" || m.value_qualifier === "excluded") {
    return null;
  }

  if (curve && m.source_curve_id === curve.id) {
    return {
      value: m.value ?? null,
      qualifier: m.value_qualifier,
      unit: m.unit,
      source: "dose_response",
      curve_type: curve.curve_type,
      r_squared: curve.r_squared,
      data_point_count: curve.num_points,
      raw_data: (curve.raw_data as Array<{ x: number; y: number }> | null) ?? null,
      curve_params: {
        hill_slope: curve.hill_slope,
        top: curve.top,
        bottom: curve.bottom,
        num_points: curve.num_points,
        curve_class: curve.curve_class ?? null,
        confidence_interval_low: curve.confidence_interval_low ?? null,
        confidence_interval_high: curve.confidence_interval_high ?? null,
        fit_quality_warnings: curve.fit_quality_warnings ?? null,
      },
    };
  }

  return {
    value: m.value ?? null,
    qualifier: m.value_qualifier,
    unit: m.unit,
    source: "readout",
    curve_type: null,
    r_squared: null,
    data_point_count: m.replicate_count ?? 1,
    raw_data: null,
    curve_params: null,
  };
}
