"use client";

import { CHART_AXIS, CHART_COLORS } from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";
import type { ShiftRow } from "../lib/melt-results";

// Same hues as the grid's ΔTm tint: blue up, red down, grey inside the band.
const UP = "#3b82f6";
const DOWN = "#ef4444";
const GRID = "rgba(113,113,122,0.2)";

export function ShiftPlot({
  rows,
  threshold,
  selected,
  onSelect,
}: {
  rows: readonly ShiftRow[];
  threshold: number;
  selected: ReadonlySet<string>;
  onSelect: (wellId: string) => void;
}) {
  const colour = (d: number) =>
    d >= threshold ? UP : d <= -threshold ? DOWN : CHART_COLORS.neutral;
  const longest = Math.max(0, ...rows.map((r) => r.label.length));
  const left = Math.min(180, 40 + longest * 7);
  const note = {
    xref: "x" as const,
    yref: "paper" as const,
    y: 1,
    yanchor: "bottom" as const,
    showarrow: false,
    font: { size: 11, color: CHART_AXIS.tick },
  };
  return (
    <Plot
      data={[
        {
          type: "scatter",
          mode: "markers",
          orientation: "h",
          x: rows.map((r) => r.deltaTm),
          y: rows.map((r) => r.label),
          customdata: rows.map((r) => r.wellId),
          marker: {
            color: rows.map((r) => colour(r.deltaTm)),
            size: rows.map((r) => (selected.has(r.wellId) ? 11 : 8)),
            line: {
              width: rows.map((r) => (selected.has(r.wellId) ? 2 : 0)),
              color: "#111827",
            },
          },
          hovertemplate: "%{y}: %{x:.1f} °C<extra></extra>",
        },
      ]}
      layout={{
        autosize: true,
        height: Math.max(240, 22 * rows.length + 60),
        margin: { t: 28, b: 40, l: left, r: 16 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: CHART_AXIS.tick },
        xaxis: { title: { text: "ΔTm (°C)" }, gridcolor: GRID, zeroline: false },
        yaxis: {
          type: "category",
          categoryorder: "array",
          categoryarray: rows.map((r) => r.label),
          gridcolor: GRID,
          automargin: true,
        },
        shapes: [
          {
            type: "rect",
            xref: "x",
            yref: "paper",
            x0: -threshold,
            x1: threshold,
            y0: 0,
            y1: 1,
            fillcolor: CHART_COLORS.neutral,
            opacity: 0.12,
            line: { width: 0 },
            layer: "below",
          },
          {
            type: "line",
            xref: "x",
            yref: "paper",
            x0: 0,
            x1: 0,
            y0: 0,
            y1: 1,
            line: { color: CHART_AXIS.tick, width: 1 },
          },
        ],
        annotations: [
          { ...note, x: -threshold, xanchor: "right", text: `within ±${threshold} °C` },
          { ...note, x: 0, xanchor: "left", text: "protein alone" },
        ],
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
      onClick={(event) => {
        const id = (event as { points: { customdata?: unknown }[] }).points[0]?.customdata;
        if (typeof id === "string") onSelect(id);
      }}
    />
  );
}
