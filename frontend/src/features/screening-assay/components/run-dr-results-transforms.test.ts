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

  it("filters by a secondary intercept (intercept_key=EC90) instead of fitted_value", () => {
    const iv = (kind: "ec" | "ic", level: number, value: number) => ({
      spec: { kind, level, basis: "relative_percent" as const, label: null },
      value,
      confidence_interval_low: null,
      confidence_interval_high: null,
      at_bound: false,
    });
    const rows = [
      // mol-1: primary EC50=5 (would pass lt 50), EC90=80 (fails lt 50)
      makeRow({
        molecule_id: "mol-1",
        fitted_value: 5,
        intercept_values: [iv("ec", 50, 5), iv("ec", 90, 80)],
      }),
      // mol-2: primary EC50=2 (passes lt 50), EC90=10 (passes lt 50)
      makeRow({
        molecule_id: "mol-2",
        fitted_value: 2,
        intercept_values: [iv("ec", 50, 2), iv("ec", 90, 10)],
      }),
    ];
    const criteria: HitCriterion[] = [
      {
        readout_name: "Resazurin",
        operator: "lt",
        value: 50,
        intercept_key: { kind: "ec", level: 90 },
      },
    ];
    const result = applyHitFilter(rows, criteria);
    expect(result.map((r) => r.molecule_id)).toEqual(["mol-2"]);
  });

  it("with intercept_key set but no matching value on the row, the row is rejected", () => {
    const iv = (kind: "ec" | "ic", level: number, value: number) => ({
      spec: { kind, level, basis: "relative_percent" as const, label: null },
      value,
      confidence_interval_low: null,
      confidence_interval_high: null,
      at_bound: false,
    });
    const rows = [
      makeRow({
        molecule_id: "mol-legacy",
        fitted_value: 5,
        // EC50 only — protocol later added EC90 but this curve was never refit
        intercept_values: [iv("ec", 50, 5)],
      }),
    ];
    const criteria: HitCriterion[] = [
      {
        readout_name: "Resazurin",
        operator: "lt",
        value: 50,
        intercept_key: { kind: "ec", level: 90 },
      },
    ];
    const result = applyHitFilter(rows, criteria);
    expect(result).toHaveLength(0);
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
