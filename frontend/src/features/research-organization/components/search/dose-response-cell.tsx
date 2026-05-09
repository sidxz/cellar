"use client";

import { memo } from "react";
import type { ActivityValue } from "../../types";
import {
  COMPACT_4PL_OPTIONS,
  COMPACT_DR_CHART,
  generate4PLFromData,
} from "@/features/screening-assay/lib/dose-response-display";
import {
  CHART_AXIS,
  CHART_COLORS,
  CURVE_DEFAULT_COLOR,
  CURVE_QUALITY_COLORS,
} from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";

interface DoseResponseCellProps {
  value?: ActivityValue;
}

const CELL_SIZE = {
  width: COMPACT_DR_CHART.WIDTH,
  height: COMPACT_DR_CHART.HEIGHT,
} as const;

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
  const curveClass = value.curve_params?.curve_class ?? null;
  const curveColor = CURVE_QUALITY_COLORS[curveClass ?? ""] ?? CURVE_DEFAULT_COLOR;
  const isExtrapolated = Boolean(
    value.curve_params?.fit_quality_warnings?.includes("ec50_at_bound"),
  );

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [
    {
      x: rawX,
      y: rawY,
      mode: "markers",
      type: "scatter",
      marker: { color: curveColor, size: 4 },
      hoverinfo: "skip",
    },
  ];

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const shapes: any[] = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const annotations: any[] = [];

  // Add fitted curve + IC50 cross-hair so the cell agrees visually with
  // the protocol view (same Prism convention, same marker semantics).
  if (value.curve_params && value.value != null) {
    const { hill_slope, top, bottom } = value.curve_params;
    const params = { top, bottom, fitted_value: value.value, hill_slope };
    const fitted = generate4PLFromData(params, value.raw_data, COMPACT_4PL_OPTIONS);
    if (fitted.x.length > 0) {
      traces.push({
        x: fitted.x,
        y: fitted.y,
        mode: "lines",
        type: "scatter",
        line: { color: curveColor, width: 1.5 },
        hoverinfo: "skip",
      });
    }

    const ec50 = value.value;
    const midY = (top + bottom) / 2;
    if (Number.isFinite(ec50) && ec50 > 0 && Number.isFinite(midY)) {
      // Vertical dashed line at the IC50 — chemist's anchor point. Matches
      // the protocol view's cross-hair, just thinner because of the cell size.
      shapes.push({
        type: "line",
        xref: "x",
        x0: ec50,
        x1: ec50,
        yref: "paper",
        y0: 0,
        y1: 1,
        line: { color: CHART_COLORS.warning, width: 1, dash: "dot" },
        opacity: 0.7,
      });
      // Small marker at (IC50, midpoint) to disambiguate the dotted line
      // from grid lines on dense screens.
      traces.push({
        type: "scatter",
        mode: "markers",
        x: [ec50],
        y: [midY],
        marker: {
          color: CHART_COLORS.warning,
          size: 5,
          line: { color: CHART_COLORS.error, width: 1 },
          symbol: "circle",
        },
        showlegend: false,
        hoverinfo: "skip",
      });
    }
  }

  if (isExtrapolated) {
    annotations.push({
      x: 0,
      y: 1,
      xref: "paper",
      yref: "paper",
      xanchor: "left",
      yanchor: "top",
      text: "extrapolated",
      showarrow: false,
      font: { size: 9, color: CHART_COLORS.warning },
      bgcolor: "rgba(0,0,0,0.0)",
    });
  }

  return (
    <Plot
      data={traces}
      layout={{
        width: CELL_SIZE.width,
        height: CELL_SIZE.height,
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
        shapes,
        annotations,
      }}
      config={{
        staticPlot: true,
        displayModeBar: false,
      }}
      style={{ width: CELL_SIZE.width, height: CELL_SIZE.height }}
    />
  );
}

export const DoseResponseCell = memo(DoseResponseCellInner);
