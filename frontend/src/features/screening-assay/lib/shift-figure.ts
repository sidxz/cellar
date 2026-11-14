import { CHART_AXIS, CHART_COLORS } from "@/shared/lib/chart-colors";
import type { Band } from "./melt-hits";

/** Shared look of the ΔTm figures (ranked shift plot, ΔTm by concentration). */

// Same hues as the grid's ΔTm tint: blue up, red down, grey for everything not a hit.
const UP = "#3b82f6";
const DOWN = "#ef4444";
export const GRID = "rgba(113,113,122,0.2)";

/** A hit is blue up or red down; everything else is neutral. */
export const shiftColour = (deltaTm: number, isHit: boolean) =>
  !isHit ? CHART_COLORS.neutral : deltaTm > 0 ? UP : deltaTm < 0 ? DOWN : CHART_COLORS.neutral;

/** The ring round a selected point: dark ink on the light surface, light on the dark. */
export const selectedOutline = (theme: string | undefined) =>
  theme === "light" ? "#111827" : "#f1f5f9";

const ZERO_LABEL = "ΔTm = 0 (reference)";

/** `−2`, `2`, `0.5`: a rule's bound as the figures label it (true minus). */
const fmt = (v: number) => `${v < 0 ? "−" : ""}${Math.abs(v)}`;

/** The run's hit rule drawn on a ΔTm axis (`"x"` or `"y"`; the other spans the
 *  paper): "outside" as a shaded band, a one-sided rule as a dashed line, no
 *  rule as nothing; the 0 line always. Labels sit at the low end of the
 *  concentration axis, where the lowest dose is. */
export function shiftBand(band: Band | null, axis: "x" | "y") {
  const x = axis === "x";
  const span = x
    ? { xref: "x" as const, yref: "paper" as const }
    : { xref: "paper" as const, yref: "y" as const };
  const at = (lo: number, hi: number) =>
    x ? { x0: lo, x1: hi, y0: 0, y1: 1 } : { x0: 0, x1: 1, y0: lo, y1: hi };
  const note = { showarrow: false, font: { size: 11, color: CHART_AXIS.tick } };
  // A label at a value on the ΔTm axis: above the plot (x), or at its left edge (y).
  const label = (value: number, text: string, side: "low" | "high") =>
    x
      ? {
          ...note,
          xref: "x" as const,
          yref: "paper" as const,
          y: 1,
          yanchor: "bottom" as const,
          x: value,
          xanchor: side === "low" ? ("right" as const) : ("left" as const),
          text,
        }
      : {
          ...note,
          xref: "paper" as const,
          yref: "y" as const,
          x: 0,
          xanchor: "left" as const,
          y: value,
          yanchor: side === "low" ? ("top" as const) : ("bottom" as const),
          text,
        };
  const zero = {
    type: "line" as const,
    ...span,
    ...at(0, 0),
    line: { color: CHART_AXIS.tick, width: 1 },
  };
  const zeroLabel = label(0, ZERO_LABEL, "high");
  if (band?.kind === "outside") {
    const rect = {
      type: "rect" as const,
      ...span,
      ...at(band.low, band.high),
      fillcolor: CHART_COLORS.neutral,
      opacity: 0.12,
      line: { width: 0 },
      layer: "below" as const,
    };
    const text = `outside ${fmt(band.low)} to ${fmt(band.high)} °C is a hit`;
    return { shapes: [rect, zero], annotations: [label(band.low, text, "low"), zeroLabel] };
  }
  if (band?.kind === "line") {
    const line = {
      type: "line" as const,
      ...span,
      ...at(band.at, band.at),
      line: { color: CHART_AXIS.tick, width: 1, dash: "dash" as const },
    };
    const text = `hit threshold ${fmt(band.at)} °C`;
    return { shapes: [line, zero], annotations: [label(band.at, text, "low"), zeroLabel] };
  }
  return { shapes: [zero], annotations: [zeroLabel] };
}
