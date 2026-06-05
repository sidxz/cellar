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
import type { CurveDetail, RunScope } from "../types";
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
export function aggregateValue(curves: CurveDetail[], mode: "gmean" | "mean"): number | null {
  const xs: number[] = [];
  for (const c of curves) {
    if (c.curve_class === "inactive") continue;
    if (!Number.isFinite(c.fitted_value) || c.fitted_value <= 0) continue;
    xs.push(c.fitted_value);
  }
  if (xs.length === 0) return null;
  if (mode === "gmean") {
    const logMean = xs.reduce((acc, v) => acc + Math.log10(v), 0) / xs.length;
    return 10 ** logMean;
  }
  return xs.reduce((acc, v) => acc + v, 0) / xs.length;
}

/**
 * Narrow a curve list to the runs allowed by a `RunScope`. The drawer
 * fetches every curve for a molecule via `GetMoleculeActivityDetail` and
 * then needs to honor the search criterion's per-protocol scope so its
 * pick (and the chart it draws) matches the grid cell.
 *
 * Modes:
 *  - `undefined` / `any` / `all` → no filter (return input).
 *  - `specific {run_ids[]}` (or legacy `run_id`) → keep curves with
 *    matching `run_id`. Empty selection returns `[]` (an invalid scope
 *    means nothing is in-scope; defensive, mirrors the picker's invalid
 *    state).
 *  - `latest` → keep ALL curves from the most recent `run_date` (a
 *    multi-DR run yields multiple curves per run, all of which belong).
 *    Curves with null `run_date` cannot win and are dropped.
 *  - `past_n_days` → keep curves whose `run_date >= today - N days`.
 *  - `date_range` → keep curves within the inclusive `[date_from, date_to]`
 *    window; either bound omitted is unbounded on that side; both omitted
 *    is a no-op (parity with the BE's `RunScope.all()` fallback).
 *
 * Null `run_date` is dropped from any date-based filter; passes through
 * untouched on `any` / `all` / `undefined`.
 */
export function filterCurvesByRunScope(
  curves: CurveDetail[],
  scope: RunScope | undefined,
): CurveDetail[] {
  if (!scope) return curves;
  if (scope.mode === "any" || scope.mode === "all") return curves;

  if (scope.mode === "specific") {
    const ids = new Set<string>();
    for (const id of scope.run_ids ?? []) ids.add(id);
    if (scope.run_id) ids.add(scope.run_id);
    if (ids.size === 0) return [];
    return curves.filter((c) => ids.has(c.run_id));
  }

  if (scope.mode === "latest") {
    let latestDate: string | null = null;
    let latestRunId: string | null = null;
    for (const c of curves) {
      if (c.run_date === null) continue;
      if (latestDate === null || c.run_date > latestDate) {
        latestDate = c.run_date;
        latestRunId = c.run_id;
      }
    }
    if (latestRunId === null) return [];
    return curves.filter((c) => c.run_id === latestRunId);
  }

  if (scope.mode === "past_n_days") {
    const threshold = new Date();
    threshold.setDate(threshold.getDate() - scope.days);
    const thresholdStr = threshold.toISOString().slice(0, 10);
    return curves.filter((c) => c.run_date !== null && c.run_date >= thresholdStr);
  }

  if (scope.mode === "date_range") {
    if (!scope.date_from && !scope.date_to) return curves;
    return curves.filter((c) => {
      if (c.run_date === null) return false;
      if (scope.date_from && c.run_date < scope.date_from) return false;
      if (scope.date_to && c.run_date > scope.date_to) return false;
      return true;
    });
  }

  return curves;
}
