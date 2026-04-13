"use client";

import type { CurveClass, CurveParams } from "../types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface DoseResponseSparklineProps {
  params: CurveParams;
  dataPoints?: Array<{ x: number; y: number }> | null;
  curveClass?: CurveClass | null;
  width?: number;
  height?: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CURVE_COLORS: Record<string, string> = {
  full: "#34d399",
  partial: "#fbbf24",
  bell_shaped: "#60a5fa",
};
const DEFAULT_COLOR = "#71717a";
const AXIS_COLOR = "#3f3f46";
const TICK_COLOR = "#52525b";
const LABEL_COLOR = "#71717a";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatConc(v: number): string {
  if (v >= 1000) return `${(v / 1000).toFixed(0)}k`;
  if (v >= 1) return v.toPrecision(2);
  if (v >= 0.01) return v.toPrecision(1);
  return v.toExponential(0);
}

function logTicks(logMin: number, logMax: number): number[] {
  const ticks: number[] = [];
  const startDecade = Math.ceil(logMin);
  const endDecade = Math.floor(logMax);
  for (let d = startDecade; d <= endDecade; d++) {
    ticks.push(Math.pow(10, d));
  }
  if (ticks.length < 2) {
    ticks.length = 0;
    ticks.push(Math.pow(10, logMin));
    ticks.push(Math.pow(10, logMax));
  }
  if (ticks.length > 3) {
    const step = Math.ceil(ticks.length / 3);
    const filtered = ticks.filter((_, i) => i % step === 0);
    if (!filtered.includes(ticks[ticks.length - 1])) {
      filtered.push(ticks[ticks.length - 1]);
    }
    return filtered.slice(0, 3);
  }
  return ticks;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DoseResponseSparkline({
  params,
  dataPoints,
  curveClass,
  width = 140,
  height = 60,
}: DoseResponseSparklineProps) {
  const { hill_slope, top, bottom, fitted_value, r_squared } = params;
  const color = CURVE_COLORS[curveClass ?? ""] ?? DEFAULT_COLOR;

  const ml = 18;
  const mr = 4;
  const mt = 4;
  const mb = 14;
  const plotW = width - ml - mr;
  const plotH = height - mt - mb;

  const logMin = Math.log10(Math.max(fitted_value * 0.01, 1e-12));
  const logMax = Math.log10(fitted_value * 100);
  const logRange = logMax - logMin || 1;

  const yMin = Math.min(0, bottom, top);
  const yMax = Math.max(100, bottom, top);
  const yRange = yMax - yMin || 1;

  const toSvgX = (logVal: number) => ml + ((logVal - logMin) / logRange) * plotW;
  const toSvgY = (yVal: number) => mt + (1 - (yVal - yMin) / yRange) * plotH;

  const N = 30;
  const curvePoints: string[] = [];
  for (let i = 0; i < N; i++) {
    const logX = logMin + (logRange * i) / (N - 1);
    const x = Math.pow(10, logX);
    const y = bottom + (top - bottom) / (1 + Math.pow(x / fitted_value, hill_slope));
    curvePoints.push(`${toSvgX(logX).toFixed(1)},${toSvgY(y).toFixed(1)}`);
  }

  const xTicks = logTicks(logMin, logMax);
  const ic50SvgX = toSvgX(Math.log10(fitted_value));

  return (
    <div className="flex items-center gap-1">
      <svg width={width} height={height} className="shrink-0">
        {/* Axis frame */}
        <line x1={ml} y1={mt} x2={ml} y2={mt + plotH} stroke={AXIS_COLOR} strokeWidth={1} />
        <line x1={ml} y1={mt + plotH} x2={ml + plotW} y2={mt + plotH} stroke={AXIS_COLOR} strokeWidth={1} />

        {/* Y-axis labels */}
        <text x={ml - 2} y={toSvgY(0)} textAnchor="end" dominantBaseline="middle" fill={LABEL_COLOR} fontSize={7}>0</text>
        <text x={ml - 2} y={toSvgY(100)} textAnchor="end" dominantBaseline="middle" fill={LABEL_COLOR} fontSize={7}>100</text>

        {/* 50% gridline */}
        <line x1={ml} y1={toSvgY(50)} x2={ml + plotW} y2={toSvgY(50)} stroke={AXIS_COLOR} strokeWidth={0.5} strokeDasharray="2,2" opacity={0.5} />

        {/* X-axis ticks */}
        {xTicks.map((tickVal) => {
          const sx = toSvgX(Math.log10(tickVal));
          if (sx < ml || sx > ml + plotW) return null;
          return (
            <g key={tickVal}>
              <line x1={sx} y1={mt + plotH} x2={sx} y2={mt + plotH + 3} stroke={TICK_COLOR} strokeWidth={0.5} />
              <text x={sx} y={mt + plotH + 10} textAnchor="middle" fill={LABEL_COLOR} fontSize={6}>{formatConc(tickVal)}</text>
            </g>
          );
        })}

        {/* IC50 vertical dashed marker */}
        {ic50SvgX >= ml && ic50SvgX <= ml + plotW && (
          <line x1={ic50SvgX} y1={mt} x2={ic50SvgX} y2={mt + plotH} stroke={color} strokeWidth={0.75} strokeDasharray="2,2" opacity={0.6} />
        )}

        {/* Fitted sigmoid */}
        <polyline points={curvePoints.join(" ")} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />

        {/* Data points */}
        {dataPoints?.map((pt, i) => {
          const sx = toSvgX(Math.log10(Math.max(pt.x, 1e-12)));
          const sy = toSvgY(pt.y);
          if (sx < ml || sx > ml + plotW) return null;
          return <circle key={i} cx={sx} cy={sy} r={1.5} fill={color} opacity={0.7} />;
        })}
      </svg>
      <span className="text-[10px] text-muted-foreground whitespace-nowrap">
        {r_squared.toFixed(2)}
      </span>
    </div>
  );
}
