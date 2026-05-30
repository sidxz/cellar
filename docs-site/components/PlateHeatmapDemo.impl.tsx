"use client";

import { useMemo, useState } from "react";

/** Supported microplate formats. */
export type PlateFormat = 96 | 384;

/** One well's value, addressed like "A1" or "P24". */
export interface WellValue {
  /** Well address, e.g. "A1". */
  well: string;
  /** Numeric readout used for the heatmap color. */
  value: number;
  /** Optional label shown on hover. */
  label?: string;
}

export interface PlateHeatmapDemoProps {
  /** Plate format. Defaults to 96. */
  format?: PlateFormat;
  /** Well values. When omitted, the widget generates a sample gradient. */
  wells?: WellValue[];
  /** Color scale name (Plotly/named ramp). Defaults to "viridis". */
  colorScale?: string;
  /** Show the row/column axis labels. Defaults to true. */
  showLabels?: boolean;
  /** Extra CSS class for the outer container. */
  className?: string;
}

// ─── Plate geometry (mirrors frontend plate-dimensions.ts) ───────────────────

const DIMENSIONS: Record<PlateFormat, { rows: number; cols: number }> = {
  96: { rows: 8, cols: 12 },
  384: { rows: 16, cols: 24 },
};

/** Cell size in px per format — 384 wells render smaller to fit. */
const CELL_SIZE_PX: Record<PlateFormat, number> = {
  96: 26,
  384: 15,
};

/** A1, …, Z1, then AA, AB, … for >26 rows (matches the app's rowLabel). */
function rowLabel(index: number): string {
  if (index < 26) return String.fromCharCode(65 + index);
  return (
    String.fromCharCode(65 + Math.floor(index / 26) - 1) +
    String.fromCharCode(65 + (index % 26))
  );
}

// ─── Color ramps ─────────────────────────────────────────────────────────────

type RGB = readonly [number, number, number];
type ColorStops = ReadonlyArray<readonly [number, RGB]>;

/** Named ramps. Keyed by lowercased name; "viridis" is the default and the
 *  contract's documented default. Plotly scale names are accepted; unknown
 *  names fall back to viridis. */
const COLOR_RAMPS: Record<string, ColorStops> = {
  viridis: [
    [0.0, [68, 1, 84]],
    [0.25, [59, 82, 139]],
    [0.5, [33, 145, 140]],
    [0.75, [94, 201, 98]],
    [1.0, [253, 231, 37]],
  ],
  cividis: [
    [0.0, [0, 32, 76]],
    [0.25, [60, 75, 113]],
    [0.5, [124, 123, 120]],
    [0.75, [183, 173, 110]],
    [1.0, [255, 234, 70]],
  ],
  magma: [
    [0.0, [0, 0, 4]],
    [0.25, [81, 18, 124]],
    [0.5, [183, 55, 121]],
    [0.75, [252, 137, 97]],
    [1.0, [252, 253, 191]],
  ],
  // Sequential warm ramp, mirroring the app's SEQUENTIAL_STOPS.
  reds: [
    [0.0, [254, 242, 242]],
    [0.25, [252, 165, 165]],
    [0.5, [239, 68, 68]],
    [0.75, [185, 28, 28]],
    [1.0, [69, 10, 10]],
  ],
  // Diverging blue→white→red, mirroring the app's DIVERGING_STOPS.
  rdbu: [
    [0.0, [30, 58, 138]],
    [0.25, [96, 165, 250]],
    [0.5, [248, 250, 252]],
    [0.75, [220, 38, 38]],
    [1.0, [20, 5, 5]],
  ],
};

function rampFor(name: string): ColorStops {
  return COLOR_RAMPS[name.toLowerCase()] ?? COLOR_RAMPS.viridis;
}

function interpolateRGB(a: RGB, b: RGB, t: number): string {
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgb(${r},${g},${bl})`;
}

function rampColor(t: number, stops: ColorStops): string {
  const tc = Math.max(0, Math.min(1, t));
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (tc >= t0 && tc <= t1) {
      const local = t1 === t0 ? 0 : (tc - t0) / (t1 - t0);
      return interpolateRGB(c0, c1, local);
    }
  }
  return interpolateRGB(stops[stops.length - 1][1], stops[stops.length - 1][1], 0);
}

// ─── Sample data ─────────────────────────────────────────────────────────────

/** A plausible plate-readout gradient: a radial signal with a touch of noise,
 *  so the heatmap looks like a real screening readout rather than a flat ramp.
 *  Deterministic (seeded) so SSR-free hydration stays stable across renders. */
function sampleWells(format: PlateFormat): WellValue[] {
  const { rows, cols } = DIMENSIONS[format];
  const cr = (rows - 1) / 2;
  const cc = (cols - 1) / 2;
  const maxD = Math.hypot(cr, cc);
  const out: WellValue[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const d = Math.hypot(r - cr, c - cc) / maxD;
      // Deterministic pseudo-noise from the cell index.
      const noise = (Math.sin((r * 31 + c * 17) * 1.37) + 1) / 2;
      const v = 100 * (1 - d) * 0.85 + noise * 12;
      out.push({
        well: `${rowLabel(r)}${c + 1}`,
        value: Math.round(v * 10) / 10,
        label: "% inhibition",
      });
    }
  }
  return out;
}

// ─── Component ───────────────────────────────────────────────────────────────

interface HoverState {
  well: WellValue;
  /** Anchor position within the SVG container, in px. */
  x: number;
  y: number;
}

/**
 * PlateHeatmapDemo — interactive 96/384-well microplate heatmap rendered as an
 * SVG. Hover any well to read its value; toggle between 96- and 384-well
 * formats. Mirrors the screening plate-readout heatmap pattern (value→color
 * interpolation over a named ramp).
 *
 * This widget is pure SVG + DOM; it does not use RDKit/Ketcher/Plotly, so it
 * adds no extra WASM copy. It is still client-only (mounted via next/dynamic
 * with ssr:false) per the widgets contract.
 */
export function PlateHeatmapDemoImpl({
  format: initialFormat = 96,
  wells,
  colorScale = "viridis",
  showLabels = true,
  className,
}: PlateHeatmapDemoProps) {
  // When wells are provided, the size toggle is hidden — the data is tied to a
  // single format. Without data we generate per-format sample gradients.
  const controlled = Array.isArray(wells);
  const [format, setFormat] = useState<PlateFormat>(initialFormat);
  const [hover, setHover] = useState<HoverState | null>(null);

  const effectiveFormat = controlled ? initialFormat : format;
  const { rows, cols } = DIMENSIONS[effectiveFormat];
  const cell = CELL_SIZE_PX[effectiveFormat];
  const gap = effectiveFormat === 384 ? 1 : 2;
  const labelGutter = showLabels ? (effectiveFormat === 384 ? 16 : 22) : 0;

  const data = useMemo<WellValue[]>(
    () => (controlled ? wells! : sampleWells(format)),
    [controlled, wells, format],
  );

  const stops = useMemo(() => rampFor(colorScale), [colorScale]);

  const { byWell, min, max } = useMemo(() => {
    const m = new Map<string, WellValue>();
    let lo = Infinity;
    let hi = -Infinity;
    for (const w of data) {
      m.set(w.well, w);
      if (w.value < lo) lo = w.value;
      if (w.value > hi) hi = w.value;
    }
    if (!isFinite(lo)) {
      lo = 0;
      hi = 1;
    }
    return { byWell: m, min: lo, max: hi };
  }, [data]);

  const span = max - min;

  const svgW = labelGutter + cols * cell + (cols - 1) * gap;
  const svgH = labelGutter + rows * cell + (rows - 1) * gap;

  const cellX = (c: number) => labelGutter + c * (cell + gap);
  const cellY = (r: number) => labelGutter + r * (cell + gap);

  const muted = "color-mix(in srgb, currentColor 55%, transparent)";
  const emptyFill = "color-mix(in srgb, currentColor 8%, transparent)";

  return (
    <div
      className={className}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
        margin: "1rem 0",
      }}
    >
      {/* Toolbar: format toggle (only when generating sample data) + legend */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.75rem",
        }}
      >
        {!controlled ? (
          <div
            role="group"
            aria-label="Plate format"
            style={{
              display: "inline-flex",
              borderRadius: "0.5rem",
              border:
                "1px solid color-mix(in srgb, currentColor 22%, transparent)",
              overflow: "hidden",
              fontSize: "0.8125rem",
            }}
          >
            {([96, 384] as PlateFormat[]).map((f) => {
              const active = format === f;
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => {
                    setFormat(f);
                    setHover(null);
                  }}
                  aria-pressed={active}
                  style={{
                    padding: "0.3rem 0.7rem",
                    border: "none",
                    cursor: "pointer",
                    fontWeight: active ? 600 : 400,
                    background: active
                      ? "color-mix(in srgb, currentColor 14%, transparent)"
                      : "transparent",
                    color: "inherit",
                  }}
                >
                  {f}-well
                </button>
              );
            })}
          </div>
        ) : (
          <span style={{ fontSize: "0.8125rem", opacity: 0.7 }}>
            {effectiveFormat}-well plate
          </span>
        )}

        {/* Color-scale legend */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            fontSize: "0.7rem",
            color: muted,
          }}
        >
          <span style={{ fontVariantNumeric: "tabular-nums" }}>
            {min.toFixed(1)}
          </span>
          <span
            aria-hidden
            style={{
              display: "inline-block",
              width: 90,
              height: 10,
              borderRadius: 3,
              background: `linear-gradient(to right, ${stops
                .map(([t, [r, g, b]]) => `rgb(${r},${g},${b}) ${t * 100}%`)
                .join(", ")})`,
            }}
          />
          <span style={{ fontVariantNumeric: "tabular-nums" }}>
            {max.toFixed(1)}
          </span>
        </div>
      </div>

      {/* Plate */}
      <div style={{ position: "relative", overflow: "auto" }}>
        <svg
          role="img"
          aria-label={`${effectiveFormat}-well plate heatmap`}
          width={svgW}
          height={svgH}
          viewBox={`0 0 ${svgW} ${svgH}`}
          style={{ maxWidth: "100%", height: "auto", display: "block" }}
          onMouseLeave={() => setHover(null)}
        >
          {/* Column headers */}
          {showLabels &&
            Array.from({ length: cols }, (_, c) => (
              <text
                key={`col-${c}`}
                x={cellX(c) + cell / 2}
                y={labelGutter - 5}
                textAnchor="middle"
                fontSize={effectiveFormat === 384 ? 8 : 10}
                fill="currentColor"
                opacity={0.55}
              >
                {c + 1}
              </text>
            ))}

          {/* Row headers */}
          {showLabels &&
            Array.from({ length: rows }, (_, r) => (
              <text
                key={`row-${r}`}
                x={labelGutter - 5}
                y={cellY(r) + cell / 2}
                textAnchor="end"
                dominantBaseline="central"
                fontSize={effectiveFormat === 384 ? 8 : 10}
                fill="currentColor"
                opacity={0.55}
              >
                {rowLabel(r)}
              </text>
            ))}

          {/* Wells */}
          {Array.from({ length: rows }, (_, r) =>
            Array.from({ length: cols }, (_, c) => {
              const pos = `${rowLabel(r)}${c + 1}`;
              const w = byWell.get(pos);
              const t = w && span > 0 ? (w.value - min) / span : 0.5;
              const fill = w ? rampColor(t, stops) : emptyFill;
              const isHovered = hover?.well.well === pos;
              return (
                <rect
                  key={pos}
                  x={cellX(c)}
                  y={cellY(r)}
                  width={cell}
                  height={cell}
                  rx={effectiveFormat === 384 ? 1.5 : 3}
                  fill={fill}
                  stroke={isHovered ? "currentColor" : "none"}
                  strokeWidth={isHovered ? 1.5 : 0}
                  style={{ cursor: w ? "pointer" : "default" }}
                  onMouseEnter={() =>
                    w &&
                    setHover({
                      well: w,
                      x: cellX(c) + cell / 2,
                      y: cellY(r),
                    })
                  }
                  onFocus={() =>
                    w &&
                    setHover({
                      well: w,
                      x: cellX(c) + cell / 2,
                      y: cellY(r),
                    })
                  }
                  tabIndex={w ? 0 : -1}
                  aria-label={
                    w
                      ? `Well ${pos}: ${w.value}${
                          w.label ? ` ${w.label}` : ""
                        }`
                      : `Well ${pos}: empty`
                  }
                />
              );
            }),
          )}
        </svg>

        {/* Hover tooltip */}
        {hover && (
          <div
            role="status"
            style={{
              position: "absolute",
              left: hover.x,
              top: hover.y,
              transform: "translate(-50%, calc(-100% - 6px))",
              pointerEvents: "none",
              whiteSpace: "nowrap",
              padding: "0.3rem 0.5rem",
              borderRadius: "0.375rem",
              fontSize: "0.75rem",
              lineHeight: 1.3,
              background: "var(--tooltip-bg, #1f2937)",
              color: "var(--tooltip-fg, #f9fafb)",
              boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
              zIndex: 10,
            }}
          >
            <strong style={{ fontFamily: "ui-monospace, monospace" }}>
              {hover.well.well}
            </strong>
            {": "}
            <span style={{ fontVariantNumeric: "tabular-nums" }}>
              {hover.well.value}
            </span>
            {hover.well.label ? (
              <span style={{ opacity: 0.75 }}> {hover.well.label}</span>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
