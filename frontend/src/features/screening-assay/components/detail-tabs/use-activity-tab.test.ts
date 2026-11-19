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

describe("hitStatus — a dose-response readout reads its reported value", () => {
  const doses = [
    { x: 0.0002, y: 60 },
    { x: 100, y: 80 },
  ];
  const iv = (level: number, qualifier: string, value: number | null) => ({
    spec: { kind: "ec" as const, level, basis: "relative_percent" as const, label: null },
    value,
    at_bound: qualifier === ">",
    qualifier,
  });
  const compound = (
    curve_class: string,
    best: number | null,
    fitted_value: number,
    intercept_values: ReturnType<typeof iv>[],
  ) =>
    ({
      molecule_id: "m",
      readouts: {
        EC50: {
          best,
          mean: best,
          curve_class,
          data_points: doses,
          curve_params: { fitted_value, intercept_values },
        },
      },
    }) as unknown as CompoundActivity;
  const lt1: HitCriterion = { readout_name: "EC50", operator: "lt", value: 1 };
  const ec90 = (operator: HitCriterion["operator"], value: number): HitCriterion => ({
    readout_name: "EC50",
    operator,
    value,
    intercept_key: { kind: "ec", level: 90 },
  });

  it("a Curve Class rule that allows full also allows active at all doses", () => {
    const flat = compound("active_all_doses", null, 6.1, [iv(50, "<", 0.0002)]);
    const rule: HitCriterion = { readout_name: "Curve Class", operator: "in", value: ["full"] };
    expect(hitStatus(flat, [rule])).toBe("meets");
    expect(hitStatus(flat, [{ ...rule, value: ["partial"] }])).toBe("fails");
  });

  it("meets on a curve active at every dose, though no exact best exists", () => {
    // SACC-0428730-like: midpoint ~6 µM, every dose already past 50 %.
    const flat = compound("active_all_doses", null, 6.1, [iv(50, "<", 0.0002)]);
    expect(hitStatus(flat, [lt1])).toBe("meets");
  });

  it("an above-the-doses value fails an upper cut-off at its bound", () => {
    const partial = compound("partial", 3, 3, [iv(50, "=", 3), iv(90, ">", 100)]);
    expect(hitStatus(partial, [ec90("lte", 100)])).toBe("fails");
    expect(hitStatus(partial, [ec90("gte", 100)])).toBe("meets");
  });

  it("an n.d. value does not meet; a missing intercept has no data", () => {
    const partial = compound("partial", 3, 3, [iv(50, "=", 3), iv(90, "nd", null)]);
    expect(hitStatus(partial, [ec90("lt", 200)])).toBe("fails");
    const legacy = compound("full", 3, 3, [iv(50, "=", 3)]);
    expect(hitStatus(legacy, [ec90("lt", 200)])).toBe("no_data");
  });
});
