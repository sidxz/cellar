import { describe, expect, it } from "vitest";
import type { CompoundActivity, HitCriterion } from "../../types";
import { criterionLabel, hitStatus } from "./use-activity-tab";

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

describe("outside rule", () => {
  it("meets below low or above high, on the edge it does not", () => {
    const rule: HitCriterion = {
      readout_name: "ΔTm (Main)",
      operator: "not_between",
      value: [-2, 2],
    };
    expect(items.map((c) => hitStatus(c, [rule]))).toEqual([
      "meets",
      "fails",
      "fails",
      "meets",
      "no_data",
    ]);
    expect(criterionLabel(rule)).toBe("ΔTm (Main) outside -2 – 2");
  });
});

describe("hitStatus", () => {
  const compound = (values: Record<string, number | null>) =>
    ({
      molecule_id: "m",
      readouts: Object.fromEntries(
        Object.entries(values).map(([k, v]) => [k, { best: v, mean: v }]),
      ),
    }) as unknown as CompoundActivity;
  const outside: HitCriterion = {
    readout_name: "Max ΔTm",
    operator: "not_between",
    value: [-2, 2],
  };

  it("meets, does not meet, or has no data for the rule", () => {
    expect(hitStatus(compound({ "Max ΔTm": -8.5 }), [outside])).toBe("meets");
    expect(hitStatus(compound({ "Max ΔTm": -0.9 }), [outside])).toBe("fails");
    expect(hitStatus(compound({ Other: 1 }), [outside])).toBe("no_data");
    expect(hitStatus(compound({ "Max ΔTm": null }), [outside])).toBe("no_data");
  });

  it("a failed rule outweighs a missing one; no rule means no status", () => {
    const tm: HitCriterion = { readout_name: "Tm", operator: "gt", value: 60 };
    expect(hitStatus(compound({ "Max ΔTm": -0.9 }), [outside, tm])).toBe("fails");
    expect(hitStatus(compound({ "Max ΔTm": -8.5 }), [outside, tm])).toBe("no_data");
    expect(hitStatus(compound({ "Max ΔTm": -8.5 }), [])).toBeNull();
  });
});
