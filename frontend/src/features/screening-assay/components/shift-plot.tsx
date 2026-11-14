"use client";

import { CHART_AXIS } from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";
import { useTheme } from "next-themes";
import type { Band } from "../lib/melt-hits";
import type { ShiftRow } from "../lib/melt-results";
import { GRID, selectedOutline, shiftBand, shiftColour } from "../lib/shift-figure";

export function ShiftPlot({
  rows,
  hits,
  band,
  selected,
  onSelect,
}: {
  rows: readonly ShiftRow[];
  /** The positions the run's hit rule calls hits. */
  hits: ReadonlySet<string>;
  /** The rule on this window's ΔTm, drawn as a band or line; null draws none. */
  band: Band | null;
  selected: ReadonlySet<string>;
  onSelect: (wellId: string) => void;
}) {
  const { resolvedTheme } = useTheme();
  const longest = Math.max(0, ...rows.map((r) => r.label.length));
  const left = Math.min(180, 40 + longest * 7);
  const { shapes, annotations } = shiftBand(band, "x");
  const plot = (
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
            color: rows.map((r) => shiftColour(r.deltaTm, hits.has(r.wellId))),
            size: rows.map((r) => (selected.has(r.wellId) ? 11 : 8)),
            line: {
              width: rows.map((r) => (selected.has(r.wellId) ? 2 : 0)),
              color: selectedOutline(resolvedTheme),
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
  // Beyond 60 rows the panel scrolls; the figure keeps its full height inside.
  return rows.length > 60 ? <div style={{ maxHeight: 560, overflowY: "auto" }}>{plot}</div> : plot;
}
