import { describe, expect, it } from "vitest";
import type { DoseResponseCurve, HitCriterion } from "../types";
import { applyHitFilter, buildCompoundRows } from "./run-dr-results-transforms";
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

/** The protocol's dose-response readouts: the only rules this tab evaluates. */
const DR: ReadonlySet<string> = new Set(["IC50", "Resazurin"]);

describe("applyHitFilter", () => {
  it("returns all rows when criteria is empty", () => {
    const rows = [
      makeRow({ fitted_value: 5 }),
      makeRow({ molecule_id: "mol-2", fitted_value: 50 }),
    ];
    expect(applyHitFilter(rows, [], DR)).toHaveLength(2);
  });

  it("filters rows below an IC50 threshold (lt operator)", () => {
    const rows = [
      makeRow({ molecule_id: "mol-1", fitted_value: 5 }), // passes: 5 < 20
      makeRow({ molecule_id: "mol-2", fitted_value: 25 }), // fails: 25 >= 20
      makeRow({ molecule_id: "mol-3", fitted_value: 19 }), // passes: 19 < 20
    ];
    const criteria: HitCriterion[] = [{ readout_name: "IC50", operator: "lt", value: 20 }];
    const result = applyHitFilter(rows, criteria, DR);
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
    const result = applyHitFilter(rows, criteria, DR);
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.molecule_id)).toEqual(["mol-1", "mol-2"]);
  });

  it("a Curve Class rule that allows full also allows active at all doses", () => {
    const rows = [
      makeRow({ molecule_id: "flat", curve_class: "active_all_doses" }),
      makeRow({ molecule_id: "weak", curve_class: "partial" }),
    ];
    const full: HitCriterion[] = [{ readout_name: "Curve Class", operator: "in", value: ["full"] }];
    expect(applyHitFilter(rows, full, DR).map((r) => r.molecule_id)).toEqual(["flat"]);
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
    const result = applyHitFilter(rows, criteria, DR);
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
    const result = applyHitFilter(rows, criteria, DR);
    expect(result).toHaveLength(0);
  });

  it("applies multiple criteria conjunctively (all must pass)", () => {
    const rows = [
      makeRow({ molecule_id: "mol-1", fitted_value: 5, curve_class: "full" }), // passes both
      makeRow({ molecule_id: "mol-2", fitted_value: 50, curve_class: "full" }), // fails lt
      makeRow({ molecule_id: "mol-3", fitted_value: 5, curve_class: "inactive" }), // fails class
    ];
    const criteria: HitCriterion[] = [
      { readout_name: "IC50", operator: "lt", value: 20 },
      { readout_name: "Curve Class", operator: "in", value: ["full", "partial"] },
    ];
    const result = applyHitFilter(rows, criteria, DR);
    expect(result).toHaveLength(1);
    expect(result[0].molecule_id).toBe("mol-1");
  });

  it("skips a rule on a readout that is not a dose-response readout (e.g. ΔTm)", () => {
    const rows = [makeRow({ molecule_id: "mol-1", fitted_value: 0.5 })];
    // Would wrongly drop the row if applied to its fitted value (0.5 is not > 2).
    const criteria: HitCriterion[] = [{ readout_name: "ΔTm (Main)", operator: "gt", value: 2 }];
    expect(applyHitFilter(rows, criteria, DR)).toHaveLength(1);
  });

  it("evaluates outside on a dose-response readout", () => {
    const rows = [
      makeRow({ molecule_id: "mol-1", fitted_value: 0.5 }), // outside [1, 10]
      makeRow({ molecule_id: "mol-2", fitted_value: 5 }), // inside
    ];
    const criteria: HitCriterion[] = [
      { readout_name: "IC50", operator: "not_between", value: [1, 10] },
    ];
    expect(applyHitFilter(rows, criteria, DR).map((r) => r.molecule_id)).toEqual(["mol-1"]);
  });
});

describe("applyHitFilter — the reported value", () => {
  // Tested from 0.0002 to 100 µM, as on the WCA plate.
  const doses = [
    { x: 0.0002, y: 60 },
    { x: 1, y: 70 },
    { x: 100, y: 80 },
  ];
  const primary = (qualifier: string, value: number | null) => ({
    spec: { kind: "ec" as const, level: 50, basis: "relative_percent" as const, label: null },
    value,
    confidence_interval_low: null,
    confidence_interval_high: null,
    at_bound: qualifier === ">",
    qualifier,
  });
  const ec90 = (qualifier: string, value: number | null) => ({
    ...primary(qualifier, value),
    spec: { kind: "ec" as const, level: 90, basis: "relative_percent" as const, label: null },
  });
  const ids = (rows: CompoundCurveRow[], rule: HitCriterion) =>
    applyHitFilter(rows, [rule], DR).map((r) => r.molecule_id);

  it("a flat curve active at every dose meets a potency cut-off, whatever its midpoint", () => {
    // SACC-0519396-like: fitted midpoint ~6 µM is noise; the value reads "< 0.0002".
    const flat = makeRow({
      molecule_id: "flat",
      fitted_value: 6.2,
      curve_class: "active_all_doses",
      data_points: doses,
      intercept_values: [primary("<", 0.0002)],
    });
    expect(ids([flat], { readout_name: "IC50", operator: "lt", value: 1 })).toEqual(["flat"]);
    // "< 0.0002" can be anything below it: it never proves "> 0.001".
    expect(ids([flat], { readout_name: "IC50", operator: "gt", value: 0.001 })).toEqual([]);
  });

  it("a value above the doses never meets an upper cut-off at or above it", () => {
    const above = makeRow({
      molecule_id: "above",
      fitted_value: 100,
      curve_class: "partial",
      data_points: doses,
      intercept_values: [primary(">", 100), ec90(">", 100)],
    });
    expect(ids([above], { readout_name: "IC50", operator: "lte", value: 100 })).toEqual([]);
    expect(
      ids([above], {
        readout_name: "IC50",
        operator: "lt",
        value: 200,
        intercept_key: { kind: "ec", level: 90 },
      }),
    ).toEqual([]);
    expect(ids([above], { readout_name: "IC50", operator: "gt", value: 50 })).toEqual(["above"]);
  });

  it("a value the curve cannot give never meets, though its midpoint would", () => {
    const nd = makeRow({
      molecule_id: "nd",
      fitted_value: 1,
      curve_class: "partial",
      data_points: doses,
      intercept_values: [primary("nd", null)],
    });
    expect(ids([nd], { readout_name: "IC50", operator: "lt", value: 10 })).toEqual([]);
  });

  it("an exact value compares as a number", () => {
    const exact = makeRow({
      molecule_id: "exact",
      fitted_value: 3,
      data_points: doses,
      intercept_values: [primary("=", 3)],
    });
    expect(ids([exact], { readout_name: "IC50", operator: "lt", value: 10 })).toEqual(["exact"]);
  });
});

describe("buildCompoundRows — best curve", () => {
  const curve = (id: string, curve_class: string, fitted_value: number) =>
    ({
      id,
      molecule_id: "mol-1",
      curve_class,
      fitted_value,
      raw_data: [],
    }) as unknown as DoseResponseCurve;

  it("ranks a curve active at every dose ahead of an exact one, whatever its fitted midpoint", () => {
    // A flat curve's midpoint is noise (6.8 here); it is still the most potent result.
    const [row] = buildCompoundRows([
      curve("exact", "full", 0.5),
      curve("flat", "active_all_doses", 6.8),
    ]);
    expect(row.curve_class).toBe("active_all_doses");
  });

  const stored = (id: string, qualifier: string, fitted_value: number) =>
    ({
      id,
      molecule_id: "mol-1",
      curve_class: qualifier === "nd" ? "partial" : "full",
      fitted_value,
      raw_data: [],
      intercept_values: [{ spec: { kind: "ec", level: 50 }, value: null, qualifier }],
    }) as unknown as DoseResponseCurve;

  it("carries the layer the best curve fits, as the API names it", () => {
    const fit = { ...curve("a", "full", 1), fitted_layer: "percent_inhibition" };
    expect(buildCompoundRows([fit])[0].fitted_layer).toBe("percent_inhibition");
  });

  it("ranks an exact fit ahead of an n.d. one, though the n.d. midpoint is lower", () => {
    const [row] = buildCompoundRows([stored("nd", "nd", 1), stored("exact", "=", 3)]);
    expect(row.fitted_value).toBe(3);
  });

  it("ranks a stored below-the-doses value first and an above-the-doses one last", () => {
    const [row] = buildCompoundRows([
      stored("above", ">", 0.1),
      stored("exact", "=", 3),
      stored("below", "<", 50),
    ]);
    expect(row.fitted_value).toBe(50);
    const [rest] = buildCompoundRows([stored("above", ">", 0.1), stored("exact", "=", 3)]);
    expect(rest.fitted_value).toBe(3);
  });
});
