import { describe, expect, it } from "vitest";
import type { HitCriterion } from "../types";
import { applyHitFilter } from "./run-dr-results-transforms";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<CompoundCurveRow> = {}): CompoundCurveRow {
  return {
    molecule_id: "mol-1",
    molecule_name: "Compound A",
    registration_number: "REG-001",
    synonyms: [],
    smiles: null,
    batch_number: null,
    curve_type: "ic50",
    fitted_value: 10,
    fitted_unit: "nM",
    hill_slope: 1.0,
    top: 100,
    bottom: 0,
    r_squared: 0.99,
    num_points: 8,
    curve_class: "full",
    data_points: null,
    intercept_values: null,
    all_curves: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// applyHitFilter
// ---------------------------------------------------------------------------

describe("applyHitFilter", () => {
  it("returns all rows when criteria is empty", () => {
    const rows = [makeRow({ fitted_value: 5 }), makeRow({ molecule_id: "mol-2", fitted_value: 50 })];
    expect(applyHitFilter(rows, [])).toHaveLength(2);
  });

  it("filters rows below an IC50 threshold (lt operator)", () => {
    const rows = [
      makeRow({ molecule_id: "mol-1", fitted_value: 5 }),   // passes: 5 < 20
      makeRow({ molecule_id: "mol-2", fitted_value: 25 }),  // fails: 25 >= 20
      makeRow({ molecule_id: "mol-3", fitted_value: 19 }),  // passes: 19 < 20
    ];
    const criteria: HitCriterion[] = [
      { readout_name: "IC50", operator: "lt", value: 20 },
    ];
    const result = applyHitFilter(rows, criteria);
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.molecule_id)).toEqual(["mol-1", "mol-3"]);
  });

  it("filters by Curve Class (in operator)", () => {
    const rows = [
      makeRow({ molecule_id: "mol-1", curve_class: "full" }),
      makeRow({ molecule_id: "mol-2", curve_class: "partial" }),
      makeRow({ molecule_id: "mol-3", curve_class: "inactive" }),
    ];
    const criteria: HitCriterion[] = [
      { readout_name: "Curve Class", operator: "in", value: ["full", "partial"] },
    ];
    const result = applyHitFilter(rows, criteria);
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.molecule_id)).toEqual(["mol-1", "mol-2"]);
  });

  it("applies multiple criteria conjunctively (all must pass)", () => {
    const rows = [
      makeRow({ molecule_id: "mol-1", fitted_value: 5, curve_class: "full" }),   // passes both
      makeRow({ molecule_id: "mol-2", fitted_value: 50, curve_class: "full" }),  // fails lt
      makeRow({ molecule_id: "mol-3", fitted_value: 5, curve_class: "inactive" }), // fails class
    ];
    const criteria: HitCriterion[] = [
      { readout_name: "IC50", operator: "lt", value: 20 },
      { readout_name: "Curve Class", operator: "in", value: ["full", "partial"] },
    ];
    const result = applyHitFilter(rows, criteria);
    expect(result).toHaveLength(1);
    expect(result[0].molecule_id).toBe("mol-1");
  });
});
