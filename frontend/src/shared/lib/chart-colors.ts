/**
 * Centralized chart/visualization colors aligned with the VF design system.
 * Used by Plotly, Canvas, and SVG-based components.
 */

/* ── Core semantic ─────────────────────────────────────────── */
export const CHART_COLORS = {
  primary: "#3b6fb6",
  primaryLight: "#6b94cc",
  success: "#18974c",
  warning: "#f49e17",
  error: "#d41645",
  purple: "#734595",
  neutral: "#707372",
} as const;

/* ── Axis / grid / ticks (dark-mode optimized) ─────────────── */
export const CHART_AXIS = {
  grid: "#1e293b",
  tick: "#64748b",
  label: "#94a3b8",
  border: "#334155",
} as const;

/* ── Canvas export colors (light background) ───────────────── */
export const CHART_CANVAS = {
  background: "#ffffff",
  grid: "#c0c4c3",
  gridLight: "#e2e5e4",
  label: "#707372",
} as const;

/* ── Dose-response curve quality ───────────────────────────── */
export const CURVE_QUALITY_COLORS: Record<string, string> = {
  full: "#18974c",
  partial: "#f49e17",
  bell_shaped: "#3b6fb6",
};
export const CURVE_DEFAULT_COLOR = "#707372";

/* ── Plate well types ──────────────────────────────────────── */
export const WELL_TYPE_COLORS: Record<string, string> = {
  sample: "#3b6fb6",
  positive_control: "#18974c",
  negative_control: "#d41645",
  blank: "#707372",
  reference: "#734595",
};
export const WELL_EMPTY_COLOR = "#1e293b";

/* ── Compound group rotation palette (12 distinct) ─────────── */
export const GROUP_PALETTE = [
  "#3b6fb6",
  "#18974c",
  "#f49e17",
  "#d41645",
  "#734595",
  "#0891b2",
  "#db2777",
  "#65a30d",
  "#ea580c",
  "#0d9488",
  "#7c3aed",
  "#c026d3",
] as const;
