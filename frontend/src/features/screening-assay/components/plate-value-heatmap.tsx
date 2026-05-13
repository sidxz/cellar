"use client";

import { Fragment, useMemo } from "react";
import { cn } from "@/shared/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { StructureThumbnail } from "@/shared/components/chemistry";
import type { DoseUnit, PlateData, PlateMapWell } from "../types";
import { plateDimensionsTuple, plateCellSizePx, rowLabel } from "../lib/plate-dimensions";
import { WELL_TYPE_COLORS, WELL_EMPTY_COLOR } from "@/shared/lib/chart-colors";

// ─── Color palettes ──────────────────────────────────────────────────────────

type ColorStops = ReadonlyArray<readonly [number, readonly [number, number, number]]>;

/** Diverging palette — signed scales (z-score, NEG/POS anchored).
 *  t=0 dark blue → 0.5 near-white → 1 near-black via red. */
const DIVERGING_STOPS: ColorStops = [
  [0.0, [30, 58, 138]],     // blue-900
  [0.25, [96, 165, 250]],   // blue-400
  [0.5, [248, 250, 252]],   // slate-50
  [0.75, [220, 38, 38]],    // red-600
  [1.0, [20, 5, 5]],        // near-black
];

/** Sequential palette — unsigned magnitude (dose, raw counts).
 *  Pale → red → dark red. Reads as "low → high" without implying a
 *  meaningful midpoint. */
const SEQUENTIAL_STOPS: ColorStops = [
  [0.0, [254, 242, 242]],   // red-50
  [0.25, [252, 165, 165]],  // red-300
  [0.5, [239, 68, 68]],     // red-500
  [0.75, [185, 28, 28]],    // red-700
  [1.0, [69, 10, 10]],      // red-950
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
   *  For z-score: mean − 2σ. For linear: scale min / NEG anchor. */
  low: number;
  /** Value mapped to t=0.75 in diverging palettes (or t=1 in sequential).
   *  For z-score: mean + 2σ. For linear: scale max / POS anchor. */
  high: number;
  /** "linear" | "zscore" — drives legend labels. */
  kind: ScaleKind;
  /** Linear scales anchored on per-plate NEG/POS control means. False for
   *  min/max scales and all z-score scales. */
  controlAnchored: boolean;
  /** For z-score legends: the underlying mean and σ so the legend can
   *  render σ tick marks. */
  zMean?: number;
  zStd?: number;
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
  rawValue,
  computedValue,
  rawUnit,
  computedUnit,
  doseUnit,
}: {
  well: PlateMapWell;
  rawValue: number | undefined;
  computedValue: number | undefined;
  rawUnit: string | null;
  computedUnit: string;
  doseUnit: DoseUnit;
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
        <span className="font-mono text-xs font-medium">{well.position}</span>
        <span className="text-[10px] capitalize opacity-70">
          {well.well_type.replace(/_/g, " ")}
        </span>
      </div>
      {well.batch_number && (
        <p className="font-mono text-[11px] truncate">{well.batch_number}</p>
      )}
      {aliases.length > 0 && (
        <p className="text-[10px] italic opacity-70 line-clamp-2">
          {aliases.join(" · ")}
        </p>
      )}
      {well.dose != null && (
        <p className="text-[10px]">
          Dose: <span className="tabular-nums">{well.dose}</span> {doseUnit}
        </p>
      )}
      {rawValue != null && (
        <p className="text-[11px]">
          Raw:{" "}
          <span className="font-mono tabular-nums">{rawValue.toFixed(3)}</span>
          {rawUnit ? ` ${rawUnit}` : ""}
        </p>
      )}
      {computedValue != null && (
        <p className="text-[11px]">
          {computedUnit}:{" "}
          <span className="font-mono tabular-nums">
            {computedValue.toFixed(3)}
          </span>
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
  doseUnit: DoseUnit;
  className?: string;
}

const CONTROL_OUTLINE: Record<string, string> = {
  positive_control: WELL_TYPE_COLORS.positive_control,
  negative_control: WELL_TYPE_COLORS.negative_control,
  blank: WELL_TYPE_COLORS.blank,
  reference: WELL_TYPE_COLORS.reference,
};

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
  className,
}: PlateValueHeatmapProps) {
  const [rows, cols] = plateDimensionsTuple(plate.format);
  const size = plateCellSizePx(plate.format);

  const wellMap = useMemo(() => {
    const m = new Map<string, PlateMapWell>();
    for (const well of plate.wells) m.set(well.position, well);
    return m;
  }, [plate.wells]);

  const labelSize =
    size >= 28 ? "text-xs" : size >= 18 ? "text-[10px]" : "text-[8px]";

  function getWellStyle(well: PlateMapWell | undefined): {
    background: string;
    border?: string;
  } {
    if (!well) return { background: WELL_EMPTY_COLOR };

    const outline = CONTROL_OUTLINE[well.well_type];
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

    if (v == null) return { background: WELL_EMPTY_COLOR };
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
                    const cell = (
                      <div
                        className="rounded-sm cursor-default transition-opacity hover:opacity-75"
                        style={{
                          width: size,
                          height: size,
                          background: style.background,
                          border: style.border,
                          boxSizing: "border-box",
                        }}
                      />
                    );
                    if (!well) return <Fragment key={pos}>{cell}</Fragment>;
                    return (
                      <Tooltip key={pos}>
                        <TooltipTrigger asChild>{cell}</TooltipTrigger>
                        <TooltipContent
                          side="top"
                          sideOffset={6}
                          collisionPadding={12}
                          className="bg-popover text-popover-foreground border shadow-lg p-2.5"
                        >
                          <WellTooltipContent
                            well={well}
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
  controlTypesPresent?: ReadonlyArray<"negative_control" | "positive_control" | "blank" | "reference">;
  className?: string;
}

export function ColorScaleLegend({
  scale,
  palette,
  unit,
  controlTypesPresent,
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
        color: WELL_TYPE_COLORS.negative_control,
      });
    }
    if (scale.posMean != null) {
      ticks.push({
        t: valueToT(scale.posMean, scale, palette),
        label: "POS",
        value: scale.posMean,
        color: WELL_TYPE_COLORS.positive_control,
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

      <div className="flex max-w-md justify-between text-[10px] text-muted-foreground">
        {scale.kind === "zscore" ? (
          <>
            <span>
              −2σ{" "}
              <span className="font-mono tabular-nums">
                {scale.low.toFixed(2)}
              </span>
              {u}
            </span>
            {scale.zMean != null && (
              <span>
                μ{" "}
                <span className="font-mono tabular-nums">
                  {scale.zMean.toFixed(2)}
                </span>
              </span>
            )}
            <span>
              +2σ{" "}
              <span className="font-mono tabular-nums">
                {scale.high.toFixed(2)}
              </span>
              {u}
            </span>
          </>
        ) : scale.controlAnchored ? (
          <>
            <span>
              NEG{" "}
              <span className="font-mono tabular-nums">
                {scale.low.toFixed(2)}
              </span>
              {u}
            </span>
            <span>
              POS{" "}
              <span className="font-mono tabular-nums">
                {scale.high.toFixed(2)}
              </span>
              {u}
            </span>
          </>
        ) : (
          <>
            <span>
              min{" "}
              <span className="font-mono tabular-nums">
                {scale.low.toFixed(2)}
              </span>
            </span>
            <span>
              max{" "}
              <span className="font-mono tabular-nums">
                {scale.high.toFixed(2)}
              </span>
            </span>
          </>
        )}
      </div>

      {controlTypesPresent && controlTypesPresent.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
          {controlTypesPresent.map((t) => (
            <span key={t} className="flex items-center gap-1">
              <span
                className="inline-block h-2.5 w-2.5"
                style={{
                  border: `1.5px solid ${WELL_TYPE_COLORS[t]}`,
                  background: "transparent",
                }}
              />
              {WELL_TYPE_LABEL[t]}
            </span>
          ))}
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
