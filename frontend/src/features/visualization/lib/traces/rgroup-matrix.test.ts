import { cellKey } from "@/features/sar-analysis/components/rgroup-matrix-grid";
import { describe, expect, it } from "vitest";
import { panelDefaults } from "../default-panels";
import { rgroupPositions } from "../derived";
import { carryConfig } from "../level-switch";
import { MATRIX_AXIS_CAP } from "../limits";
import { buildRGroupMatrix } from "./rgroup-matrix";
import { dataset, matrixWells, panel, pass } from "./test-fixtures";

const V = "rd:s:raw";
const CL = "Cl[*:1]";
const H = "[H][*:2]";

const matrix = (patch = {}) =>
  panel("rgroup-matrix", { category: "chem:rg1:R1", x: "chem:rg1:R2", y: V, ...patch });

describe("buildRGroupMatrix", () => {
  it("groups passing rows by their two R groups, counting compounds once", () => {
    const m = buildRGroupMatrix(
      matrixWells(),
      matrix(),
      Uint8Array.from([1, 1, 1, 0, 1, 1, 1]),
      new Set(),
    );
    expect(m.yValues).toEqual([CL, "F[*:1]"]);
    expect(m.xValues).toEqual([H]);
    const cell = m.cells.get(cellKey(CL, H));
    // m2's failing row is left out; m1's three wells are one compound.
    expect(cell).toMatchObject({ rows: [0, 1, 2], compounds: 1, value: 3, selected: false });
    expect(m.cells.get(cellKey("F[*:1]", H))?.value).toBe(5);
    // m3 (no match) and the control.
    expect(m.skipped).toBe(2);
    expect(m.noCompound).toBe(1);
    expect(m.truncated).toBe(false);
  });

  it("takes the mean when asked, and only counts without a value field", () => {
    const ds = matrixWells();
    const mean = buildRGroupMatrix(ds, matrix({ agg: "mean" }), pass(7), new Set());
    expect(mean.cells.get(cellKey(CL, H))?.value).toBe(28.5);
    const count = buildRGroupMatrix(ds, matrix({ y: undefined }), pass(7), new Set());
    expect(count.cells.get(cellKey(CL, H))).toMatchObject({ compounds: 2, value: null });
  });

  it("orders axes most-populated first", () => {
    const m = buildRGroupMatrix(matrixWells(), matrix(), pass(7), new Set());
    expect(m.yValues).toEqual([CL, "F[*:1]"]);
  });

  it("leaves censored values out of the value and counts them", () => {
    const ds = matrixWells();
    ds.values[`${V}:q`] = [null, null, ">", null, null, null, null];
    const m = buildRGroupMatrix(ds, matrix(), Uint8Array.from([1, 1, 1, 0, 1, 1, 1]), new Set());
    expect(m.cells.get(cellKey(CL, H))?.value).toBe(2);
    expect(m.censored).toBe(1);
  });

  it("marks the cell of a selected row", () => {
    const m = buildRGroupMatrix(matrixWells(), matrix(), pass(7), new Set(["w5"]));
    expect(m.cells.get(cellKey("F[*:1]", H))?.selected).toBe(true);
    expect(m.cells.get(cellKey(CL, H))?.selected).toBe(false);
  });

  it(`caps each axis at the ${MATRIX_AXIS_CAP} most-populated values`, () => {
    const n = 35;
    const r1 = Array.from({ length: n }, (_, k) => `${"C".repeat(k + 1)}[*:1]`);
    // The last R1 has a second compound, so it leads.
    const ids = [...r1.map((_, k) => `m${k}`), "extra"];
    const ds = dataset(
      {
        molecule_id: ids,
        structure: ids.map(() => "C"),
        "chem:rg1:R1:smiles": [...r1, r1[n - 1]],
        "chem:rg1:R2:smiles": ids.map(() => H),
      },
      {
        structure: "structure",
        "chem:rg1:R1:smiles": "structure",
        "chem:rg1:R2:smiles": "structure",
      },
    );
    const m = buildRGroupMatrix(ds, matrix({ y: undefined }), pass(n + 1), new Set());
    expect(m.yValues).toHaveLength(MATRIX_AXIS_CAP);
    expect(m.yValues[0]).toBe(r1[n - 1]);
    expect(m.yTotal).toBe(n);
    expect(m.xTotal).toBe(1);
    expect(m.truncated).toBe(true);
  });
});

describe("R-group matrix fields", () => {
  it("lists the R positions of each R-groups set", () => {
    expect(rgroupPositions(matrixWells())).toEqual(["chem:rg1:R1", "chem:rg1:R2"]);
    expect(rgroupPositions(dataset({ y: [1] }))).toEqual([]);
  });

  it("defaults to R1 rows × R2 columns and the median of the first numeric readout", () => {
    expect(panelDefaults(matrixWells(), "rgroup-matrix")).toEqual({
      category: "chem:rg1:R1",
      x: "chem:rg1:R2",
      y: V,
      agg: "median",
    });
  });

  it("becomes the default plot when its R-group columns are gone", () => {
    const before = matrixWells();
    const plain = dataset({ well_order: [1], [V]: [1] });
    const { panels, dropped } = carryConfig(
      { panels: [matrix()], filters: [], selectedIds: [], columns: before.columns },
      plain,
    );
    expect(panels[0].type).toBe("scatter");
    expect(dropped).toEqual(["Plot 1: Columns (R2)", "Plot 1: Rows (R1)"]);
  });
});
