"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { WELL_TYPE_COLORS } from "@/shared/lib/chart-colors";
import { cn } from "@/shared/lib/utils";
import { Fragment, useMemo } from "react";
import { holderDimensions, plateCellSizePx, rowLabel } from "../lib/plate-dimensions";
import type { PlateData, PlateMapWell } from "../types";
import { OutlierFlagPopover } from "./outlier-flag-popover";

/** A position with no value (or no well): light grey, as the platform draws it — the
 *  scale's dark end means "beyond full effect". */
const NO_VALUE_COLOR = "#cbd5e1";

/** The platform's ✕ over a flagged well's colour, legible on any fill. */
function OutlierMark() {
  return (
    <svg
      role="img"
      aria-label="Outlier"
      viewBox="0 0 10 10"
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      <path d="M2 2L8 8M8 2L2 8" stroke="#0f172a" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M2 2L8 8M8 2L2 8" stroke="#fff" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

// ─── Color palettes ──────────────────────────────────────────────────────────

type ColorStops = ReadonlyArray<readonly [number, readonly [number, number, number]]>;

/** Diverging palette — signed scales (z-score, NEG/POS anchored).
 *  t=0 dark blue → 0.5 near-white → 1 near-black via red. */
const DIVERGING_STOPS: ColorStops = [
  [0.0, [30, 58, 138]], // blue-900
  [0.25, [96, 165, 250]], // blue-400
  [0.5, [248, 250, 252]], // slate-50
  [0.75, [220, 38, 38]], // red-600
  [1.0, [20, 5, 5]], // near-black
];

/** Sequential palette — unsigned magnitude (dose, raw counts).
 *  Pale → red → dark red. Reads as "low → high" without implying a
 *  meaningful midpoint. */
const SEQUENTIAL_STOPS: ColorStops = [
  [0.0, [254, 242, 242]], // red-50
  [0.25, [252, 165, 165]], // red-300
  [0.5, [239, 68, 68]], // red-500
  [0.75, [185, 28, 28]], // red-700
  [1.0, [69, 10, 10]], // red-950
];

export type Palette = "diverging" | "sequential";

function stopsFor(palette: Palette): ColorStops {
  return palette === "sequential" ? SEQUENTIAL_STOPS : DIVERGING_STOPS;
}

function interpolateRGB(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
  t: number,
): string {
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgb(${r},${g},${bl})`;
}

function paletteColor(t: number, palette: Palette): string {
  const stops = stopsFor(palette);
  const tc = Math.max(0, Math.min(1, t));
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (tc >= t0 && tc <= t1) {
      const local = (tc - t0) / (t1 - t0);
      return interpolateRGB(c0, c1, local);
    }
  }
  return interpolateRGB(stops[0][1], stops[0][1], 0);
}

export type ScaleKind = "linear" | "zscore";

export interface ValueScale {
  /** Value mapped to t=0.25 in diverging palettes (or t=0 in sequential).
   *  For z-score: mean − 2σ. For linear: scale min, or (anchored) the mirror of
   *  ``high`` around the no-effect level, which then sits at white (t=0.5). */
  low: number;
  /** Value mapped to t=0.75 in diverging palettes (or t=1 in sequential).
   *  For z-score: mean + 2σ. For linear: scale max, or (anchored) the full-effect
   *  level, red. */
  high: number;
  /** "linear" | "zscore" — drives legend labels. */
  kind: ScaleKind;
  /** For z-score legends: the underlying mean and σ so the legend can
   *  render σ tick marks. */
  zMean?: number;
  zStd?: number;
  /** Labels under the gradient at their own values, for scales anchored the
   *  platform's way ("0 %" at white, "100 %" at red). Replaces the end labels. */
  marks?: { value: number; text: string }[];
  /** Mean of negative-control wells on the plate, when present. Surfaced
   *  by the legend as a tick mark on the gradient even when the scale
   *  isn't anchored on controls — answers "where do controls land?"
   *  for the chemist at a glance. */
  negMean?: number;
  posMean?: number;
}

/** Map a value to a normalized [0,1] scale position.
 *
 *  Diverging palettes use a 0.25/0.75 anchor convention so outliers fall
 *  into the dark tails (t=0 / t=1) — `low` is mid-cool, `high` is mid-warm.
 *  Sequential palettes use the full 0..1 range — `low` is the palest,
 *  `high` is the darkest. */
function valueToT(v: number, scale: ValueScale, palette: Palette): number {
  const span = scale.high - scale.low;
  if (span === 0) return palette === "sequential" ? 0 : 0.5;
  const ratio = (v - scale.low) / span;
  if (palette === "sequential") {
    return Math.max(0, Math.min(1, ratio));
  }
  const t = 0.25 + ratio * 0.5;
  return Math.max(0, Math.min(1, t));
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

function WellTooltipContent({
  well,
  outlier,
  rawValue,
  computedValue,
  rawUnit,
  computedUnit,
  doseUnit,
}: {
  well: PlateMapWell;
  outlier: boolean;
  rawValue: number | undefined;
  computedValue: number | undefined;
  rawUnit: string | null;
  computedUnit: string;
  // Display-only label from PlateMapResponse.dose_unit (a backend string).
  doseUnit: string;
}) {
  const aliases: string[] = [];
  if (well.molecule_name && !aliases.includes(well.molecule_name)) {
    aliases.push(well.molecule_name);
  }
  for (const s of well.synonyms ?? []) {
    if (s && !aliases.includes(s)) aliases.push(s);
  }
  return (
    <div className="w-[210px] space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-xs font-medium">{well.position_label}</span>
        <span className="text-[10px] capitalize opacity-70">
          {well.well_type.replace(/_/g, " ")}
        </span>
      </div>
      {outlier && (
        <p className="text-[11px] font-medium">Outlier · left out of plate QC and anchors</p>
      )}
      {well.batch_number && <p className="font-mono text-[11px] truncate">{well.batch_number}</p>}
      {aliases.length > 0 && (
        <p className="text-[10px] italic opacity-70 line-clamp-2">{aliases.join(" · ")}</p>
      )}
      {well.dose != null && (
        <p className="text-[10px]">
          Dose: <span className="tabular-nums">{well.dose}</span> {doseUnit}
        </p>
      )}
      {rawValue != null && (
        <p className="text-[11px]">
          Raw: <span className="font-mono tabular-nums">{rawValue.toFixed(3)}</span>
          {rawUnit ? ` ${rawUnit}` : ""}
        </p>
      )}
      {computedValue != null && (
        <p className="text-[11px]">
          {computedUnit}: <span className="font-mono tabular-nums">{computedValue.toFixed(3)}</span>
        </p>
      )}
      {well.smiles && (
        <div className="flex items-center justify-center rounded-sm bg-white p-1">
          <StructureThumbnail smiles={well.smiles} size={140} />
        </div>
      )}
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

interface PlateValueHeatmapProps {
  plate: PlateData;
  /** well_id → value used for coloring. Wells absent from the map render
   *  empty (no fill). Control wells are usually omitted so they render as
   *  type-colored outlines, regardless of whether they have a raw value. */
  valueByWellId: Map<string, number>;
  /** Full per-well raw + computed values (for tooltip). Optional. */
  rawByWellId?: Map<string, number>;
  computedByWellId?: Map<string, number>;
  /** Color scale anchors. */
  scale: ValueScale;
  /** Color encoding to use. Sequential reads as low→high; diverging as
   *  below-baseline / above-baseline. */
  palette: Palette;
  /** Unit shown in the tooltip for the canonical fit value. */
  rawUnit: string | null;
  /** Label for the computed/normalized value (e.g. "% Inhibition"). */
  computedUnit: string;
  // Display-only label from PlateMapResponse.dose_unit (a backend string).
  doseUnit: string;
  /** Wells flagged as outliers: drawn with an ✕. */
  outlierWellIds?: ReadonlySet<string>;
  /** Well-type colours, the controls by effect (`wellTypeColors`). */
  colors?: Record<string, string>;
  /** Given when the user can flag: a well with a raw value opens the flag popover. */
  onFlag?: (well: PlateMapWell, outlier: boolean, reason: string | null) => void;
  flagPending?: boolean;
  className?: string;
}

const OUTLINED = new Set(["positive_control", "negative_control", "blank", "reference"]);

export function PlateValueHeatmap({
  plate,
  valueByWellId,
  rawByWellId,
  computedByWellId,
  scale,
  palette,
  rawUnit,
  computedUnit,
  doseUnit,
  outlierWellIds,
  colors = WELL_TYPE_COLORS,
  onFlag,
  flagPending = false,
  className,
}: PlateValueHeatmapProps) {
  const [rows, cols] = holderDimensions(plate);
  const size = plateCellSizePx(plate.format);

  const wellMap = useMemo(() => {
    const m = new Map<string, PlateMapWell>();
    for (const well of plate.wells) m.set(well.position, well);
    return m;
  }, [plate.wells]);

  const labelSize = size >= 28 ? "text-xs" : size >= 18 ? "text-[10px]" : "text-[8px]";

  function getWellStyle(well: PlateMapWell | undefined): {
    background: string;
    border?: string;
  } {
    if (!well) return { background: NO_VALUE_COLOR };

    const outline = OUTLINED.has(well.well_type) ? colors[well.well_type] : undefined;
    const isControl = !!outline && well.well_type !== "sample";
    const v = valueByWellId.get(well.well_id);

    // Controls without a gradient value render as type-color outlines so
    // their position on the plate is still legible. Controls *with* a
    // gradient value (the concentration view, where POS has a fixed dose
    // worth seeing) get filled and keep the outline as identity.
    if (isControl) {
      if (v == null) {
        return { background: "transparent", border: `2px solid ${outline}` };
      }
      return {
        background: paletteColor(valueToT(v, scale, palette), palette),
        border: `2px solid ${outline}`,
      };
    }

    if (v == null) return { background: NO_VALUE_COLOR };
    return { background: paletteColor(valueToT(v, scale, palette), palette) };
  }

  return (
    <div className={cn("space-y-3", className)}>
      <TooltipProvider delayDuration={120}>
        <div className="overflow-auto">
          <div
            className="inline-grid select-none"
            style={{
              gridTemplateColumns: `${size + 8}px repeat(${cols}, ${size}px)`,
              gridTemplateRows: `${size}px repeat(${rows}, ${size}px)`,
              gap: "1px",
            }}
          >
            {/* Top-left corner */}
            <div />

            {/* Column headers */}
            {Array.from({ length: cols }, (_, c) => (
              <div
                key={`col-${c}`}
                className={cn(
                  "flex items-center justify-center",
                  labelSize,
                  "text-muted-foreground font-medium",
                )}
              >
                {c + 1}
              </div>
            ))}

            {/* Rows */}
            {Array.from({ length: rows }, (_, r) => {
              const rLabel = rowLabel(r);
              return (
                <Fragment key={`row-${r}`}>
                  <div
                    className={cn(
                      "flex items-center justify-center",
                      labelSize,
                      "text-muted-foreground font-medium",
                    )}
                  >
                    {rLabel}
                  </div>

                  {Array.from({ length: cols }, (_, c) => {
                    const pos = `${rLabel}${c + 1}`;
                    const well = wellMap.get(pos);
                    const style = getWellStyle(well);
                    const outlier = !!well && !!outlierWellIds?.has(well.well_id);
                    const flaggable =
                      !!well && !!onFlag && (outlier || !!rawByWellId?.has(well.well_id));
                    const cellStyle = {
                      width: size,
                      height: size,
                      background: style.background,
                      border: style.border,
                      boxSizing: "border-box" as const,
                    };
                    const cell = flaggable ? (
                      <button
                        type="button"
                        data-position={pos}
                        aria-label={`${pos}${outlier ? ", outlier" : ""}`}
                        className="relative rounded-sm p-0 transition-opacity hover:opacity-75"
                        style={cellStyle}
                      >
                        {outlier && <OutlierMark />}
                      </button>
                    ) : (
                      <div
                        data-position={pos}
                        className="relative rounded-sm cursor-default transition-opacity hover:opacity-75"
                        style={cellStyle}
                      >
                        {outlier && <OutlierMark />}
                      </div>
                    );
                    if (!well) return <Fragment key={pos}>{cell}</Fragment>;
                    const trigger = <TooltipTrigger asChild>{cell}</TooltipTrigger>;
                    return (
                      <Tooltip key={pos}>
                        {flaggable && onFlag ? (
                          <OutlierFlagPopover
                            flagged={outlier}
                            title={`${well.position_label} · ${well.well_type.replace(/_/g, " ")}`}
                            pending={flagPending}
                            onSubmit={(reason) => onFlag(well, !outlier, reason)}
                          >
                            {trigger}
                          </OutlierFlagPopover>
                        ) : (
                          trigger
                        )}
                        <TooltipContent
                          side="top"
                          sideOffset={6}
                          collisionPadding={12}
                          className="bg-popover text-popover-foreground border shadow-lg p-2.5"
                        >
                          <WellTooltipContent
                            well={well}
                            outlier={outlier}
                            rawValue={rawByWellId?.get(well.well_id)}
                            computedValue={computedByWellId?.get(well.well_id)}
                            rawUnit={rawUnit}
                            computedUnit={computedUnit}
                            doseUnit={doseUnit}
                          />
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                </Fragment>
              );
            })}
          </div>
        </div>
      </TooltipProvider>
    </div>
  );
}

// ─── Color-scale legend ──────────────────────────────────────────────────────

interface ColorScaleLegendProps {
  scale: ValueScale;
  palette: Palette;
  unit: string | null;
  /** Which well types actually appear on this plate. Drives the swatch
   *  key beneath the gradient; types not present are omitted so the key
   *  doesn't advertise outlines the chemist will never see. */
  controlTypesPresent?: ReadonlyArray<
    "negative_control" | "positive_control" | "blank" | "reference"
  >;
  /** The plate has outlier-flagged wells: the key names the ✕. */
  hasOutliers?: boolean;
  /** Well-type colours, the controls by effect (`wellTypeColors`). */
  colors?: Record<string, string>;
  className?: string;
}

export function ColorScaleLegend({
  scale,
  palette,
  unit,
  controlTypesPresent,
  hasOutliers = false,
  colors = WELL_TYPE_COLORS,
  className,
}: ColorScaleLegendProps) {
  const stops = stopsFor(palette)
    .map(([t, [r, g, b]]) => `rgb(${r},${g},${b}) ${t * 100}%`)
    .join(", ");

  const u = unit ? ` ${unit}` : "";

  // Tick-mark positions on the gradient. Linear scales overlay NEG/POS
  // means when the panel computed them — even when the gradient isn't
  // anchored on controls, the chemist still wants to see where controls
  // landed.
  const ticks: { t: number; label: string; value: number; color: string }[] = [];
  if (scale.kind === "linear") {
    if (scale.negMean != null) {
      ticks.push({
        t: valueToT(scale.negMean, scale, palette),
        label: "NEG",
        value: scale.negMean,
        color: colors.negative_control,
      });
    }
    if (scale.posMean != null) {
      ticks.push({
        t: valueToT(scale.posMean, scale, palette),
        label: "POS",
        value: scale.posMean,
        color: colors.positive_control,
      });
    }
  }

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="relative h-3 w-full max-w-md">
        <div
          className="absolute inset-0 rounded-sm"
          style={{ background: `linear-gradient(to right, ${stops})` }}
        />
        {ticks.map((tk) => (
          <span
            key={tk.label}
            className="pointer-events-none absolute -top-0.5 -bottom-0.5 w-[2px] rounded-sm"
            style={{
              left: `calc(${tk.t * 100}% - 1px)`,
              background: tk.color,
              boxShadow: "0 0 0 1px rgba(255,255,255,0.7)",
            }}
            title={`${tk.label} ${tk.value.toFixed(2)}${u}`}
          />
        ))}
      </div>

      {scale.marks ? (
        <div className="relative h-3.5 max-w-md text-[10px] text-muted-foreground">
          {scale.marks.map((m) => (
            <span
              key={m.text}
              className="absolute -translate-x-1/2 whitespace-nowrap font-mono tabular-nums"
              style={{ left: `${valueToT(m.value, scale, palette) * 100}%` }}
            >
              {m.text}
            </span>
          ))}
        </div>
      ) : (
        <div className="flex max-w-md justify-between text-[10px] text-muted-foreground">
          {scale.kind === "zscore" ? (
            <>
              <span>
                −2σ <span className="font-mono tabular-nums">{scale.low.toFixed(2)}</span>
                {u}
              </span>
              {scale.zMean != null && (
                <span>
                  μ <span className="font-mono tabular-nums">{scale.zMean.toFixed(2)}</span>
                </span>
              )}
              <span>
                +2σ <span className="font-mono tabular-nums">{scale.high.toFixed(2)}</span>
                {u}
              </span>
            </>
          ) : (
            <>
              <span>
                min <span className="font-mono tabular-nums">{scale.low.toFixed(2)}</span>
              </span>
              <span>
                max <span className="font-mono tabular-nums">{scale.high.toFixed(2)}</span>
              </span>
            </>
          )}
        </div>
      )}

      {((controlTypesPresent && controlTypesPresent.length > 0) || hasOutliers) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
          {controlTypesPresent?.map((t) => (
            <span key={t} className="flex items-center gap-1">
              <span
                className="inline-block h-2.5 w-2.5"
                style={{
                  border: `1.5px solid ${colors[t]}`,
                  background: "transparent",
                }}
              />
              {WELL_TYPE_LABEL[t]}
            </span>
          ))}
          {hasOutliers && <span>✕ Outlier · left out of QC</span>}
        </div>
      )}
    </div>
  );
}

const WELL_TYPE_LABEL: Record<
  "negative_control" | "positive_control" | "blank" | "reference",
  string
> = {
  negative_control: "Negative control",
  positive_control: "Positive control",
  blank: "Blank",
  reference: "Reference",
};
