/**
 * Selection rules for the search-results compound detail drawer.
 *
 * The drawer fetches every dose-response curve for a molecule via
 * ``GetMoleculeActivityDetail`` and then picks ONE representative to plot,
 * with optional overlay context for aggregate modes. The selection logic
 * mirrors the grid cell's BE-side rule so the chart and the grid cell
 * value stay consistent end-to-end.
 *
 * - ``latest``  → newest ``run_date`` wins (matches the BE default
 *                 ``LATEST_APPROVED_RUN``).
 * - ``best_r2`` → highest R² wins (legacy drawer default; kept as an
 *                 explicit mode).
 * - ``gmean`` / ``mean`` → representative = newest run_date (chart
 *                 draws its sigmoid solid for shape reference); aggregate
 *                 value is computed across all non-inactive contributors
 *                 and exposed as an amber marker via the overlay.
 */
import type { CurveDetail } from "../types";
import type { AggregationMode } from "./use-aggregation-mode";

/** Pick the curve to plot as the headline / rep, based on toolbar mode.
 *
 *  Returns ``null`` when the input list is empty (e.g. molecule has no
 *  curves for this protocol). Curves with null ``run_date`` sort to the
 *  back for latest / gmean / mean (treated as eldest) so a populated
 *  date always beats a missing one.
 */
export function pickRepresentative(
  curves: CurveDetail[],
  mode: AggregationMode,
): CurveDetail | null {
  if (curves.length === 0) return null;
  if (mode === "best_r2") {
    return [...curves].sort((a, b) => b.r_squared - a.r_squared)[0];
  }
  const sortedByDate = [...curves].sort((a, b) => {
    const ad = a.run_date ?? "";
    const bd = b.run_date ?? "";
    if (ad === bd) return 0;
    return ad < bd ? 1 : -1;
  });
  return sortedByDate[0];
}

/** Compute the aggregate (gmean / mean) across a set of curves'
 *  fitted_values. Mirrors the BE's chemistry-honest rule: Inactive
 *  curves drop out; everything else contributes.
 *
 *  Returns ``null`` when no contributors qualify (e.g. all Inactive).
 */
export function aggregateValue(
  curves: CurveDetail[],
  mode: "gmean" | "mean",
): number | null {
  const xs: number[] = [];
  for (const c of curves) {
    if (c.curve_class === "inactive") continue;
    if (!Number.isFinite(c.fitted_value) || c.fitted_value <= 0) continue;
    xs.push(c.fitted_value);
  }
  if (xs.length === 0) return null;
  if (mode === "gmean") {
    const logMean = xs.reduce((acc, v) => acc + Math.log10(v), 0) / xs.length;
    return Math.pow(10, logMean);
  }
  return xs.reduce((acc, v) => acc + v, 0) / xs.length;
}
