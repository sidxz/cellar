"use client";

/**
 * DoseResponseFigure — the canonical dose-response renderer.
 *
 * Every surface that draws a fitted curve goes through this component so
 * the same data always paints the same picture: protocol Activity tab,
 * run DR results, campaign grid sparkline, campaign click-to-expand dialog,
 * search results compact cell. Four size presets cover the common sizes;
 * each one shares the same trace-building logic and color tokens.
 *
 * The component is Plotly-based with `staticPlot` toggled by the
 * `interactive` prop, so a 220×140 sparkline costs the same as the
 * previous SVG version while a modal-sized expand renders fully
 * interactive zoom + hover. One source of truth for every surface.
 */

import { memo, useMemo } from "react";

import {
  CHART_AXIS,
  CHART_COLORS,
  CURVE_DEFAULT_COLOR,
  CURVE_QUALITY_COLORS,
} from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";

import { generate4PLPoints } from "../lib/dose-response-display";

// ─── Public types ───────────────────────────────────────────────────────────

/** Per-point shape carried in raw_data / excluded_points arrays. Optional
 *  metadata flags drive the marker styling (size + opacity). */
export interface CurvePoint {
  x: number;
  y: number;
  is_excluded?: boolean;
  is_outlier?: boolean;
  replicate_count?: number | null;
}

export interface CurveSnapshot {
  fitted_value: number;
  top: number;
  bottom: number;
  hill_slope: number;
  r_squared?: number | null;
  curve_class?: string | null;
  raw_data?: CurvePoint[] | null;
  excluded_points?: CurvePoint[] | null;
  /** Descriptive curve type ("ec50", "ic50", …). Post-033 it's not
   *  identity-bearing (readout_definition_id is); only used by the
   *  shared <DoseResponseChart> SummaryCard's legacy-fallback label. */
  curve_type?: string | null;
  /** Bounds of the primary intercept's CI strip in the chart's
   *  SummaryCard. Optional — pre-Hill-fit or aggregate snapshots omit. */
  confidence_interval_low?: number | null;
  confidence_interval_high?: number | null;
  /** Per-spec intercepts derived from the same Hill fit (EC50 + EC90 …).
   *  Drives the secondary chip strip and the headline label via
   *  `interceptLabel(spec)` when present. Legacy snapshots omit. */
  intercept_values?: Array<Record<string, unknown>> | null;
  /** Machine-readable fit-quality codes (`"ec50_at_bound"`, …). Rendered
   *  as amber badges in the SummaryCard. */
  fit_quality_warnings?: string[] | null;
}

export type FigureSize = "sparkline" | "cell" | "expand" | "full";

interface DoseResponseFigureProps {
  curve: CurveSnapshot | null | undefined;
  /** Unit appended to the x-axis title and IC50 readout. */
  unit?: string | null;
  /** Size preset — drives width / height / margins / font / axis chrome. */
  size?: FigureSize;
  /** When true, Plotly renders interactive (hover, zoom). Defaults vary
   *  by size: sparkline+cell static, expand+full interactive. */
  interactive?: boolean;
  /** Override the preset's width / height (full preset uses 100% width
   *  via the wrapper div — pass undefined for that). */
  width?: number;
  height?: number;
}

// ─── Size presets ───────────────────────────────────────────────────────────

interface Preset {
  width: number | "auto";
  height: number;
  margin: { l: number; r: number; t: number; b: number };
  tickFont: number;
  axisTitleFont: number;
  markerSize: number;
  excludedMarkerSize: number;
  curveWidth: number;
  showAxisTitles: boolean;
  showAxisTicks: boolean;
  defaultInteractive: boolean;
}

const PRESETS: Record<FigureSize, Preset> = {
  sparkline: {
    width: 220,
    height: 140,
    margin: { l: 28, r: 6, t: 6, b: 22 },
    tickFont: 8,
    axisTitleFont: 9,
    markerSize: 4,
    excludedMarkerSize: 5,
    curveWidth: 1.5,
    showAxisTitles: false,
    showAxisTicks: true,
    defaultInteractive: false,
  },
  cell: {
    width: 220,
    height: 160,
    margin: { l: 30, r: 8, t: 8, b: 26 },
    tickFont: 8,
    axisTitleFont: 9,
    markerSize: 4,
    excludedMarkerSize: 5,
    curveWidth: 1.5,
    showAxisTitles: false,
    showAxisTicks: true,
    defaultInteractive: false,
  },
  expand: {
    width: 720,
    height: 460,
    margin: { l: 60, r: 16, t: 20, b: 50 },
    tickFont: 12,
    axisTitleFont: 13,
    markerSize: 7,
    excludedMarkerSize: 9,
    curveWidth: 2,
    showAxisTitles: true,
    showAxisTicks: true,
    defaultInteractive: true,
  },
  full: {
    width: "auto",
    height: 360,
    margin: { l: 60, r: 16, t: 20, b: 50 },
    tickFont: 11,
    axisTitleFont: 12,
    markerSize: 6,
    excludedMarkerSize: 8,
    curveWidth: 2,
    showAxisTitles: true,
    showAxisTicks: true,
    defaultInteractive: true,
  },
};

// ─── Component ──────────────────────────────────────────────────────────────

function DoseResponseFigureInner({
  curve,
  unit,
  size = "cell",
  interactive,
  width,
  height,
}: DoseResponseFigureProps) {
  const preset = PRESETS[size];
  const isInteractive = interactive ?? preset.defaultInteractive;

  const figure = useMemo(() => {
    if (!curve || !Number.isFinite(curve.fitted_value) || curve.fitted_value <= 0) {
      return null;
    }
    return buildPlotInputs(curve, preset, unit ?? null);
  }, [curve, preset, unit]);

  const renderWidth = width ?? (preset.width === "auto" ? undefined : preset.width);
  const renderHeight = height ?? preset.height;

  if (!figure) {
    return (
      <div
        className="inline-flex items-center justify-center text-[10px] text-muted-foreground italic"
        style={{ width: renderWidth, height: renderHeight }}
      >
        {curve?.curve_class === "inactive" ? "inactive" : "no fit"}
      </div>
    );
  }

  return (
    <Plot
      data={figure.traces}
      layout={{
        ...figure.layout,
        width: renderWidth,
        height: renderHeight,
        autosize: preset.width === "auto",
      }}
      config={{
        staticPlot: !isInteractive,
        displayModeBar: false,
        responsive: preset.width === "auto",
      }}
      style={
        preset.width === "auto"
          ? { width: "100%", height: renderHeight }
          : { width: renderWidth, height: renderHeight }
      }
    />
  );
}

export const DoseResponseFigure = memo(DoseResponseFigureInner);

// ─── Trace + layout construction (the SHARED logic that was duplicated) ────

interface FigureInputs {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  traces: any[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layout: any;
}

function buildPlotInputs(
  curve: CurveSnapshot,
  preset: Preset,
  unit: string | null,
): FigureInputs {
  const color =
    CURVE_QUALITY_COLORS[curve.curve_class ?? ""] ?? CURVE_DEFAULT_COLOR;

  // Axis range: one decade past the data extremes; fall back to a
  // centred range around fitted_value when no raw points are present.
  const xRange = computeXRange(curve);

  // Partition raw points: kept (in-fit) vs flagged (excluded / outliers).
  // is_excluded and is_outlier behave the same visually — both render with
  // reduced opacity and a slightly larger marker so they're identifiable.
  const allPoints = curve.raw_data ?? [];
  const flagged: CurvePoint[] = [];
  const kept: CurvePoint[] = [];
  for (const pt of allPoints) {
    if (pt.is_excluded || pt.is_outlier) flagged.push(pt);
    else kept.push(pt);
  }
  // Some fitters emit the excluded list as a sibling array instead of an
  // is_excluded flag on the kept list — handle either shape.
  if (curve.excluded_points) {
    for (const pt of curve.excluded_points) flagged.push({ ...pt, is_excluded: true });
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [];

  if (kept.length > 0) {
    traces.push({
      x: kept.map((p) => p.x),
      y: kept.map((p) => p.y),
      mode: "markers",
      type: "scatter",
      marker: { color, size: preset.markerSize },
      name: "Data",
      hovertemplate: "x=%{x:.3g}<br>y=%{y:.2f}<extra></extra>",
    });
  }
  if (flagged.length > 0) {
    traces.push({
      x: flagged.map((p) => p.x),
      y: flagged.map((p) => p.y),
      mode: "markers",
      type: "scatter",
      marker: {
        color,
        size: preset.excludedMarkerSize,
        opacity: 0.4,
        symbol: "x-thin",
        line: { color, width: 1 },
      },
      name: "Excluded",
      hovertemplate: "x=%{x:.3g}<br>y=%{y:.2f} (excluded)<extra></extra>",
    });
  }

  // Fitted sigmoid via the canonical 4PL evaluator. Sampled across the
  // axis range so the curve fills the visible plot rather than tapering
  // off at the data extremes.
  const fitted = generate4PLPoints(
    {
      top: curve.top,
      bottom: curve.bottom,
      fitted_value: curve.fitted_value,
      hill_slope: curve.hill_slope,
    },
    xRange[0],
    xRange[1],
  );
  traces.push({
    x: fitted.x,
    y: fitted.y,
    mode: "lines",
    type: "scatter",
    line: { color, width: preset.curveWidth },
    name: "Fit",
    hoverinfo: "skip",
  });

  const layout = {
    margin: preset.margin,
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    showlegend: false,
    xaxis: {
      type: "log",
      range: [Math.log10(xRange[0]), Math.log10(xRange[1])],
      showgrid: true,
      gridcolor: "rgba(63,63,70,0.3)",
      tickfont: { size: preset.tickFont, color: CHART_AXIS.tick },
      zeroline: false,
      title: preset.showAxisTitles
        ? {
            text: `Concentration${unit ? ` (${unit})` : ""}`,
            font: { size: preset.axisTitleFont, color: CHART_AXIS.label },
          }
        : undefined,
    },
    yaxis: {
      showgrid: true,
      gridcolor: "rgba(63,63,70,0.3)",
      tickfont: { size: preset.tickFont, color: CHART_AXIS.tick },
      zeroline: false,
      title: preset.showAxisTitles
        ? {
            text: "Response",
            font: { size: preset.axisTitleFont, color: CHART_AXIS.label },
          }
        : undefined,
    },
    shapes: [
      // Vertical dashed line at the fitted IC50.
      {
        type: "line",
        xref: "x",
        x0: curve.fitted_value,
        x1: curve.fitted_value,
        yref: "paper",
        y0: 0,
        y1: 1,
        line: { color: CHART_COLORS.warning, width: 1, dash: "dot" },
        opacity: 0.7,
      },
    ],
  };

  return { traces, layout };
}

/** Visible x-axis range: pad one decade past the raw-data extremes (log
 *  scale). Falls back to ×0.01..×100 around fitted_value when no raw
 *  points are available. */
function computeXRange(curve: CurveSnapshot): [number, number] {
  const xs = (curve.raw_data ?? [])
    .map((p) => p.x)
    .filter((x): x is number => Number.isFinite(x) && x > 0);
  if (xs.length > 0) {
    const min = Math.min(...xs);
    const max = Math.max(...xs);
    return [Math.max(min * 0.1, 1e-12), max * 10];
  }
  const fv = curve.fitted_value;
  return [Math.max(fv * 0.01, 1e-12), fv * 100];
}
