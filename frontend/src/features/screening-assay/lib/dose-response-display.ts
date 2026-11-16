/**
 * Cellar-only dose-response display helpers.
 *
 * The 4PL evaluator, the axis ratios and the marker sizes now live in
 * `@structflo/components/dose-response` — shared so the chart, this app's
 * canvas export and the other apps' renderers can't disagree about what a
 * curve looks like. What stays here is the compact-renderer sugar only cellar
 * uses.
 */

import { X_AXIS_FLOOR, generate4PLPoints } from "@structflo/components/dose-response";

/** Compact dose-response chart dimensions used in cell renderers / detail sheets. */
export const COMPACT_DR_CHART = {
  WIDTH: 220,
  HEIGHT: 160,
  POINTS: 80,
  RANGE_EXTENSION: 0.5,
} as const;

/** Tighter X-axis preset for grid-cell thumbnails — fewer pixels means
 *  less room for the asymptote tails, so we shrink the visible decade
 *  extension on each side. */
export const COMPACT_4PL_OPTIONS = { numPoints: 80, rangeExtension: 0.3 } as const;

/** Smoother preset for the search compound-detail sheet. */
export const DETAIL_4PL_OPTIONS = { numPoints: 100, rangeExtension: 0.5 } as const;

/**
 * Convenience wrapper around ``generate4PLPoints`` for compact renderers
 * that only have raw data points (not pre-computed xMin/xMax).
 *
 * Returns empty arrays when inputs would produce non-finite results
 * (e.g. fitted_value === 0, hill_slope === 0, or fewer than 2 positive
 * x-values in rawData).
 */
export function generate4PLFromData(
  params: { top: number; bottom: number; fitted_value: number; hill_slope: number },
  rawData: Array<{ x: number; y: number }>,
  options?: { numPoints?: number; rangeExtension?: number },
): { x: number[]; y: number[] } {
  if (!Number.isFinite(params.fitted_value) || params.fitted_value === 0) {
    return { x: [], y: [] };
  }
  if (!Number.isFinite(params.hill_slope) || params.hill_slope === 0) {
    return { x: [], y: [] };
  }

  const positiveXs = rawData.map((p) => p.x).filter((v) => v > 0);
  if (positiveXs.length < 2) return { x: [], y: [] };

  const ext = options?.rangeExtension ?? COMPACT_DR_CHART.RANGE_EXTENSION;
  const n = options?.numPoints ?? COMPACT_DR_CHART.POINTS;

  const xMin = Math.max(10 ** (Math.log10(Math.min(...positiveXs)) - ext), X_AXIS_FLOOR);
  const xMax = 10 ** (Math.log10(Math.max(...positiveXs)) + ext);

  const { x, y } = generate4PLPoints(params, xMin, xMax, n);
  return { x, y };
}

/** The backend's note of points left out of a fit for a dose <= 0 (no place on a log axis),
 *  suffixed with how many: `dose_zero_left_out:2`. */
const DOSE_ZERO_LEFT_OUT = "dose_zero_left_out:";

/** A fit-quality code worded for a chemist where cellar owns the wording; any other code
 *  passes through (the suite's summary card labels its own). */
export function fitNoteLabel(code: string): string {
  if (!code.startsWith(DOSE_ZERO_LEFT_OUT)) return code;
  const n = Number(code.slice(DOSE_ZERO_LEFT_OUT.length));
  return `${n} point${n === 1 ? "" : "s"} at dose 0 left out of the fit`;
}

/** The curve with its fit notes worded (the same object when there is nothing to word). */
export function withFitNotes<T extends { fit_quality_warnings?: readonly string[] | null }>(
  curve: T,
): T {
  const codes = curve.fit_quality_warnings;
  if (!codes?.some((c) => c.startsWith(DOSE_ZERO_LEFT_OUT))) return curve;
  return { ...curve, fit_quality_warnings: codes.map(fitNoteLabel) };
}
