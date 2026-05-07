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
  return (
    bottom +
    (top - bottom) / (1 + Math.pow(10, (logEc50 - logX) * hill_slope))
  );
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
    x.push(Math.pow(10, lx));
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
