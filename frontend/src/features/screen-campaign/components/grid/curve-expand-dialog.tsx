"use client";

/**
 * CurveExpandDialog — click-to-expand for the sparkline cell in the campaign
 * results grid. Renders a larger, interactive (read-only) Plotly chart with
 * the fitted sigmoid + data points + IC50 cross-hair, mirroring the
 * search-page DoseResponseCell pattern but at modal scale.
 *
 * Stays read-only: no refit, no constraint editing — that lives on the
 * protocol Activity tab. Chemists viewing a campaign just need to inspect.
 */

import { useMemo } from "react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Badge } from "@/shared/components/ui/badge";
import { Plot } from "@/shared/lib/plotly";
import {
  CHART_AXIS,
  CHART_COLORS,
  CURVE_DEFAULT_COLOR,
  CURVE_QUALITY_COLORS,
} from "@/shared/lib/chart-colors";
import {
  DETAIL_4PL_OPTIONS,
  generate4PLFromData,
} from "@/features/screening-assay/lib/dose-response-display";
import {
  CURVE_CLASS_LABELS,
  type CurveClass,
} from "@/features/screening-assay/types";

export interface ExpandedCurve {
  fitted_value: number;
  top: number;
  bottom: number;
  hill_slope: number;
  r_squared: number;
  curve_class: CurveClass | null;
  raw_data: Array<{ x: number; y: number }> | null;
  unit?: string | null;
  /** Header context — molecule registration number and channel label. */
  moleculeLabel: string;
  channelLabel: string;
}

const CHART_WIDTH = 720;
const CHART_HEIGHT = 460;

interface Props {
  data: ExpandedCurve | null;
  onOpenChange: (open: boolean) => void;
}

export function CurveExpandDialog({ data, onOpenChange }: Props) {
  const traces = useMemo(() => {
    if (!data) return null;
    const rawData = data.raw_data ?? [];
    if (rawData.length === 0) return [];

    const color =
      CURVE_QUALITY_COLORS[data.curve_class ?? ""] ?? CURVE_DEFAULT_COLOR;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const out: any[] = [
      {
        x: rawData.map((p) => p.x),
        y: rawData.map((p) => p.y),
        mode: "markers",
        type: "scatter",
        marker: { color, size: 7 },
        name: "Data",
        hovertemplate: "x=%{x:.3g}<br>y=%{y:.2f}<extra></extra>",
      },
    ];

    if (data.fitted_value && data.fitted_value > 0) {
      const params = {
        top: data.top,
        bottom: data.bottom,
        fitted_value: data.fitted_value,
        hill_slope: data.hill_slope,
      };
      const fitted = generate4PLFromData(params, rawData, DETAIL_4PL_OPTIONS);
      if (fitted.x.length > 0) {
        out.push({
          x: fitted.x,
          y: fitted.y,
          mode: "lines",
          type: "scatter",
          line: { color, width: 2 },
          name: "Fit",
          hoverinfo: "skip",
        });
      }
    }
    return out;
  }, [data]);

  if (!data) return null;

  const color =
    CURVE_QUALITY_COLORS[data.curve_class ?? ""] ?? CURVE_DEFAULT_COLOR;
  const showIc50 = Number.isFinite(data.fitted_value) && data.fitted_value > 0;
  const classLabel = data.curve_class
    ? (CURVE_CLASS_LABELS as Record<string, string>)[data.curve_class] ??
      data.curve_class
    : null;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span>{data.moleculeLabel}</span>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground font-normal">
              {data.channelLabel}
            </span>
            {classLabel && (
              <Badge
                variant="outline"
                className="ml-1"
                style={{ borderColor: color, color }}
              >
                {classLabel}
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="flex items-baseline gap-4 text-sm font-mono">
          {showIc50 && (
            <span>
              <span className="text-muted-foreground">IC50</span>{" "}
              {data.fitted_value.toPrecision(4)}
              {data.unit ? ` ${data.unit}` : ""}
            </span>
          )}
          <span>
            <span className="text-muted-foreground">R²</span>{" "}
            {data.r_squared.toFixed(3)}
          </span>
          <span>
            <span className="text-muted-foreground">Hill</span>{" "}
            {data.hill_slope.toFixed(2)}
          </span>
          <span>
            <span className="text-muted-foreground">Top/Bot</span>{" "}
            {data.top.toFixed(1)} / {data.bottom.toFixed(1)}
          </span>
        </div>

        <div className="flex justify-center pt-2">
          {traces && traces.length > 0 ? (
            <Plot
              data={traces}
              layout={{
                width: CHART_WIDTH,
                height: CHART_HEIGHT,
                margin: { l: 60, r: 16, t: 20, b: 50 },
                xaxis: {
                  type: "log",
                  title: { text: "Concentration" + (data.unit ? ` (${data.unit})` : "") },
                  showgrid: true,
                  gridcolor: "rgba(63,63,70,0.3)",
                  tickfont: { color: CHART_AXIS.tick },
                  zeroline: false,
                },
                yaxis: {
                  title: { text: "Response (%)" },
                  showgrid: true,
                  gridcolor: "rgba(63,63,70,0.3)",
                  tickfont: { color: CHART_AXIS.tick },
                  zeroline: false,
                },
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                showlegend: false,
                shapes: showIc50
                  ? [
                      {
                        type: "line",
                        xref: "x",
                        x0: data.fitted_value,
                        x1: data.fitted_value,
                        yref: "paper",
                        y0: 0,
                        y1: 1,
                        line: { color: CHART_COLORS.warning, width: 1, dash: "dot" },
                        opacity: 0.7,
                      },
                    ]
                  : [],
                annotations: [],
              }}
              config={{
                displayModeBar: false,
                staticPlot: false,
              }}
            />
          ) : (
            <p className="py-8 text-sm text-muted-foreground italic">
              No raw data points available for this curve.
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
