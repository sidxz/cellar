import { groupBy } from "@/shared/lib/group-by";
import type { CurveClass, DoseResponseCurve, HitCriterion } from "../types";

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
      registration_number: best.registration_number ?? best.molecule_id.slice(0, 8),
      synonyms: best.synonyms ?? [],
      smiles: best.smiles,
      batch_number: best.batch_number,
      curve_type: best.curve_type,
      fitted_value: best.fitted_value,
      fitted_unit: best.fitted_unit,
      hill_slope: best.hill_slope,
      top: best.top,
      bottom: best.bottom,
      r_squared: best.r_squared,
      num_points: best.num_points,
      curve_class: best.curve_class as CurveClass | null,
      data_points: dataPoints,
      all_curves: molCurves,
    });
  }
  return rows;
}

/** Apply hit criteria filter to compound rows */
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
      // For IC50/EC50 rules — match against fitted_value
      const threshold = typeof rule.value === "number" ? rule.value : 0;
      switch (rule.operator) {
        case "gt":
          return row.fitted_value > threshold;
        case "lt":
          return row.fitted_value < threshold;
        case "gte":
          return row.fitted_value >= threshold;
        case "lte":
          return row.fitted_value <= threshold;
        default:
          return true;
      }
    }),
  );
}
