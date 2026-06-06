import { groupBy } from "@/shared/lib/group-by";
import { shortId } from "@/shared/lib/utils";
import { findInterceptValue } from "../lib/intercept-label";
import {
  type CurveClass,
  type DoseResponseCurve,
  type HitCriterion,
  type InterceptValue,
  narrowInterceptValues,
} from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** One row in the grid = one compound (best curve per molecule) */
export interface CompoundCurveRow {
  molecule_id: string;
  molecule_name: string;
  registration_number: string;
  synonyms: string[];
  smiles: string | null;
  batch_number: string | null;
  curve_type: string;
  fitted_value: number;
  fitted_unit: string;
  hill_slope: number;
  top: number;
  bottom: number;
  r_squared: number;
  num_points: number;
  curve_class: CurveClass | null;
  data_points: Array<{ x: number; y: number }> | null;
  /** Per-spec intercepts (EC50, EC90, IC10, ...) from this curve's fit.
   *  Columns matching protocol intercepts read values out of this list. */
  intercept_values: InterceptValue[] | null;
  /** All curves for this molecule in this run (for detail panel) */
  all_curves: DoseResponseCurve[];
}

// ---------------------------------------------------------------------------
// Transforms
// ---------------------------------------------------------------------------

/** Group curves by molecule, pick best (lowest fitted_value for IC50-type).
 *
 * The enrichment reader pre-populates `registration_number`, `synonyms`,
 * and `smiles` on each curve, so this no longer depends on a separate
 * paginated `useMolecules()` lookup (which hid structure for any compound
 * past the first page).
 */
export function buildCompoundRows(curves: DoseResponseCurve[]): CompoundCurveRow[] {
  const byMolecule = groupBy(curves, (c) => c.molecule_id);

  const rows: CompoundCurveRow[] = [];
  for (const [, molCurves] of byMolecule) {
    // Best curve = lowest fitted_value (most potent), excluding inactive
    const active = molCurves.filter((c) => c.curve_class !== "inactive");
    const sorted = (active.length > 0 ? active : molCurves).sort(
      (a, b) => a.fitted_value - b.fitted_value,
    );
    const best = sorted[0];

    // Condense raw_data to [{x, y}]
    let dataPoints: Array<{ x: number; y: number }> | null = null;
    if (best.raw_data && Array.isArray(best.raw_data)) {
      dataPoints = [];
      for (const pt of best.raw_data) {
        const x =
          (pt as Record<string, unknown>).concentration ?? (pt as Record<string, unknown>).x;
        const y = (pt as Record<string, unknown>).response ?? (pt as Record<string, unknown>).y;
        if (typeof x === "number" && typeof y === "number") {
          dataPoints.push({ x, y });
        }
      }
    }

    rows.push({
      molecule_id: best.molecule_id,
      molecule_name: best.molecule_name ?? "",
      registration_number: best.registration_number ?? shortId(best.molecule_id),
      synonyms: best.synonyms ?? [],
      smiles: best.smiles ?? null,
      batch_number: best.batch_number ?? null,
      curve_type: best.curve_type,
      fitted_value: best.fitted_value,
      fitted_unit: best.fitted_unit,
      hill_slope: best.hill_slope,
      top: best.top,
      bottom: best.bottom,
      r_squared: best.r_squared,
      num_points: best.num_points,
      curve_class: (best.curve_class as CurveClass | null) ?? null,
      data_points: dataPoints,
      intercept_values: narrowInterceptValues(best.intercept_values),
      all_curves: molCurves,
    });
  }
  return rows;
}

/** Apply hit criteria filter to compound rows.
 *
 *  Numeric rules read a scalar from the row before comparing against the
 *  threshold. A criterion with `intercept_key` set (e.g. `EC90`) looks up
 *  the matching `(kind, level)` pair in `row.intercept_values`; the
 *  legacy unkeyed path stays on `row.fitted_value` (= the primary intercept).
 *  A missing intercept (legacy curve fit before the protocol's intercept
 *  was added) makes the row fail the criterion. */
export function applyHitFilter(
  rows: CompoundCurveRow[],
  criteria: HitCriterion[],
): CompoundCurveRow[] {
  if (criteria.length === 0) return rows;
  return rows.filter((row) =>
    criteria.every((rule) => {
      if (rule.readout_name === "Curve Class") {
        if (rule.operator === "in" && Array.isArray(rule.value)) {
          return row.curve_class != null && (rule.value as string[]).includes(row.curve_class);
        }
        return true;
      }
      const measured = rowValueForRule(row, rule);
      if (measured === null) return false;
      const threshold = typeof rule.value === "number" ? rule.value : 0;
      switch (rule.operator) {
        case "gt":
          return measured > threshold;
        case "lt":
          return measured < threshold;
        case "gte":
          return measured >= threshold;
        case "lte":
          return measured <= threshold;
        default:
          return true;
      }
    }),
  );
}

function rowValueForRule(row: CompoundCurveRow, rule: HitCriterion): number | null {
  if (!rule.intercept_key) return row.fitted_value;
  const match = findInterceptValue(row.intercept_values, {
    kind: rule.intercept_key.kind,
    level: rule.intercept_key.level,
    basis: "relative_percent",
    label: null,
  });
  return match ? match.value : null;
}
