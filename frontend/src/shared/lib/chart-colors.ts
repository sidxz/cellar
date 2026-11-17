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

/* ── Measured curves (run Curves tab) ──────────────────────── */
/* Validated for colour-blind separation. `dark` is for the dark surface,
 * `light` for the light surface and for every exported (white) figure.
 * `selected` (the selected trace in Highlight mode) is the second series
 * step: orange separates from the violet reference where blue does not. */
const DARK_SERIES = [
  "#3987e5",
  "#d95926",
  "#199e70",
  "#c98500",
  "#d55181",
  "#008300",
  "#9085e9",
  "#e66767",
] as const;
const LIGHT_SERIES = [
  "#2a78d6",
  "#eb6834",
  "#1baf7a",
  "#eda100",
  "#e87ba4",
  "#008300",
  "#6250d6",
  "#e34948",
] as const;
export const MEASURED_CURVE_COLORS = {
  dark: {
    series: DARK_SERIES,
    neutral: "#8494ab",
    reference: "#9085e9",
    selected: DARK_SERIES[1],
    focus: "#3987e5",
  },
  light: {
    series: LIGHT_SERIES,
    neutral: "#7c8a9c",
    reference: "#6250d6",
    selected: LIGHT_SERIES[1],
    focus: "#2a78d6",
  },
} as const;

/* ── Plate well types ──────────────────────────────────────── */
/** Controls are coloured by effect, not by name: the full-effect (hit) control red, the
 * no-effect control blue — the ends of the platform's blue → red activity scale, never a
 * red/green pair. Which role is which depends on the protocol (`wellTypeColors`); this
 * default is cellar's default convention (positive control = no effect, % inhibition).
 * Samples stay neutral. */
export const FULL_EFFECT_COLOR = "#dc2626";
export const NO_EFFECT_COLOR = "#2563eb";
export const WELL_TYPE_COLORS: Record<string, string> = {
  sample: "#64748b",
  positive_control: NO_EFFECT_COLOR,
  negative_control: FULL_EFFECT_COLOR,
  blank: "#a3a3a3",
  reference: "#734595",
};

export type ControlRole = "positive_control" | "negative_control";

/** The control anchoring the full-effect end, as the backend normalizer puts it: the high
 * anchor (positive under "high", negative under "low") is 0 % for inhibition, % control and
 * z-score, and 100 % for activation. */
export function fullEffectControl(signal?: string | null, activation = false): ControlRole {
  const highIsPositive = signal !== "low";
  return highIsPositive === activation ? "positive_control" : "negative_control";
}

/** The full effect is the 100 % end: % activation, without % inhibition beside it. */
export function isActivation(normalizations: Iterable<string | null | undefined>): boolean {
  const ns = new Set(normalizations);
  return ns.has("percent_activation") && !ns.has("percent_inhibition");
}

/** Well-type colours with the two controls coloured by effect. */
export function wellTypeColors(signal?: string | null, activation = false): Record<string, string> {
  const full = fullEffectControl(signal, activation);
  const none = full === "positive_control" ? "negative_control" : "positive_control";
  return { ...WELL_TYPE_COLORS, [full]: FULL_EFFECT_COLOR, [none]: NO_EFFECT_COLOR };
}

/** A protocol's well-type colours: its signal, activation over all its readouts. */
export function protocolWellTypeColors(
  protocol?: {
    pos_control_signal?: string | null;
    readout_definitions?: ReadonlyArray<{ normalizations?: ReadonlyArray<string> | null }>;
  } | null,
): Record<string, string> {
  const normalizations = (protocol?.readout_definitions ?? []).flatMap(
    (d) => d.normalizations ?? [],
  );
  return wellTypeColors(protocol?.pos_control_signal, isActivation(normalizations));
}
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
