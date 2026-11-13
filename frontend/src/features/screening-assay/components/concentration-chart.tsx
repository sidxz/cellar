"use client";

import { CHART_AXIS, CHART_COLORS } from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";
import type { SeriesPoint } from "../lib/melt-results";
import { GRID, shiftBand, shiftColour } from "../lib/shift-figure";

/** ΔTm against dose for one batch: a dose-dependent shift rises, then plateaus. */
export function ConcentrationChart({
  title,
  points,
  doseUnit,
  threshold,
  selected,
  onSelect,
}: {
  title: string;
  points: readonly SeriesPoint[];
  doseUnit: string;
  threshold: number;
  selected: ReadonlySet<string>;
  onSelect: (wellId: string) => void;
}) {
  const byDose = new Map<number, number[]>();
  for (const p of points) byDose.set(p.dose, [...(byDose.get(p.dose) ?? []), p.deltaTm]);
  const doses = [...byDose.keys()].sort((a, b) => a - b);
  const mean = (d: number) => {
    const v = byDose.get(d) as number[];
    return v.reduce((a, b) => a + b, 0) / v.length;
  };
  const repeated = doses.filter((d) => (byDose.get(d) as number[]).length >= 2);
  const { shapes, annotations } = shiftBand(threshold, "y");
  return (
    <div>
      <p className="mb-1 text-sm font-medium">{title}</p>
      <Plot
        data={[
          {
            type: "scatter",
            mode: "markers",
            x: points.map((p) => p.dose),
            y: points.map((p) => p.deltaTm),
            customdata: points.map((p) => p.wellId),
            marker: {
              color: points.map((p) => shiftColour(p.deltaTm, threshold)),
              size: points.map((p) => (selected.has(p.wellId) ? 11 : 8)),
              line: {
                width: points.map((p) => (selected.has(p.wellId) ? 2 : 0)),
                color: "#111827",
              },
            },
            hovertemplate: `%{x} ${doseUnit}: %{y:.1f} °C<extra></extra>`,
          },
          {
            type: "scatter",
            mode: "lines",
            x: doses,
            y: doses.map(mean),
            line: { color: CHART_COLORS.neutral, width: 1 },
            hoverinfo: "skip",
          },
          {
            type: "scatter",
            mode: "markers",
            x: repeated,
            y: repeated.map(mean),
            marker: {
              symbol: "line-ew",
              size: 18,
              color: CHART_AXIS.tick,
              line: { width: 2, color: CHART_AXIS.tick },
            },
            hoverinfo: "skip",
          },
        ]}
        layout={{
          autosize: true,
          height: 260,
          margin: { t: 28, b: 48, l: 56, r: 16 },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { color: CHART_AXIS.tick },
          showlegend: false,
          xaxis: {
            type: "log",
            title: { text: `Concentration (${doseUnit})` },
            tickvals: doses,
            ticktext: doses.map(String),
            gridcolor: GRID,
          },
          yaxis: { title: { text: "ΔTm (°C)" }, gridcolor: GRID, zeroline: false },
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
    </div>
  );
}
