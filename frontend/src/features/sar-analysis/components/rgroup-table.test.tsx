import type { ActivityValue } from "@/features/research-organization/types";
import { describe, expect, it } from "vitest";
import type { SarColorSpec } from "../lib/sar-color-spec";
import {
  buildActivityColumns,
  buildRGroupColumns,
  buildRGroupRows,
  pickReference,
  potencyShade,
} from "./rgroup-table";

const decomp = {
  core_smiles: "c1ccccc1",
  rgroup_labels: ["R1", "R2"],
  assignments: [
    { molecule_id: "m1", rgroups: { R1: "F[*:1]", R2: "[H][*:2]" } },
    { molecule_id: "m2", rgroups: { R1: "Cl[*:1]", R2: "[H][*:2]" } },
  ],
  unmatched_ids: [],
};

// Descriptor field names match the real Molecule type: descriptors.molecular_weight
// / descriptors.logp / descriptors.tpsa (NOT clogp), smiles at structure.smiles.
const mols = [
  {
    id: "m1",
    registration_number: "CV-1",
    name: "fluorobenzene",
    structure: { smiles: "Fc1ccccc1" },
    descriptors: { molecular_weight: 96.1, logp: 2.27, tpsa: 0 },
  },
  {
    id: "m2",
    registration_number: "CV-2",
    name: "chlorobenzene",
    structure: { smiles: "Clc1ccccc1" },
    descriptors: { molecular_weight: 112.56, logp: 2.84, tpsa: 0 },
  },
] as never;

describe("rgroup-table builders", () => {
  it("builds one row per matched assignment with R-group values + smiles", () => {
    const rows = buildRGroupRows(decomp as never, mols);
    expect(rows).toHaveLength(2);
    expect(rows[0].rgroups.R1).toBe("F[*:1]");
    expect(rows[0].smiles).toBe("Fc1ccccc1");
    expect(rows[0].registration_number).toBe("CV-1");
  });

  it("joins descriptors (mw/logp/tpsa) from the matched molecule", () => {
    const rows = buildRGroupRows(decomp as never, mols);
    expect(rows[0].mw).toBe(96.1);
    expect(rows[0].clogp).toBe(2.27);
    expect(rows[0].tpsa).toBe(0);
  });

  it("yields null fields for an assignment with no matching molecule", () => {
    const orphan = {
      ...decomp,
      assignments: [{ molecule_id: "missing", rgroups: { R1: "Br[*:1]", R2: "[H][*:2]" } }],
    };
    const rows = buildRGroupRows(orphan as never, mols);
    expect(rows).toHaveLength(1);
    expect(rows[0].smiles).toBeNull();
    expect(rows[0].registration_number).toBeNull();
    expect(rows[0].mw).toBeNull();
    // R-group values come from the assignment, so they survive a missing molecule.
    expect(rows[0].rgroups.R1).toBe("Br[*:1]");
  });

  it("builds a structure column + one column per rgroup label", () => {
    const cols = buildRGroupColumns(["R1", "R2"]);
    const ids = cols.map((c) => c.colId);
    expect(ids).toContain("structure");
    expect(ids).toEqual(expect.arrayContaining(["rg:R1", "rg:R2"]));
    expect(ids).toEqual(expect.arrayContaining(["mw", "clogp", "tpsa"]));
  });

  it("rgroup column valueGetter reads the substituent smiles off the row", () => {
    const cols = buildRGroupColumns(["R1"]);
    const r1 = cols.find((c) => c.colId === "rg:R1");
    expect(r1).toBeDefined();
    const getter = r1?.valueGetter;
    expect(typeof getter).toBe("function");
    const value =
      typeof getter === "function"
        ? // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueGetterParams shim for the unit test
          getter({ data: { rgroups: { R1: "F[*:1]" } } } as any)
        : undefined;
    expect(value).toBe("F[*:1]");
  });

  it("formats physchem columns to fixed precision with a dash for null", () => {
    const cols = buildRGroupColumns(["R1"]);
    // ColDef.valueFormatter is typed `string | func`; our builder always sets a
    // function. Narrow with `typeof` so the call is type-safe.
    const fmt = (colId: string, value: number | null) => {
      const f = cols.find((c) => c.colId === colId)?.valueFormatter;
      // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
      return typeof f === "function" ? f({ value } as any) : undefined;
    };
    expect(fmt("mw", 96.10000001)).toBe("96.1");
    expect(fmt("mw", null)).toBe("—");
    expect(fmt("clogp", 2.27)).toBe("2.27");
    expect(fmt("clogp", null)).toBe("—");
    expect(fmt("tpsa", 12.345)).toBe("12.3");
    expect(fmt("tpsa", null)).toBe("—");
  });

  it("inserts activity columns between the rgroup columns and physchem columns", () => {
    const activityCols = buildActivityColumns(colorSpec, {}, null);
    const cols = buildRGroupColumns(["R1"], activityCols);
    const ids = cols.map((c) => c.colId);
    const rgIdx = ids.indexOf("rg:R1");
    const valIdx = ids.indexOf("activity:value");
    const mwIdx = ids.indexOf("mw");
    // R-group → activity → physchem ordering.
    expect(rgIdx).toBeGreaterThanOrEqual(0);
    expect(valIdx).toBeGreaterThan(rgIdx);
    expect(mwIdx).toBeGreaterThan(valIdx);
  });
});

// ─── Activity: potency reference + shading + columns ──────────────────────────

const colorSpec: SarColorSpec = {
  protocolId: "p1",
  column: "drc:rd1",
  interceptKey: null,
  source: "dr_curve",
  label: "EGFR · IC50",
};

/** Minimal DR ActivityValue carrying a primary scalar (`value`) + a unit. */
function drActivity(value: number): ActivityValue {
  return {
    value,
    qualifier: "=",
    unit: "nM",
    source: "dose_response",
    curve_type: "ic50",
    r_squared: 0.99,
    data_point_count: 8,
    raw_data: [
      { x: 1e-9, y: 100 },
      { x: 1e-6, y: 0 },
    ],
    curve_params: {
      hill_slope: 1,
      top: 100,
      bottom: 0,
      num_points: 8,
      curve_class: "full",
      confidence_interval_low: null,
      confidence_interval_high: null,
    },
  };
}

describe("pickReference", () => {
  it("returns the minimum non-null scalar (most potent)", () => {
    expect(pickReference([30, 5, 100, null])).toBe(5);
  });

  it("ignores nulls and non-finite values", () => {
    expect(pickReference([null, Number.NaN, 12, Number.POSITIVE_INFINITY])).toBe(12);
  });

  it("returns null when empty or all-null", () => {
    expect(pickReference([])).toBeNull();
    expect(pickReference([null, null])).toBeNull();
  });
});

describe("potencyShade", () => {
  it("returns a green-ish class when the scalar is at/below the reference", () => {
    expect(potencyShade(5, 5)).toContain("green");
    expect(potencyShade(3, 5)).toContain("green");
  });

  it("returns a redder/weaker class as the scalar grows far above the reference", () => {
    // 1000× off the most-potent reference → the most-saturated (red) end.
    const far = potencyShade(5000, 5);
    expect(far).toContain("red");
    expect(far).not.toContain("green");
  });

  it("walks the ramp away from green as the fold increases", () => {
    // ≤3× still green; 6× (>3×) leaves green for the amber/orange/red end.
    expect(potencyShade(15, 5)).toContain("green"); // 3× — still green
    expect(potencyShade(30, 5)).not.toContain("green"); // 6× — off the green band
  });

  it("returns an empty string when the scalar or reference is null", () => {
    expect(potencyShade(null, 5)).toBe("");
    expect(potencyShade(5, null)).toBe("");
  });
});

describe("buildActivityColumns", () => {
  const activityByMolecule: Record<string, ActivityValue | undefined> = {
    m1: drActivity(5),
    m2: drActivity(50),
  };
  const reference = pickReference([5, 50]);

  it("returns a value column + a plot column with the expected colIds", () => {
    const cols = buildActivityColumns(colorSpec, activityByMolecule, reference);
    const ids = cols.map((c) => c.colId);
    expect(ids).toContain("activity:value");
    expect(ids).toContain("activity:plot");
  });

  it("uses colorSpecScalar(activity[id]) as the value column's valueGetter", () => {
    const cols = buildActivityColumns(colorSpec, activityByMolecule, reference);
    const val = cols.find((c) => c.colId === "activity:value");
    const getter = val?.valueGetter;
    expect(typeof getter).toBe("function");
    // primary intercept (interceptKey null) → av.value
    const got =
      typeof getter === "function"
        ? // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueGetterParams shim for the unit test
          getter({ data: { id: "m2" } } as any)
        : undefined;
    expect(got).toBe(50);
  });

  it("formats the value column to 3 sig figs with the cell's unit", () => {
    const cols = buildActivityColumns(colorSpec, activityByMolecule, reference);
    const val = cols.find((c) => c.colId === "activity:value");
    const f = val?.valueFormatter;
    const fmt =
      typeof f === "function"
        ? // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
          (f({ value: 5, data: { id: "m1" } } as any) as string)
        : undefined;
    expect(fmt).toBe("5.00 nM");
    const dash =
      typeof f === "function"
        ? // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
          (f({ value: null, data: { id: "m1" } } as any) as string)
        : undefined;
    expect(dash).toBe("—");
  });

  it("shades the value cell by potency vs the reference", () => {
    const cols = buildActivityColumns(colorSpec, activityByMolecule, reference);
    const val = cols.find((c) => c.colId === "activity:value");
    const cc = val?.cellClass;
    expect(typeof cc).toBe("function");
    const cls = (id: string) =>
      typeof cc === "function"
        ? // biome-ignore lint/suspicious/noExplicitAny: AG Grid CellClassParams shim for the unit test
          (cc({ data: { id } } as any) as string)
        : undefined;
    // m1 is the reference (5 nM) → green; m2 (50 nM, 10× off) → not green.
    expect(cls("m1")).toContain("green");
    expect(cls("m2")).not.toContain("green");
  });

  it("renders the DoseResponseCell in the plot column", () => {
    const cols = buildActivityColumns(colorSpec, activityByMolecule, reference);
    const plot = cols.find((c) => c.colId === "activity:plot");
    expect(typeof plot?.cellRenderer).toBe("function");
  });
});
