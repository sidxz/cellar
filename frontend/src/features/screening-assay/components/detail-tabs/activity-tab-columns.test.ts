import type { ColDef, ValueGetterParams } from "ag-grid-community";
import { describe, expect, it } from "vitest";

import type { CompoundActivity } from "../../types";
import { type Statistic, buildColumnDefs } from "./activity-tab-columns";

const value = (statistic: Statistic, row: CompoundActivity) => {
  const cols = buildColumnDefs({
    catalog: [
      {
        colId: "ic50",
        readout: "IC50",
        kind: "intercept",
        label: "IC50",
        group: null,
        defaultVisible: true,
        empty: false,
        primary: true,
      },
    ],
    visible: new Set(["ic50"]),
    readoutDefs: [],
    statistic,
    showStructures: false,
    hits: null,
    sort: null,
    flagsByMolecule: new Map(),
    onToggleFlag: () => {},
  });
  const col = cols.find((c) => "colId" in c && c.colId === "ic50") as ColDef<CompoundActivity>;
  const getter = col.valueGetter as (p: Partial<ValueGetterParams<CompoundActivity>>) => unknown;
  return getter({ data: row });
};

describe("activity intercept column", () => {
  // The best curve tested up to 10; the mean of the compound's curves is 50.
  const row = {
    molecule_id: "m1",
    readouts: {
      IC50: {
        best: 50,
        mean: 50,
        curve_class: "full",
        data_points: [
          { x: 0.1, y: 5 },
          { x: 10, y: 40 },
        ],
      },
    },
  } as unknown as CompoundActivity;

  it("censors the best curve's value at its top dose, not a mean over several curves", () => {
    expect(value("best", row)).toBe(Number.POSITIVE_INFINITY);
    expect(value("mean", row)).toBe(50);
  });
});
