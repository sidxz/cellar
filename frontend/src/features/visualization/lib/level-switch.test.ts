import { describe, expect, it } from "vitest";
import type { PanelConfig } from "../store/workbench-store";
import type { Dataset, DatasetColumn } from "../types";
import type { Filter } from "./filters";
import { type Carry, carryConfig, switchNote } from "./level-switch";
import { panel } from "./traces/test-fixtures";

const X = "rd:x:percent_inhibition";
const Y = "rd:y:raw";

const col = (key: string, label: string, kind: DatasetColumn["kind"]): DatasetColumn => ({
  key,
  label,
  kind,
  provenance: key.startsWith("rd:") ? { readout_definition_id: key.split(":")[1] } : {},
});

const WELL_COLUMNS = [
  col("compound", "Compound", "category"),
  col("plate", "Plate", "category"),
  col("well_type", "Well type", "category"),
  col("well_order", "Well order", "number"),
  col(X, "% Inhibition", "number"),
  col(Y, "Signal", "number"),
];

const compounds: Dataset = {
  revision: "c",
  level: "compounds",
  row_count: 2,
  row_ids: ["m1", "m2"],
  columns: [
    col("compound", "Compound", "category"),
    col(X, "% Inhibition", "number"),
    col(Y, "Signal", "number"),
  ],
  values: { compound: ["CEL-1", "CEL-2"], [X]: [40, 80], [Y]: [1, 2] },
};

const carry = (panels: PanelConfig[], filters: Filter[] = []): Carry => ({
  panels,
  filters,
  selectedIds: [],
  columns: WELL_COLUMNS,
});

describe("carryConfig", () => {
  it("keeps filters on columns the new level has and lists the ones it drops", () => {
    const kept: Filter = {
      id: "f1",
      kind: "range",
      key: X,
      min: 30,
      max: null,
      includeMissing: false,
    };
    const filters: Filter[] = [
      kept,
      { id: "f2", kind: "range", key: "well_order", min: 1, max: 96, includeMissing: true },
      { id: "selection", kind: "rows", rowIds: ["w1", "w2"] },
    ];
    const out = carryConfig(carry([], filters), compounds);
    expect(out.filters).toEqual([kept]);
    expect(out.dropped).toEqual(["Filter: Well order", "Filter: Selection"]);
  });

  it("keeps a substructure filter at every level: molecule ids do not change between levels", () => {
    const sub: Filter = {
      id: "sub-1",
      kind: "substructure",
      query: "c1ccccc1",
      queryKind: "smiles",
      moleculeIds: ["m1"],
    };
    const out = carryConfig(carry([], [sub]), compounds);
    expect(out.filters).toEqual([sub]);
    expect(out.dropped).toEqual([]);
  });

  it("turns a well-order scatter into a histogram of its value, keeping the panel id", () => {
    const scatter = { ...panel("scatter", { x: "well_order", y: X }), id: "keep-me" };
    const out = carryConfig(carry([scatter]), compounds);
    expect(out.panels).toHaveLength(1);
    expect(out.panels[0]).toMatchObject({ id: "keep-me", type: "histogram", x: X, y: undefined });
    expect(out.dropped).toEqual(["Plot 1: X (Well order)", "Plot 1: Scatter (now a histogram)"]);
  });

  it("says when a compared protocol's field leaves a scatter that becomes a histogram", () => {
    const B = "rd:b:p";
    const scatter = panel("scatter", { x: B, y: X });
    const out = carryConfig(
      { ...carry([scatter]), columns: [...compounds.columns, col(B, "Counter · pIC50", "number")] },
      compounds,
    );
    expect(out.panels[0]).toMatchObject({ type: "histogram", x: X });
    expect(out.dropped).toEqual([
      "Plot 1: X (Counter · pIC50)",
      "Plot 1: Scatter (now a histogram)",
    ]);
  });

  it("clears appearance fields and tooltip entries the new level lacks, keeping the rest", () => {
    const scatter = panel("scatter", {
      x: X,
      y: Y,
      appearance: {
        colorBy: "plate",
        colorBins: [1, 2],
        shapeBy: "well_type",
        splitBy: "plate",
        sizeBy: Y,
        tooltip: ["compound", "well_order"],
      },
    });
    const out = carryConfig(carry([panel("histogram", { x: X }), scatter]), compounds);
    expect(out.panels[1]).toMatchObject({ type: "scatter", x: X, y: Y });
    expect(out.panels[1].appearance).toMatchObject({
      colorBy: undefined,
      colorBins: undefined,
      shapeBy: undefined,
      splitBy: undefined,
      sizeBy: Y,
      tooltip: ["compound"],
    });
    expect(out.dropped).toEqual([
      "Plot 2: Color (Plate)",
      "Plot 2: Shape (Well type)",
      "Plot 2: Split (Plate)",
      "Plot 2: Tooltip (Well order)",
    ]);
  });

  it("changes nothing when every field exists at the new level", () => {
    const filters: Filter[] = [
      { id: "f", kind: "category", key: "compound", values: ["CEL-1"], includeMissing: false },
    ];
    const panels = [panel("box", { y: X, category: "compound" })];
    expect(carryConfig(carry(panels, filters), compounds)).toEqual({
      panels,
      filters,
      dropped: [],
    });
  });
});

describe("switchNote", () => {
  it("names the level, what was dropped and that a selection does not carry", () => {
    expect(switchNote("compounds", ["Filter: Well order"], 3)).toBe(
      "Switched to Compounds. Not available at this level: Filter: Well order. " +
        "Selection cleared — rows differ between levels.",
    );
    expect(switchNote("runs", ["Plot 1: X (Well order)"], 0)).toBe(
      "Switched to Runs. Not available at this level: Plot 1: X (Well order).",
    );
    expect(switchNote("batches", [], 2)).toBe(
      "Switched to Batches. Selection cleared — rows differ between levels.",
    );
  });

  it("says nothing when nothing was lost", () => {
    expect(switchNote("compounds", [], 0)).toBeNull();
  });
});
