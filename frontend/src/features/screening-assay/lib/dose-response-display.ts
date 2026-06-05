/** Number of points used to draw a fitted 4PL sigmoid curve. */
export const CURVE_FIT_POINTS = 100;

/** Industry-standard 4PL (Prism / GraphPad convention).
 *
 *     y = bottom + (top - bottom) / (1 + 10^((logEC50 - logX) * hill))
 *
 * ``top`` and ``bottom`` are the upper / lower plateaus of the Y axis,
 * direction-agnostic. ``hill`` is signed: positive for rising curves,
 * negative for falling. Must stay in lock-step with the backend fitter
 * in ``infrastructure/lmfit/curve_fitter.py``.
 */
export function evaluate4PL(
  logX: number,
  params: { top: number; bottom: number; fitted_value: number; hill_slope: number },
): number {
  const { top, bottom, fitted_value, hill_slope } = params;
  const logEc50 = Math.log10(fitted_value);
  return bottom + (top - bottom) / (1 + 10 ** ((logEc50 - logX) * hill_slope));
}

/** Generate ``n`` evenly-spaced (log-X) sigmoid points across [xMin, xMax].
 *  Returns parallel arrays so callers can format for Plotly, SVG polylines,
 *  or canvas paths without re-implementing the equation. */
export function generate4PLPoints(
  params: { top: number; bottom: number; fitted_value: number; hill_slope: number },
  xMin: number,
  xMax: number,
  n: number = CURVE_FIT_POINTS,
): { x: number[]; y: number[]; logX: number[] } {
  const logMin = Math.log10(xMin);
  const logMax = Math.log10(xMax);
  const x: number[] = [];
  const y: number[] = [];
  const logX: number[] = [];
  for (let i = 0; i < n; i++) {
    const lx = logMin + ((logMax - logMin) * i) / (n - 1);
    logX.push(lx);
    x.push(10 ** lx);
    y.push(evaluate4PL(lx, params));
  }
  return { x, y, logX };
}

/** Multiplier applied to the lowest data X to set the rendered axis floor. */
export const X_AXIS_MIN_RATIO = 0.1;

/** Multiplier applied to the highest data X to set the rendered axis ceiling. */
export const X_AXIS_MAX_RATIO = 10;

/** Fallback ratios when no data points are present (centered on fitted_value). */
export const X_AXIS_FALLBACK_MIN_RATIO = 0.01;
export const X_AXIS_FALLBACK_MAX_RATIO = 100;

/** Lower clamp on the rendered X axis to keep log10 stable. */
export const X_AXIS_FLOOR = 1e-12;

/** Marker styling for replicate / outlier points on the dose-response plot. */
export const PLOT_MARKER = {
  REPLICATE_SIZE: 5,
  REPLICATE_OPACITY: 0.35,
  EXCLUDED_SIZE: 8,
  MANUAL_EXCLUDED_OPACITY: 0.5,
  AUTO_EXCLUDED_OPACITY: 0.45,
  POINT_SIZE_INTERACTIVE: 9,
  POINT_SIZE_STATIC: 7,
} as const;

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
 * that only have raw data points (not pre-computed xMin/xMax). Mirrors the
 * old ``research-organization/lib/curve-math.ts::generate4PLPoints`` API
 * shape — but uses the canonical Prism-convention evaluator under the hood
 * so search-results curves match the protocol view.
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
