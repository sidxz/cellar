/**
 * Cellar-only dose-response display helpers.
 *
 * The 4PL evaluator, the axis ratios and the marker sizes now live in
 * `@structflo/components/dose-response` — shared so the chart, this app's
 * canvas export and the other apps' renderers can't disagree about what a
 * curve looks like. What stays here is the compact-renderer sugar only cellar
 * uses.
 */

import {
  type CapturedPoint,
  type CurveLike,
  X_AXIS_FLOOR,
  buildCapturedPoints,
  generate4PLPoints,
} from "@structflo/components/dose-response";
import { curvePotency, curvePotencyText } from "./intercept-label";

/** Compact dose-response chart dimensions used in cell renderers / detail sheets. */
export const COMPACT_DR_CHART = {
  WIDTH: 220,
  HEIGHT: 160,
  POINTS: 80,
  RANGE_EXTENSION: 0.5,
} as const;

/** Tighter X-axis preset for grid-cell thumbnails — fewer pixels means
 *  less room for the asymptote tails, so we shrink the visible decade
 *  extension on each side. */
export const COMPACT_4PL_OPTIONS = { numPoints: 80, rangeExtension: 0.3 } as const;

/** Smoother preset for the search compound-detail sheet. */
export const DETAIL_4PL_OPTIONS = { numPoints: 100, rangeExtension: 0.5 } as const;

/**
 * Convenience wrapper around ``generate4PLPoints`` for compact renderers
 * that only have raw data points (not pre-computed xMin/xMax).
 *
 * Returns empty arrays when inputs would produce non-finite results
 * (e.g. fitted_value === 0, hill_slope === 0, or fewer than 2 positive
 * x-values in rawData).
 */
export function generate4PLFromData(
  params: { top: number; bottom: number; fitted_value: number; hill_slope: number },
  rawData: Array<{ x: number; y: number }>,
  options?: { numPoints?: number; rangeExtension?: number },
): { x: number[]; y: number[] } {
  if (!Number.isFinite(params.fitted_value) || params.fitted_value === 0) {
    return { x: [], y: [] };
  }
  if (!Number.isFinite(params.hill_slope) || params.hill_slope === 0) {
    return { x: [], y: [] };
  }

  const positiveXs = rawData.map((p) => p.x).filter((v) => v > 0);
  if (positiveXs.length < 2) return { x: [], y: [] };

  const ext = options?.rangeExtension ?? COMPACT_DR_CHART.RANGE_EXTENSION;
  const n = options?.numPoints ?? COMPACT_DR_CHART.POINTS;

  const xMin = Math.max(10 ** (Math.log10(Math.min(...positiveXs)) - ext), X_AXIS_FLOOR);
  const xMax = 10 ** (Math.log10(Math.max(...positiveXs)) + ext);

  const { x, y } = generate4PLPoints(params, xMin, xMax, n);
  return { x, y };
}

/** The backend's note of points left out of a fit for a dose <= 0 (no place on a log axis),
 *  suffixed with how many: `dose_zero_left_out:2`. */
const DOSE_ZERO_LEFT_OUT = "dose_zero_left_out:";

/** A fit-quality code worded for a chemist where cellar owns the wording; any other code
 *  passes through (the suite's summary card labels its own). */
export function fitNoteLabel(code: string): string {
  if (!code.startsWith(DOSE_ZERO_LEFT_OUT)) return code;
  const n = Number(code.slice(DOSE_ZERO_LEFT_OUT.length));
  return `${n} point${n === 1 ? "" : "s"} at dose 0 left out of the fit`;
}

/** The curve with its fit notes worded, and a note of the value it reports when that value
 *  is censored at the dose range — the suite's card headline shows the fitted number (the
 *  same object when there is nothing to add). */
export function withFitNotes<T extends CurveLike>(curve: T): T {
  const codes = curve.fit_quality_warnings ?? [];
  const reported =
    curvePotency(curve).kind === "qualifier" ? [`Reported as ${curvePotencyText(curve)}`] : [];
  if (!reported.length && !codes.some((c) => c.startsWith(DOSE_ZERO_LEFT_OUT))) return curve;
  return { ...curve, fit_quality_warnings: [...reported, ...codes.map(fitNoteLabel)] };
}

type Row = Record<string, unknown>;
const coords = (p: Row) => [p.concentration ?? p.x, p.response ?? p.y];

/**
 * The curve with its `excluded_points` placed for the shared chart.
 *
 * Every point index of a curve (an entry's `idx`, the editor's exclusions) counts positions in
 * one captured set: `raw_data` plus the excluded entries, stably sorted by dose (the backend's
 * `captured_set`). The shared chart builds that set too, but pins an entry with coordinates on
 * `raw_data[idx]`, its own point only while no excluded point sorts below it. So an excluded
 * entry gets an idx that pins nowhere (it is its own point), and a suggestion, one of the
 * raw_data points, the raw_data index of the point with its coordinates.
 */
export function placeExclusions<T extends CurveLike>(curve: T): T {
  if (!curve.excluded_points?.length) return curve;
  const raw = (curve.raw_data ?? []) as Row[];
  const excluded_points = (curve.excluded_points as Row[]).map((e) => {
    const [c, r] = coords(e);
    if (typeof e.idx !== "number" || typeof c !== "number" || typeof r !== "number") return e;
    if (e.excluded !== false) return { ...e, idx: -1 };
    const at = raw.findIndex((p) => coords(p)[0] === c && coords(p)[1] === r);
    return at < 0 ? e : { ...e, idx: at };
  });
  return { ...curve, excluded_points };
}

/** The curve's captured set as the chart draws it, and its entries as the curve editor edits
 *  them: each idx set to its point's position there, the index the editor toggles, previews
 *  and saves. Entries without a place (legacy, idx-less) follow as they are. */
export function editablePoints(curve: CurveLike): { captured: CapturedPoint[]; exclusions: Row[] } {
  const placed = placeExclusions(curve);
  const captured = buildCapturedPoints(placed.raw_data, placed.excluded_points);
  return {
    captured,
    exclusions: [
      ...captured.flatMap((p) =>
        p.exclusionEntry ? [{ ...p.exclusionEntry, idx: p.capturedIdx }] : [],
      ),
      ...((curve.excluded_points ?? []) as Row[]).filter((e) => typeof e.idx !== "number"),
    ],
  };
}
