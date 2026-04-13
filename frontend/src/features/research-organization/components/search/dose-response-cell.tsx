"use client";

import { memo } from "react";
import dynamic from "next/dynamic";
import type { ActivityValue } from "../../types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Plot = dynamic<any>(
  () => import("react-plotly.js").then((mod) => mod.default as any),
  { ssr: false }
) as React.ComponentType<{
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layout: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  config?: any;
  style?: React.CSSProperties;
}>;

interface DoseResponseCellProps {
  value?: ActivityValue;
}

/** Generate fitted 4PL sigmoid curve points on log scale */
function generate4PLPoints(
  ic50: number,
  hillSlope: number,
  top: number,
  bottom: number,
  xMin: number,
  xMax: number,
): { x: number[]; y: number[] } {
  const logMin = Math.log10(xMin);
  const logMax = Math.log10(xMax);
  const xs: number[] = [];
  const ys: number[] = [];

  for (let i = 0; i <= 80; i++) {
    const logX = logMin + (logMax - logMin) * (i / 80);
    const x = Math.pow(10, logX);
    const y = bottom + (top - bottom) / (1 + Math.pow(x / ic50, hillSlope));
    xs.push(x);
    ys.push(y);
  }
  return { x: xs, y: ys };
}

function DoseResponseCellInner({ value }: DoseResponseCellProps) {
  if (
    !value ||
    !value.raw_data ||
    value.raw_data.length === 0 ||
    value.source !== "dose_response"
  ) {
    return <span className="text-muted-foreground">&mdash;</span>;
  }

  const rawX = value.raw_data.map((pt) => pt.x);
  const rawY = value.raw_data.map((pt) => pt.y);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [
    {
      x: rawX,
      y: rawY,
      mode: "markers",
      type: "scatter",
      marker: { color: "#a78bfa", size: 4 },
      hoverinfo: "skip",
    },
  ];

  // Add fitted curve if curve_params available
  if (value.curve_params && value.value != null) {
    const xMin = Math.min(...rawX);
    const xMax = Math.max(...rawX);
    if (xMin > 0 && xMax > xMin) {
      const fitted = generate4PLPoints(
        value.value,
        value.curve_params.hill_slope,
        value.curve_params.top,
        value.curve_params.bottom,
        xMin * 0.5,
        xMax * 2,
      );
      traces.push({
        x: fitted.x,
        y: fitted.y,
        mode: "lines",
        type: "scatter",
        line: { color: "#60a5fa", width: 1.5 },
        hoverinfo: "skip",
      });
    }
  }

  return (
    <Plot
      data={traces}
      layout={{
        width: 220,
        height: 160,
        margin: { l: 30, r: 8, t: 8, b: 26 },
        xaxis: {
          type: "log",
          showgrid: true,
          gridcolor: "rgba(63,63,70,0.3)",
          tickfont: { size: 8, color: "#71717a" },
          zeroline: false,
        },
        yaxis: {
          showgrid: true,
          gridcolor: "rgba(63,63,70,0.3)",
          tickfont: { size: 8, color: "#71717a" },
          zeroline: false,
        },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        showlegend: false,
      }}
      config={{
        staticPlot: true,
        displayModeBar: false,
      }}
      style={{ width: 220, height: 160 }}
    />
  );
}

export const DoseResponseCell = memo(DoseResponseCellInner);
