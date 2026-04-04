"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Badge } from "@/shared/components/ui/badge";
import { cn } from "@/shared/lib/utils";
import {
  type DoseResponseCurve,
  type CurveType,
  type CurveClass,
  CURVE_TYPE_LABELS,
  CURVE_CLASS_LABELS,
} from "../types";

// ─── Dynamic import — Plotly must NOT be SSR'd ─────────────────────────────

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <Skeleton className="h-[350px] w-full" />,
});

// ─── Types ────────────────────────────────────────────────────────────────────

interface DoseResponseChartProps {
  curves: DoseResponseCurve[];
  className?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Generate 100-point 4PL sigmoid on log scale between min/max concentration */
function generate4PLCurve(
  curve: DoseResponseCurve,
  xMin: number,
  xMax: number
): { x: number[]; y: number[] } {
  const { fitted_value, hill_slope, top, bottom } = curve;
  const logMin = Math.log10(xMin);
  const logMax = Math.log10(xMax);
  const xs: number[] = [];
  const ys: number[] = [];

  for (let i = 0; i <= 100; i++) {
    const logX = logMin + (logMax - logMin) * (i / 100);
    const x = Math.pow(10, logX);
    const y = bottom + (top - bottom) / (1 + Math.pow(x / fitted_value, hill_slope));
    xs.push(x);
    ys.push(y);
  }
  return { x: xs, y: ys };
}

/** Extract (concentration, response) pairs from raw_data / excluded_points */
function extractPoints(
  points: Array<Record<string, unknown>> | null
): { x: number[]; y: number[] } {
  if (!points || points.length === 0) return { x: [], y: [] };
  const xs: number[] = [];
  const ys: number[] = [];
  for (const pt of points) {
    const conc = pt["concentration"] ?? pt["x"];
    const resp = pt["response"] ?? pt["y"];
    if (typeof conc === "number" && typeof resp === "number") {
      xs.push(conc);
      ys.push(resp);
    }
  }
  return { x: xs, y: ys };
}

const TRACE_COLORS = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#a855f7",
  "#06b6d4",
  "#ec4899",
  "#84cc16",
];

// ─── Component ────────────────────────────────────────────────────────────────

export function DoseResponseChart({ curves, className }: DoseResponseChartProps) {
  if (curves.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-dashed p-12 text-sm text-muted-foreground">
        No dose-response curves available.
      </div>
    );
  }

  // Build Plotly traces
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [];

  for (let i = 0; i < curves.length; i++) {
    const curve = curves[i];
    const color = TRACE_COLORS[i % TRACE_COLORS.length];
    const group = `curve-${curve.id}`;
    const label = `${CURVE_TYPE_LABELS[curve.curve_type as CurveType] ?? curve.curve_type} (${curve.molecule_id.slice(0, 8)})`;

    // Collect all x values to determine range for curve
    const included = extractPoints(curve.raw_data);
    const excluded = extractPoints(curve.excluded_points);

    const allX = [...included.x, ...excluded.x, curve.fitted_value];
    const xMin = allX.length > 0 ? Math.min(...allX) * 0.1 : curve.fitted_value * 0.01;
    const xMax = allX.length > 0 ? Math.max(...allX) * 10 : curve.fitted_value * 100;

    // Included data points
    if (included.x.length > 0) {
      traces.push({
        type: "scatter",
        mode: "markers",
        name: label,
        legendgroup: group,
        x: included.x,
        y: included.y,
        marker: { color, size: 7, symbol: "circle" },
        showlegend: true,
      });
    }

    // Excluded data points
    if (excluded.x.length > 0) {
      traces.push({
        type: "scatter",
        mode: "markers",
        name: `${label} (excluded)`,
        legendgroup: group,
        x: excluded.x,
        y: excluded.y,
        marker: { color, size: 8, symbol: "x", opacity: 0.5 },
        showlegend: false,
      });
    }

    // Fitted 4PL sigmoid line
    const { x: lineX, y: lineY } = generate4PLCurve(curve, xMin, xMax);
    traces.push({
      type: "scatter",
      mode: "lines",
      name: `${label} fit`,
      legendgroup: group,
      x: lineX,
      y: lineY,
      line: { color, width: 2 },
      showlegend: included.x.length === 0, // show in legend only if no markers already showed
    });
  }

  const layout = {
    height: 350,
    autosize: true,
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#a1a1aa" }, // zinc-400
    xaxis: {
      title: { text: "Concentration" },
      type: "log" as const,
      gridcolor: "#27272a",
      zerolinecolor: "#27272a",
    },
    yaxis: {
      title: { text: "Response" },
      gridcolor: "#27272a",
      zerolinecolor: "#27272a",
    },
    legend: {
      orientation: "h" as const,
      y: -0.2,
      font: { color: "#a1a1aa" },
    },
    margin: { t: 20, b: 60, l: 60, r: 20 },
  };

  const config = {
    displayModeBar: false,
    responsive: true,
  };

  return (
    <div className={cn("space-y-4", className)}>
      <Plot
        data={traces}
        layout={layout}
        config={config}
        style={{ width: "100%" }}
        useResizeHandler
      />

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {curves.map((curve) => (
          <Card key={curve.id} className="py-4">
            <CardHeader className="pb-0">
              <CardTitle className="text-sm">
                {CURVE_TYPE_LABELS[curve.curve_type as CurveType] ?? curve.curve_type}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-2 space-y-1">
              <p className="text-sm font-mono">
                {curve.fitted_value} {curve.fitted_unit}
              </p>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>R² = {curve.r_squared.toFixed(3)}</span>
                {curve.curve_class && (
                  <Badge variant="outline" className="text-xs">
                    {CURVE_CLASS_LABELS[curve.curve_class as CurveClass] ?? curve.curve_class}
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
