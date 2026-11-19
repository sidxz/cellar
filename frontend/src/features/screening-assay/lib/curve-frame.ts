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

type Points = ReadonlyArray<{ x: number; y: number }> | null | undefined;

const HALF_DECADE = Math.sqrt(10);

export function curveFrame(
  pointSets: ReadonlyArray<Points>,
  opts: { percent: boolean },
): CurveFrame {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const points of pointSets) {
    for (const p of points ?? []) {
      if (!Number.isFinite(p.x) || p.x <= 0 || !Number.isFinite(p.y)) continue;
      xs.push(p.x);
      ys.push(p.y);
    }
  }
  if (xs.length === 0) return { xRange: undefined, yRange: undefined };

  const xRange: [number, number] = [Math.min(...xs) / HALF_DECADE, Math.max(...xs) * HALF_DECADE];
  return { xRange, yRange: opts.percent ? percentRange(ys) : dataRange(ys) };
}

function percentRange(ys: number[]): [number, number] {
  const lo = Math.min(0, ...ys);
  const hi = Math.max(100, ...ys);
  const pad = (hi - lo) / 10;
  return [lo - pad, hi + pad];
}

function dataRange(ys: number[]): [number, number] {
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const pad = hi > lo ? (hi - lo) / 20 : Math.abs(lo) / 20 || 1;
  return [lo - pad, hi + pad];
}
