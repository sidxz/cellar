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
