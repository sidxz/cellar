/**
 * Pure grid builder for the 2-axis R-group heatmap.
 *
 * Given the R-group decomposition assignments and a choice of two R-positions
 * (axisY / axisX), groups the matched molecules by their `(substituent at
 * axisY, substituent at axisX)` pair into a sparse grid of cells. Each cell
 * carries the molecules that share that substituent combination plus their
 * best (most-potent) activity scalar.
 *
 * "Most potent" = the minimum non-null scalar in the cell — a LOWER-is-better
 * convention that matches DR-fitted potencies (IC50/EC50/Kd). The component
 * only colors by this scalar for `dr_curve` sources (see {@link
 * potencyShade}); for `readout_data` it renders the cell uncolored. The builder
 * itself is colour-agnostic — it just surfaces the min scalar.
 *
 * Sparse on purpose: combos with no assignment simply have no entry in
 * `cells`, so the component can render those positions as gaps ("make?").
 */

export interface HeatmapCell {
  yValue: string;
  xValue: string;
  /** Molecule ids whose (axisY, axisX) substituents land in this cell. */
  moleculeIds: string[];
  /** Most potent (minimum non-null) scalar among the cell's molecules; null
   *  when none of them carry a scalar for the active color spec. */
  bestScalar: number | null;
}

export interface HeatmapGrid {
  /** Distinct substituent SMILES on the Y axis, sorted ascending. */
  yValues: string[];
  /** Distinct substituent SMILES on the X axis, sorted ascending. */
  xValues: string[];
  /** Sparse cell map keyed `${yValue}__${xValue}`. Absent key = a gap. */
  cells: Record<string, HeatmapCell>;
}

/** Stable cell key for a `(yValue, xValue)` substituent pair. */
export function heatmapCellKey(yValue: string, xValue: string): string {
  return `${yValue}__${xValue}`;
}

export function buildHeatmapGrid(
  assignments: { molecule_id: string; rgroups: Record<string, string> }[],
  axisY: string,
  axisX: string,
  scalarOf: (molId: string) => number | null,
): HeatmapGrid {
  const yValueSet = new Set<string>();
  const xValueSet = new Set<string>();
  const cells: Record<string, HeatmapCell> = {};

  for (const a of assignments) {
    const yValue = a.rgroups[axisY];
    const xValue = a.rgroups[axisX];
    // Skip assignments missing either axis substituent — they have no place on
    // a grid keyed by both positions.
    if (yValue == null || xValue == null) continue;

    yValueSet.add(yValue);
    xValueSet.add(xValue);

    const key = heatmapCellKey(yValue, xValue);
    const cell = cells[key] ?? { yValue, xValue, moleculeIds: [], bestScalar: null };
    cell.moleculeIds.push(a.molecule_id);

    const scalar = scalarOf(a.molecule_id);
    if (scalar != null && Number.isFinite(scalar)) {
      // Most potent = minimum (lower-is-better).
      cell.bestScalar = cell.bestScalar == null ? scalar : Math.min(cell.bestScalar, scalar);
    }

    cells[key] = cell;
  }

  return {
    yValues: [...yValueSet].sort(),
    xValues: [...xValueSet].sort(),
    cells,
  };
}
