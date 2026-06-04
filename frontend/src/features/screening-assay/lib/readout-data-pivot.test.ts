import { describe, expect, it } from "vitest";
import type { DoseResponseCurve, ReadoutData } from "../types";
import { pivotReadoutData, valueKey } from "./readout-data-pivot";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<ReadoutData> = {}): ReadoutData {
  return {
    id: "rd-1",
    workspace_id: "ws-1",
    run_id: "run-1",
    well_id: "well-1",
    molecule_id: "mol-1",
    registration_number: "CC-001",
    molecule_name: "Compound A",
    synonyms: [],
    smiles: null,
    batch_id: "batch-1",
    batch_number: "B-001",
    readout_definition_id: "def-1",
    value_numeric: 42,
    value_qualifier: "=",
    value_text: null,
    is_outlier: false,
    is_computed: false,
    ...overrides,
  };
}

function makeCurve(overrides: Partial<DoseResponseCurve> = {}): DoseResponseCurve {
  return {
    id: "curve-1",
    workspace_id: "ws-1",
    molecule_id: "mol-1",
    registration_number: "CC-001",
    molecule_name: "Compound A",
    synonyms: [],
    smiles: null,
    batch_id: "batch-1",
    batch_number: "B-001",
    protocol_id: "proto-1",
    run_id: "run-1",
    readout_definition_id: "dr-def",
    curve_type: "ic50",
    fitted_value: 5,
    fitted_unit: "nM",
    hill_slope: 1,
    top: 100,
    bottom: 0,
    r_squared: 0.99,
    confidence_interval_low: null,
    confidence_interval_high: null,
    num_points: 8,
    curve_class: "full",
    raw_data: null,
    excluded_points: null,
    ...overrides,
  };
}

/** Build the `defId -> (mol::batch -> curve)` lookup the pivot consumes. */
function curveLookupOf(defId: string, molBatchKey: string, curve: DoseResponseCurve) {
  return new Map([[defId, new Map([[molBatchKey, curve]])]]);
}

const NO_CURVES = new Map<string, Map<string, DoseResponseCurve>>();

// ---------------------------------------------------------------------------
// Characterization — locks existing behavior (per-well + merge)
// ---------------------------------------------------------------------------

describe("pivotReadoutData — existing behavior", () => {
  it("returns [] for undefined data", () => {
    expect(pivotReadoutData(undefined, NO_CURVES)).toEqual([]);
  });

  it("returns [] for empty data", () => {
    expect(pivotReadoutData([], NO_CURVES)).toEqual([]);
  });

  it("emits one row per (molecule, batch, well)", () => {
    const rows = [
      makeRow({ well_id: "well-1", value_numeric: 10 }),
      makeRow({ well_id: "well-2", value_numeric: 20 }),
    ];
    const result = pivotReadoutData(rows, NO_CURVES);
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.wellId).sort()).toEqual(["well-1", "well-2"]);
  });

  it("keeps raw and computed layers of one readout def separate", () => {
    const rows = [
      makeRow({ readout_definition_id: "def-1", is_computed: false, value_numeric: 10 }),
      makeRow({ readout_definition_id: "def-1", is_computed: true, value_numeric: 95 }),
    ];
    const result = pivotReadoutData(rows, NO_CURVES);
    expect(result).toHaveLength(1);
    const row = result[0];
    expect(row.values.get(valueKey("def-1", false))?.value_numeric).toBe(10);
    expect(row.values.get(valueKey("def-1", true))?.value_numeric).toBe(95);
  });

  it("merges a well-less aggregate onto every well row of the same compound", () => {
    const rows = [
      makeRow({ well_id: "well-1", readout_definition_id: "raw", value_numeric: 10 }),
      makeRow({ well_id: "well-2", readout_definition_id: "raw", value_numeric: 20 }),
      makeRow({
        well_id: null,
        readout_definition_id: "ic50",
        is_computed: true,
        value_numeric: 5,
      }),
    ];
    const result = pivotReadoutData(rows, NO_CURVES);
    // Two wells; the aggregate is merged in, not emitted as its own row.
    expect(result).toHaveLength(2);
    for (const row of result) {
      expect(row.values.get(valueKey("ic50", true))?.value_numeric).toBe(5);
    }
  });

  it("attaches the compound's curve to its well rows", () => {
    const curve = makeCurve();
    const lookup = curveLookupOf("dr-def", "mol-1::batch-1", curve);
    const result = pivotReadoutData([makeRow({ well_id: "well-1" })], lookup);
    expect(result[0].curves.get("dr-def")).toBe(curve);
  });
});

// ---------------------------------------------------------------------------
// Well-less summary results — rows with no matching well must still render.
// (Summary Results Import attaches ReadoutData with well_id = NULL; when the
// compound has no plate/well in the run, those rows have nowhere to merge.)
// ---------------------------------------------------------------------------

describe("pivotReadoutData — well-less summary rows", () => {
  it("emits a standalone row for a well-less compound with no wells", () => {
    const rows = [
      makeRow({
        well_id: null,
        readout_definition_id: "ic50",
        is_computed: false,
        value_numeric: 7,
      }),
    ];
    const result = pivotReadoutData(rows, NO_CURVES);
    expect(result).toHaveLength(1);
    expect(result[0].wellId).toBeNull();
    expect(result[0].moleculeId).toBe("mol-1");
    expect(result[0].batchNumber).toBe("B-001");
    expect(result[0].registrationNumber).toBe("CC-001");
    expect(result[0].values.get(valueKey("ic50", false))?.value_numeric).toBe(7);
  });

  it("renders every compound of a summary-only run (no wells at all)", () => {
    const rows = [
      makeRow({ well_id: null, molecule_id: "mol-1", batch_id: "b1", registration_number: "CC-1" }),
      makeRow({ well_id: null, molecule_id: "mol-2", batch_id: "b2", registration_number: "CC-2" }),
      makeRow({ well_id: null, molecule_id: "mol-3", batch_id: "b3", registration_number: "CC-3" }),
    ];
    const result = pivotReadoutData(rows, NO_CURVES);
    expect(result).toHaveLength(3);
    expect(result.every((r) => r.wellId === null)).toBe(true);
    expect(result.map((r) => r.registrationNumber).sort()).toEqual(["CC-1", "CC-2", "CC-3"]);
  });

  it("mixes per-well compounds with summary-only compounds in one run", () => {
    const rows = [
      makeRow({
        molecule_id: "A",
        batch_id: "ba",
        well_id: "w1",
        readout_definition_id: "raw",
        value_numeric: 10,
      }),
      makeRow({
        molecule_id: "A",
        batch_id: "ba",
        well_id: "w2",
        readout_definition_id: "raw",
        value_numeric: 20,
      }),
      makeRow({
        molecule_id: "B",
        batch_id: "bb",
        well_id: null,
        readout_definition_id: "ic50",
        value_numeric: 99,
      }),
    ];
    const result = pivotReadoutData(rows, NO_CURVES);
    expect(result).toHaveLength(3);
    expect(result.filter((r) => r.moleculeId === "A")).toHaveLength(2);
    const b = result.find((r) => r.moleculeId === "B");
    expect(b?.wellId).toBeNull();
    expect(b?.values.get(valueKey("ic50", false))?.value_numeric).toBe(99);
  });

  it("does not double-emit when a compound has both well rows and well-less rows", () => {
    const rows = [
      makeRow({ well_id: "w1", readout_definition_id: "raw", value_numeric: 10 }),
      makeRow({
        well_id: null,
        readout_definition_id: "ic50",
        is_computed: true,
        value_numeric: 5,
      }),
    ];
    const result = pivotReadoutData(rows, NO_CURVES);
    // Single well row with the aggregate merged in — no extra standalone row.
    expect(result).toHaveLength(1);
    expect(result[0].wellId).toBe("w1");
    expect(result[0].values.get(valueKey("ic50", true))?.value_numeric).toBe(5);
  });

  it("attaches the compound's curve to a standalone well-less row", () => {
    const curve = makeCurve();
    const lookup = curveLookupOf("dr-def", "mol-1::batch-1", curve);
    const rows = [makeRow({ well_id: null, readout_definition_id: "ic50", value_numeric: 7 })];
    const result = pivotReadoutData(rows, lookup);
    expect(result).toHaveLength(1);
    expect(result[0].curves.get("dr-def")).toBe(curve);
  });
});

// ---------------------------------------------------------------------------
// Structure smiles — carried onto rows so the optional Structure column can
// render a thumbnail from it.
// ---------------------------------------------------------------------------

describe("pivotReadoutData — structure smiles", () => {
  it("carries the molecule smiles onto a well row", () => {
    const rows = [makeRow({ well_id: "w1", smiles: "CC(=O)Oc1ccccc1C(=O)O" })];
    const result = pivotReadoutData(rows, NO_CURVES);
    expect(result[0].smiles).toBe("CC(=O)Oc1ccccc1C(=O)O");
  });

  it("carries the molecule smiles onto a standalone well-less row", () => {
    const rows = [makeRow({ well_id: null, smiles: "CCO" })];
    const result = pivotReadoutData(rows, NO_CURVES);
    expect(result).toHaveLength(1);
    expect(result[0].smiles).toBe("CCO");
  });
});

// ---------------------------------------------------------------------------
// Optional API fields — `is_computed` is optional on the generated type (the
// DTO defaults it to False), so an absent value must be treated as raw.
// ---------------------------------------------------------------------------

describe("pivotReadoutData — optional API fields", () => {
  it("treats an absent is_computed as raw (not computed)", () => {
    const rows = [
      makeRow({
        well_id: "w1",
        readout_definition_id: "def-1",
        value_numeric: 10,
        is_computed: undefined,
      }),
    ];
    const result = pivotReadoutData(rows, NO_CURVES);
    expect(result[0].values.get(valueKey("def-1", false))?.value_numeric).toBe(10);
    expect(result[0].values.get(valueKey("def-1", true))).toBeUndefined();
  });
});
