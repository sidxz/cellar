import { CHART_AXIS, CHART_COLORS } from "@/shared/lib/chart-colors";
import { shiftDirection } from "./melt-results";

/** Shared look of the ΔTm figures (ranked shift plot, ΔTm by concentration). */

// Same hues as the grid's ΔTm tint: blue up, red down, grey inside the band.
const UP = "#3b82f6";
const DOWN = "#ef4444";
export const GRID = "rgba(113,113,122,0.2)";

export const shiftColour = (deltaTm: number, threshold: number) => {
  const d = shiftDirection(deltaTm, threshold);
  return d === "up" ? UP : d === "down" ? DOWN : CHART_COLORS.neutral;
};

/** The ring round a selected point: dark ink on the light surface, light on the dark. */
export const selectedOutline = (theme: string | undefined) =>
  theme === "light" ? "#111827" : "#f1f5f9";

const ZERO_LABEL = "ΔTm = 0 (reference)";

/** The ±threshold band and the 0 line, with their labels. The ΔTm axis is x
 *  (`"x"`) or y (`"y"`); the other axis spans the paper. */
export function shiftBand(threshold: number, axis: "x" | "y") {
  const x = axis === "x";
  const span = x
    ? { xref: "x" as const, yref: "paper" as const }
    : { xref: "paper" as const, yref: "y" as const };
  const at = (lo: number, hi: number) =>
    x ? { x0: lo, x1: hi, y0: 0, y1: 1 } : { x0: 0, x1: 1, y0: lo, y1: hi };
  const shapes = [
    {
      type: "rect" as const,
      ...span,
      ...at(-threshold, threshold),
      fillcolor: CHART_COLORS.neutral,
      opacity: 0.12,
      line: { width: 0 },
      layer: "below" as const,
    },
    {
      type: "line" as const,
      ...span,
      ...at(0, 0),
      line: { color: CHART_AXIS.tick, width: 1 },
    },
  ];
  const note = { showarrow: false, font: { size: 11, color: CHART_AXIS.tick } };
  const annotations = x
    ? [
        {
          ...note,
          xref: "x" as const,
          yref: "paper" as const,
          y: 1,
          yanchor: "bottom" as const,
          x: -threshold,
          xanchor: "right" as const,
          text: `within ±${threshold} °C`,
        },
        {
          ...note,
          xref: "x" as const,
          yref: "paper" as const,
          y: 1,
          yanchor: "bottom" as const,
          x: 0,
          xanchor: "left" as const,
          text: ZERO_LABEL,
        },
      ]
    : // At the left end, where the lowest dose sits; the highest dose (most
      // likely to sit on the line) is at the right.
      [
        {
          ...note,
          xref: "paper" as const,
          yref: "y" as const,
          x: 0,
          xanchor: "left" as const,
          y: -threshold,
          yanchor: "top" as const,
          text: `within ±${threshold} °C`,
        },
        {
          ...note,
          xref: "paper" as const,
          yref: "y" as const,
          x: 0,
          xanchor: "left" as const,
          y: 0,
          yanchor: "bottom" as const,
          text: ZERO_LABEL,
        },
      ];
  return { shapes, annotations };
}
