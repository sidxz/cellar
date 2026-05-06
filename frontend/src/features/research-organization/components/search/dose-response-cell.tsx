"use client";

import { memo } from "react";
import dynamic from "next/dynamic";
import type { ActivityValue } from "../../types";
import { generate4PLPoints, COMPACT_4PL, COMPACT_DR_CHART_SIZE } from "../../lib/curve-math";
import { CHART_COLORS, CHART_AXIS } from "@/shared/lib/chart-colors";

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
      marker: { color: CHART_COLORS.purple, size: 4 },
      hoverinfo: "skip",
    },
  ];

  // Add fitted curve if curve_params available
  if (value.curve_params && value.value != null) {
    const fitted = generate4PLPoints(
      value.raw_data!,
      value.value,
      value.curve_params.hill_slope,
      value.curve_params.top,
      value.curve_params.bottom,
      COMPACT_4PL,
    );
    if (fitted.x.length > 0) {
      traces.push({
        x: fitted.x,
        y: fitted.y,
        mode: "lines",
        type: "scatter",
        line: { color: CHART_COLORS.primaryLight, width: 1.5 },
        hoverinfo: "skip",
      });
    }
  }

  return (
    <Plot
      data={traces}
      layout={{
        width: COMPACT_DR_CHART_SIZE.width,
        height: COMPACT_DR_CHART_SIZE.height,
        margin: { l: 30, r: 8, t: 8, b: 26 },
        xaxis: {
          type: "log",
          showgrid: true,
          gridcolor: "rgba(63,63,70,0.3)",
          tickfont: { size: 8, color: CHART_AXIS.tick },
          zeroline: false,
        },
        yaxis: {
          showgrid: true,
          gridcolor: "rgba(63,63,70,0.3)",
          tickfont: { size: 8, color: CHART_AXIS.tick },
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
      style={{ width: COMPACT_DR_CHART_SIZE.width, height: COMPACT_DR_CHART_SIZE.height }}
    />
  );
}

export const DoseResponseCell = memo(DoseResponseCellInner);
