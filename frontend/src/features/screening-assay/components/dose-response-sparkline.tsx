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
  type CurveSnapshot,
} from "./dose-response-figure";

interface DoseResponseSparklineProps {
  params: CurveParams;
  dataPoints?: Array<{ x: number; y: number }> | null;
  curveClass?: CurveClass | null;
  width?: number;
  height?: number;
}

export function DoseResponseSparkline({
  params,
  dataPoints,
  curveClass,
  width,
  height,
}: DoseResponseSparklineProps) {
  const curve: CurveSnapshot = {
    fitted_value: params.fitted_value,
    top: params.top,
    bottom: params.bottom,
    hill_slope: params.hill_slope,
    r_squared: params.r_squared,
    curve_class: curveClass ?? null,
    raw_data: dataPoints ?? null,
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
