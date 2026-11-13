import { describe, expect, it } from "vitest";
import type { CompoundActivity, HitCriterion } from "../../types";
import { applyFilters, criterionLabel } from "./use-activity-tab";

const compound = (id: string, best: number | null): CompoundActivity => ({
  molecule_id: id,
  molecule_name: id,
  registration_number: id,
  run_count: 1,
  last_tested: null,
  smiles: null,
  batch_number: null,
  synonyms: [],
  readouts: { "ΔTm (Main)": { best, mean: best } },
});

const items = [
  compound("low", -3),
  compound("edge", 2),
  compound("inside", 0.5),
  compound("high", 4),
  compound("none", null),
];

describe("applyFilters", () => {
  it("outside keeps values below low or above high", () => {
    const rule: HitCriterion = {
      readout_name: "ΔTm (Main)",
      operator: "not_between",
      value: [-2, 2],
    };
    expect(applyFilters(items, [rule]).map((c) => c.molecule_id)).toEqual(["low", "high"]);
    expect(criterionLabel(rule)).toBe("ΔTm (Main) outside -2 – 2");
  });
});
