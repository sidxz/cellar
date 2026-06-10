import { describe, expect, it } from "vitest";
import { buildRGroupColumns, buildRGroupRows } from "./rgroup-table";

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
    const mw = cols.find((c) => c.colId === "mw");
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
    expect(mw?.valueFormatter?.({ value: 96.10000001 } as any)).toBe("96.1");
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
    expect(mw?.valueFormatter?.({ value: null } as any)).toBe("—");

    const clogp = cols.find((c) => c.colId === "clogp");
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
    expect(clogp?.valueFormatter?.({ value: 2.27 } as any)).toBe("2.27");
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
    expect(clogp?.valueFormatter?.({ value: null } as any)).toBe("—");

    const tpsa = cols.find((c) => c.colId === "tpsa");
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
    expect(tpsa?.valueFormatter?.({ value: 12.345 } as any)).toBe("12.3");
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid ValueFormatterParams shim for the unit test
    expect(tpsa?.valueFormatter?.({ value: null } as any)).toBe("—");
  });
});
