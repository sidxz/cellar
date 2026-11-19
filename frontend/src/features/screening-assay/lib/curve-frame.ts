import { isPercentNormalization } from "./dose-response-math";

/**
 * One frame for every curve thumbnail in a table, so thumbnails compare at a glance.
 *
 * Derived from the scale and the data, not from any vendor's defaults:
 * - x: lowest to highest tested dose across the table, half a decade either side.
 * - y on a % layer: the scale's anchors (0 % and 100 %) and every point, padded by a
 *   tenth of that span, so both anchors always show and nothing is clipped.
 * - y on any other layer: the points' min to max, padded by a twentieth of the span.
 * An axis with no usable points is left to the chart (undefined).
 */

export interface CurveFrame {
  xRange: [number, number] | undefined;
  yRange: [number, number] | undefined;
}

/** A curve's points as `{x, y}` or as stored on a curve, `{concentration, response}`. */
type Points = ReadonlyArray<Record<string, unknown>> | null | undefined;

const HALF_DECADE = Math.sqrt(10);

export function curveFrame(
  pointSets: ReadonlyArray<Points>,
  opts: { percent: boolean },
): CurveFrame {
  // Min / max in the loop: spreading a large table into Math.min overflows the call stack.
  let [xLo, xHi, yLo, yHi] = [
    Number.POSITIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
    Number.POSITIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
  ];
  for (const points of pointSets) {
    for (const p of points ?? []) {
      const x = p.x ?? p.concentration;
      const y = p.y ?? p.response;
      if (typeof x !== "number" || typeof y !== "number") continue;
      if (!Number.isFinite(x) || x <= 0 || !Number.isFinite(y)) continue;
      xLo = Math.min(xLo, x);
      xHi = Math.max(xHi, x);
      yLo = Math.min(yLo, y);
      yHi = Math.max(yHi, y);
    }
  }
  if (xHi === Number.NEGATIVE_INFINITY) return { xRange: undefined, yRange: undefined };

  const xRange: [number, number] = [xLo / HALF_DECADE, xHi * HALF_DECADE];
  return { xRange, yRange: opts.percent ? percentRange(yLo, yHi) : dataRange(yLo, yHi) };
}

function percentRange(yLo: number, yHi: number): [number, number] {
  const lo = Math.min(0, yLo);
  const hi = Math.max(100, yHi);
  const pad = (hi - lo) / 10;
  return [lo - pad, hi + pad];
}

function dataRange(lo: number, hi: number): [number, number] {
  const pad = hi > lo ? (hi - lo) / 20 : Math.abs(lo) / 20 || 1;
  return [lo - pad, hi + pad];
}

interface CurveReadout {
  name: string;
  normalizations?: readonly string[] | null;
  dose_response_config?: { y_readout_name: string; y_normalization?: string | null } | null;
}

/** The layer a protocol's dose-response readout fits: the one it names, else its Y readout's
 *  first calculated layer; null on raw values. Without a name, the protocol's first curve. */
export function curveLayer(readouts: readonly CurveReadout[], curveName?: string): string | null {
  const curve = readouts.find((r) =>
    curveName === undefined ? r.dose_response_config != null : r.name === curveName,
  );
  const cfg = curve?.dose_response_config;
  if (!cfg) return null;
  if (cfg.y_normalization) return cfg.y_normalization;
  const y = readouts.find((r) => r.name === cfg.y_readout_name);
  return y?.normalizations?.find((n) => n !== "none") ?? null;
}

/** The y range for curves drawn together in one chart when every one fits a % layer: their
 *  points (excluded ones too) with the 0 % and 100 % anchors. Otherwise undefined, and the
 *  chart frames itself. */
export function percentYRange(
  curves: ReadonlyArray<{
    fitted_layer?: string | null;
    raw_data?: Points;
    excluded_points?: Points;
  }>,
): [number, number] | undefined {
  if (curves.length === 0 || !curves.every((c) => isPercentNormalization(c.fitted_layer))) {
    return undefined;
  }
  return curveFrame(
    curves.flatMap((c) => [c.raw_data, c.excluded_points]),
    { percent: true },
  ).yRange;
}
