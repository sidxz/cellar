/** Number of points used to draw a fitted 4PL sigmoid curve. */
export const CURVE_FIT_POINTS = 100;

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
