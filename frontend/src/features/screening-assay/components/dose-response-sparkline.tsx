"use client";

import type { CurveClass, CurveParams } from "../types";

interface DoseResponseSparklineProps {
  params: CurveParams;
  curveClass?: CurveClass | null;
  width?: number;
  height?: number;
}

const CURVE_COLORS: Record<string, string> = {
  full: "#34d399", // emerald-400
  partial: "#fbbf24", // yellow-400
  bell_shaped: "#60a5fa", // blue-400
};
const DEFAULT_COLOR = "#71717a"; // zinc-500

/**
 * Pure SVG sparkline rendering a 4PL sigmoid dose-response curve.
 *
 * 4PL equation: y = bottom + (top - bottom) / (1 + (x / EC50)^hillSlope)
 *
 * Designed for AG Grid cell rendering — lightweight, no Plotly dependency.
 */
export function DoseResponseSparkline({
  params,
  curveClass,
  width = 120,
  height = 50,
}: DoseResponseSparklineProps) {
  const { hill_slope, top, bottom, fitted_value, r_squared } = params;
  const color = CURVE_COLORS[curveClass ?? ""] ?? DEFAULT_COLOR;
  const padding = 4;
  const drawW = width - 2 * padding;
  const drawH = height - 2 * padding;
  const N = 30;

  // Log-spaced x-values centered on fitted_value (EC50/IC50)
  const logMin = Math.log10(Math.max(fitted_value * 0.01, 1e-12));
  const logMax = Math.log10(fitted_value * 100);

  const yValues: number[] = [];
  for (let i = 0; i < N; i++) {
    const logX = logMin + ((logMax - logMin) * i) / (N - 1);
    const x = Math.pow(10, logX);
    const y =
      bottom + (top - bottom) / (1 + Math.pow(x / fitted_value, hill_slope));
    yValues.push(y);
  }

  // Normalize to SVG coordinate space
  const yMin = Math.min(...yValues, bottom, top);
  const yMax = Math.max(...yValues, bottom, top);
  const yRange = yMax - yMin || 1;

  const points = yValues
    .map((y, i) => {
      const sx = padding + (i / (N - 1)) * drawW;
      const sy = padding + (1 - (y - yMin) / yRange) * drawH;
      return `${sx.toFixed(1)},${sy.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="flex items-center gap-1.5">
      <svg width={width} height={height} className="shrink-0">
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="text-[10px] text-muted-foreground whitespace-nowrap">
        {r_squared.toFixed(2)}
      </span>
    </div>
  );
}
