"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { ComponentType, CSSProperties } from "react";

/**
 * Loose Plotly prop shape — mirrors the app's `shared/lib/plotly.tsx`.
 *
 * `@types/react-plotly.js` transitively needs `@types/plotly.js`, which is not
 * installed in the docs site (and we must not change package.json). Declaring
 * a loose local shape avoids the direct `plotly.js` type import while keeping
 * autocomplete on the well-typed wrapper props. Object-typed props accept any
 * plain object literal (Plotly trace/layout/config dicts).
 */
interface PlotProps {
  data: ReadonlyArray<Record<string, unknown>>;
  layout: Record<string, unknown>;
  config?: Record<string, unknown>;
  style?: CSSProperties;
  useResizeHandler?: boolean;
  className?: string;
}

// Plotly + react-plotly.js are browser-only (canvas/WebGL). Load lazily and
// disable SSR so the docs site builds and the first paint stays clean.
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <ChartSkeleton />,
}) as ComponentType<PlotProps>;

/** Four-parameter logistic (4PL) curve parameters. */
export interface FourPLParams {
  /** Bottom asymptote (% response at high concentration / low dose). */
  bottom: number;
  /** Top asymptote (% response at zero dose). */
  top: number;
  /** Inflection point: IC50 / EC50 in molar units. */
  ic50: number;
  /** Hill slope (steepness of the transition). */
  hillSlope: number;
}

export interface DoseResponseExplorerProps {
  /** Initial 4PL parameters. Sensible defaults applied when omitted. */
  initial?: Partial<FourPLParams>;
  /** Which parameters the reader may drag/edit. Defaults to ic50 + hillSlope. */
  adjustable?: (keyof FourPLParams)[];
  /** Concentration axis bounds in molar [min, max]. Defaults to [1e-10, 1e-4]. */
  concentrationRange?: [number, number];
  /** Show the readout for IC50/EC50 + Hill slope below the chart. Default true. */
  showReadout?: boolean;
  /** Chart height in pixels. Defaults to 320. */
  height?: number;
  /** Extra CSS class for the outer container. */
  className?: string;
}

const DEFAULT_PARAMS: FourPLParams = {
  bottom: 0,
  top: 100,
  ic50: 1e-7,
  hillSlope: 1,
};

const DEFAULT_ADJUSTABLE: (keyof FourPLParams)[] = ["ic50", "hillSlope"];
const DEFAULT_RANGE: [number, number] = [1e-10, 1e-4];

/** Number of points used to draw the sigmoid. Matches the app convention. */
const CURVE_POINTS = 120;

/**
 * Industry-standard 4PL (Prism / GraphPad convention), ported verbatim from
 * the app's `dose-response-display.ts#evaluate4PL`:
 *
 *     y = bottom + (top - bottom) / (1 + 10^((logEC50 - logX) * hill))
 *
 * `top`/`bottom` are the plateaus (direction-agnostic); `hillSlope` is signed
 * (positive = rising, negative = falling). The docs widget keeps this in
 * lock-step with the screening chart so readers learn the real model.
 */
function evaluate4PL(logX: number, p: FourPLParams): number {
  const logEc50 = Math.log10(p.ic50);
  return (
    p.bottom +
    (p.top - p.bottom) / (1 + Math.pow(10, (logEc50 - logX) * p.hillSlope))
  );
}

/** Evenly-spaced (in log-X) sigmoid points across [xMin, xMax]. */
function generateCurve(
  p: FourPLParams,
  xMin: number,
  xMax: number,
  n: number = CURVE_POINTS,
): { x: number[]; y: number[] } {
  const logMin = Math.log10(xMin);
  const logMax = Math.log10(xMax);
  const x: number[] = [];
  const y: number[] = [];
  for (let i = 0; i < n; i++) {
    const lx = logMin + ((logMax - logMin) * i) / (n - 1);
    x.push(Math.pow(10, lx));
    y.push(evaluate4PL(lx, p));
  }
  return { x, y };
}

/** Format a molar concentration into a friendly unit string (nM, µM, …). */
function formatMolar(m: number): string {
  if (!Number.isFinite(m) || m <= 0) return "—";
  const units: { factor: number; suffix: string }[] = [
    { factor: 1e-3, suffix: "mM" },
    { factor: 1e-6, suffix: "µM" },
    { factor: 1e-9, suffix: "nM" },
    { factor: 1e-12, suffix: "pM" },
  ];
  for (const u of units) {
    if (m >= u.factor) {
      const v = m / u.factor;
      return `${v >= 100 ? v.toFixed(0) : v.toFixed(v >= 10 ? 1 : 2)} ${u.suffix}`;
    }
  }
  return `${(m / 1e-12).toExponential(2)} pM`;
}

const SLIDER_META: Record<
  keyof FourPLParams,
  {
    label: string;
    /** Slider operates in this space; `toParam`/`fromParam` bridge to value. */
    min: number;
    max: number;
    step: number;
    /** Whether the slider is logarithmic (used for ic50). */
    log?: boolean;
    suffix?: string;
  }
> = {
  // ic50 slider works in log10(molar) space for a usable feel across decades.
  ic50: { label: "IC₅₀", min: -10, max: -4, step: 0.05, log: true },
  hillSlope: { label: "Hill slope", min: -4, max: 4, step: 0.05 },
  top: { label: "Top", min: 0, max: 120, step: 1, suffix: "%" },
  bottom: { label: "Bottom", min: -20, max: 100, step: 1, suffix: "%" },
};

function ChartSkeleton({ height = 320 }: { height?: number }) {
  return (
    <div
      role="status"
      aria-label="Loading chart"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height,
        borderRadius: "0.5rem",
        border: "1px solid color-mix(in srgb, currentColor 18%, transparent)",
        background: "color-mix(in srgb, currentColor 4%, transparent)",
        fontSize: "0.8125rem",
        color: "color-mix(in srgb, currentColor 60%, transparent)",
      }}
    >
      Loading curve…
    </div>
  );
}

function ParamSlider({
  paramKey,
  params,
  onChange,
}: {
  paramKey: keyof FourPLParams;
  params: FourPLParams;
  onChange: (next: FourPLParams) => void;
}) {
  const meta = SLIDER_META[paramKey];
  const raw = params[paramKey];
  // For ic50 the slider works in log space; everything else is linear.
  const sliderValue = meta.log ? Math.log10(raw) : raw;

  const display = meta.log
    ? formatMolar(raw)
    : `${raw.toFixed(meta.step < 1 ? 2 : 0)}${meta.suffix ?? ""}`;

  return (
    <label
      style={{
        display: "grid",
        gridTemplateColumns: "5.5rem 1fr 5rem",
        alignItems: "center",
        gap: "0.6rem",
        fontSize: "0.8125rem",
      }}
    >
      <span style={{ fontWeight: 600, opacity: 0.85 }}>{meta.label}</span>
      <input
        type="range"
        min={meta.min}
        max={meta.max}
        step={meta.step}
        value={sliderValue}
        onChange={(e) => {
          const v = Number(e.target.value);
          const next = meta.log ? Math.pow(10, v) : v;
          onChange({ ...params, [paramKey]: next });
        }}
        style={{ width: "100%", accentColor: "#2563eb" }}
        aria-label={meta.label}
      />
      <span
        style={{
          textAlign: "right",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        }}
      >
        {display}
      </span>
    </label>
  );
}

/**
 * DoseResponseExplorer — drag IC50 / Hill slope (and optionally top/bottom) to
 * see a live four-parameter logistic curve, mirroring the screening
 * dose-response chart. The curve math is ported verbatim from the app so the
 * widget teaches the real model.
 *
 * Client-only: Plotly is browser-only and loaded via `next/dynamic` (ssr:
 * false). The curve itself is pure math and needs no WASM, so it renders
 * immediately with a graceful skeleton while Plotly hydrates.
 */
export function DoseResponseExplorerImpl({
  initial,
  adjustable = DEFAULT_ADJUSTABLE,
  concentrationRange = DEFAULT_RANGE,
  showReadout = true,
  height = 320,
  className,
}: DoseResponseExplorerProps) {
  const [params, setParams] = useState<FourPLParams>({
    ...DEFAULT_PARAMS,
    ...initial,
  });

  // Re-seed when the initial prop changes (MDX hot-reload / a new example).
  useEffect(() => {
    setParams({ ...DEFAULT_PARAMS, ...initial });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(initial)]);

  const [xMin, xMax] = concentrationRange;

  const curve = useMemo(
    () => generateCurve(params, xMin, xMax),
    [params, xMin, xMax],
  );

  const ic50Response = useMemo(
    () => evaluate4PL(Math.log10(params.ic50), params),
    [params],
  );

  const plotData = useMemo<Record<string, unknown>[]>(
    () => [
      {
        x: curve.x,
        y: curve.y,
        type: "scatter",
        mode: "lines",
        line: { color: "#2563eb", width: 3, shape: "spline" },
        hovertemplate: "%{x:.2e} M<br>%{y:.1f}%<extra></extra>",
        name: "4PL fit",
      },
      {
        x: [params.ic50],
        y: [ic50Response],
        type: "scatter",
        mode: "markers",
        marker: { color: "#dc2626", size: 11, symbol: "circle" },
        hovertemplate: `IC₅₀ = %{x:.2e} M<br>%{y:.1f}%<extra></extra>`,
        name: "IC₅₀",
      },
    ],
    [curve, params.ic50, ic50Response],
  );

  const layout = useMemo<Record<string, unknown>>(
    () => ({
      autosize: true,
      height,
      margin: { l: 56, r: 16, t: 12, b: 48 },
      showlegend: false,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { size: 12 },
      xaxis: {
        type: "log",
        title: { text: "Concentration (M)" },
        range: [Math.log10(xMin), Math.log10(xMax)],
        gridcolor: "rgba(128,128,128,0.18)",
        zeroline: false,
      },
      yaxis: {
        title: { text: "Response (%)" },
        gridcolor: "rgba(128,128,128,0.18)",
        zeroline: false,
      },
      // Vertical guide line at the IC50 (mirrors the app's curve markers).
      shapes: [
        {
          type: "line",
          x0: params.ic50,
          x1: params.ic50,
          y0: 0,
          y1: 1,
          xref: "x",
          yref: "paper",
          line: { color: "#dc2626", width: 1, dash: "dot" },
        },
      ],
    }),
    [height, xMin, xMax, params.ic50],
  );

  // Only render sliders for parameters declared adjustable.
  const sliders = useMemo(
    () =>
      (Object.keys(SLIDER_META) as (keyof FourPLParams)[]).filter((k) =>
        adjustable.includes(k),
      ),
    [adjustable],
  );

  return (
    <div
      className={className}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.85rem",
        margin: "1rem 0",
        padding: "0.85rem",
        borderRadius: "0.6rem",
        border: "1px solid color-mix(in srgb, currentColor 15%, transparent)",
        background: "color-mix(in srgb, currentColor 3%, transparent)",
      }}
    >
      <Plot
        data={plotData}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        useResizeHandler
        style={{ width: "100%", height }}
      />

      {sliders.length > 0 ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            maxWidth: 480,
          }}
        >
          {sliders.map((k) => (
            <ParamSlider
              key={k}
              paramKey={k}
              params={params}
              onChange={setParams}
            />
          ))}
        </div>
      ) : null}

      {showReadout ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.4rem 1.1rem",
            fontSize: "0.8125rem",
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
            opacity: 0.9,
          }}
          aria-live="polite"
        >
          <span>IC₅₀ = {formatMolar(params.ic50)}</span>
          <span>Hill = {params.hillSlope.toFixed(2)}</span>
          <span>Top = {params.top.toFixed(1)}%</span>
          <span>Bottom = {params.bottom.toFixed(1)}%</span>
        </div>
      ) : null}
    </div>
  );
}
