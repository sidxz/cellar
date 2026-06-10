import { describe, expect, it } from "vitest";
import { buildHeatmapGrid } from "./rgroup-heatmap-grid";

// Three assignments over R1 × R2. m1 and m2 share the same (R1=F, R2=H) cell;
// m3 sits in a different cell (R1=Cl, R2=Me). The builder groups by the chosen
// (axisY, axisX) substituent pair and keeps the most-potent (min) scalar per
// cell.
const assignments: { molecule_id: string; rgroups: Record<string, string> }[] = [
  { molecule_id: "m1", rgroups: { R1: "F[*:1]", R2: "[H][*:2]" } },
  { molecule_id: "m2", rgroups: { R1: "F[*:1]", R2: "[H][*:2]" } },
  { molecule_id: "m3", rgroups: { R1: "Cl[*:1]", R2: "C[*:2]" } },
];

const scalars: Record<string, number | null> = { m1: 50, m2: 5, m3: 100 };
const scalarOf = (id: string) => scalars[id] ?? null;

describe("buildHeatmapGrid", () => {
  it("derives distinct, sorted substituents for each axis", () => {
    const grid = buildHeatmapGrid(assignments, "R2", "R1", scalarOf);
    // axisY = R2 substituents, axisX = R1 substituents, both distinct + sorted.
    expect(grid.yValues).toEqual(["C[*:2]", "[H][*:2]"].sort());
    expect(grid.xValues).toEqual(["Cl[*:1]", "F[*:1]"].sort());
  });

  it("groups molecules sharing a (y,x) substituent combo into one cell", () => {
    const grid = buildHeatmapGrid(assignments, "R2", "R1", scalarOf);
    const shared = grid.cells["[H][*:2]__F[*:1]"];
    expect(shared).toBeDefined();
    expect(shared.moleculeIds.sort()).toEqual(["m1", "m2"]);
    // best = most potent = min non-null scalar (5 beats 50).
    expect(shared.bestScalar).toBe(5);
  });

  it("keeps a singleton cell with its own scalar", () => {
    const grid = buildHeatmapGrid(assignments, "R2", "R1", scalarOf);
    const cell = grid.cells["C[*:2]__Cl[*:1]"];
    expect(cell).toBeDefined();
    expect(cell.moleculeIds).toEqual(["m3"]);
    expect(cell.bestScalar).toBe(100);
  });

  it("leaves combos with no assignment absent from cells (a gap)", () => {
    const grid = buildHeatmapGrid(assignments, "R2", "R1", scalarOf);
    // (R2=H, R1=Cl) and (R2=Me, R1=F) are present axis values but no molecule
    // occupies them — they must NOT appear in cells.
    expect(grid.cells["[H][*:2]__Cl[*:1]"]).toBeUndefined();
    expect(grid.cells["C[*:2]__F[*:1]"]).toBeUndefined();
  });

  it("yields bestScalar null when every molecule in the cell has no scalar", () => {
    const grid = buildHeatmapGrid(assignments, "R2", "R1", () => null);
    expect(grid.cells["[H][*:2]__F[*:1]"].bestScalar).toBeNull();
  });

  it("skips assignments missing either axis substituent", () => {
    const partial: { molecule_id: string; rgroups: Record<string, string> }[] = [
      ...assignments,
      { molecule_id: "m4", rgroups: { R1: "Br[*:1]" } }, // no R2
      { molecule_id: "m5", rgroups: { R2: "C[*:2]" } }, // no R1
    ];
    const grid = buildHeatmapGrid(partial, "R2", "R1", scalarOf);
    // Br only came in via an assignment with no R2, so it must not surface on
    // the R1 axis.
    expect(grid.xValues).not.toContain("Br[*:1]");
    // m4 / m5 produced no cell.
    const all = Object.values(grid.cells).flatMap((c) => c.moleculeIds);
    expect(all).not.toContain("m4");
    expect(all).not.toContain("m5");
  });
});
