"use client";

/**
 * DoseResponseSparkline — thin compatibility shim.
 *
 * Used to be a bespoke SVG renderer; the campaign grid, search results, and
 * protocol Activity tab each had their own slightly-different curve drawing
 * which is what a chemist flagged as inconsistent. Now everything goes
 * through the shared <DoseResponseFigure /> so identical inputs produce
 * identical pictures everywhere.
 *
 * Existing callers pass `params: CurveParams` + `dataPoints: [{x, y}]`;
 * we adapt that into a CurveSnapshot and delegate.
 */

import type { CurveClass, CurveParams } from "../types";
import {
  DoseResponseFigure,
  type AdditionalCurve,
  type AggregateMarker,
  type CurveSnapshot,
} from "./dose-response-figure";

interface DoseResponseSparklineProps {
  params: CurveParams;
  dataPoints?: Array<{ x: number; y: number }> | null;
  curveClass?: CurveClass | null;
  width?: number;
  height?: number;
  /** Optional aggregate-mode overlay — additional contributing curves
   *  drawn muted under the primary so the chemist sees per-run spread.
   *  Pass `CampaignMeasurement.curve_snapshot.additional_curves`. */
  additionalCurves?: AdditionalCurve[] | null;
  /** Optional aggregate marker — vertical line at the cell's aggregated
   *  value. When present, per-curve intercept dashes are suppressed.
   *  Pass `CampaignMeasurement.curve_snapshot.aggregate`. */
  aggregate?: AggregateMarker | null;
}

export function DoseResponseSparkline({
  params,
  dataPoints,
  curveClass,
  width,
  height,
  additionalCurves,
  aggregate,
}: DoseResponseSparklineProps) {
  const curve: CurveSnapshot = {
    fitted_value: params.fitted_value,
    top: params.top,
    bottom: params.bottom,
    hill_slope: params.hill_slope,
    r_squared: params.r_squared,
    curve_class: curveClass ?? null,
    raw_data: dataPoints ?? null,
    additional_curves: additionalCurves ?? null,
    aggregate: aggregate ?? null,
  };

  return (
    <DoseResponseFigure
      curve={curve}
      size="sparkline"
      width={width}
      height={height}
    />
  );
}
