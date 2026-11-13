"use client";

import { CHART_AXIS } from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";
import type { ShiftRow } from "../lib/melt-results";
import { GRID, shiftBand, shiftColour } from "../lib/shift-figure";

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
  const longest = Math.max(0, ...rows.map((r) => r.label.length));
  const left = Math.min(180, 40 + longest * 7);
  const { shapes, annotations } = shiftBand(threshold, "x");
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
            color: rows.map((r) => shiftColour(r.deltaTm, threshold)),
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
        shapes,
        annotations,
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
