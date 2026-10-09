import { describe, expect, it } from "vitest";
import {
  fixedConditionChips,
  moveTestConcentration,
  readoutTestConcentration,
} from "./test-concentration";

const cond = (over: object = {}) => ({
  name: "Hypoxia",
  data_type: "text",
  unit: "",
  pick_list_values: [] as string[],
  fixed_value: "",
  ...over,
});

describe("fixedConditionChips", () => {
  it("lowercases a text or pick-list value and joins a numeric value to its unit", () => {
    expect(
      fixedConditionChips([
        cond({ name: "Oxygen", data_type: "pick_list", fixed_value: "Hypoxia" }),
        cond({ name: "Incubation time", data_type: "numeric", unit: "h", fixed_value: "72" }),
        cond({ name: "Compound", data_type: "numeric", unit: "µM", fixed_value: "2" }),
        cond({ name: "Count", data_type: "numeric", unit: null, fixed_value: "3" }),
      ]),
    ).toEqual(["hypoxia", "72 h", "2 µM", "3"]);
  });

  it("skips conditions without a fixed value and repeats nothing", () => {
    expect(
      fixedConditionChips([
        cond({ fixed_value: "  " }),
        cond({ name: "A", fixed_value: "Yes" }),
        cond({ name: "B", fixed_value: "yes" }),
      ]),
    ).toEqual(["yes"]);
  });
});

describe("readoutTestConcentration", () => {
  it("finds a concentration phrase in a readout name", () => {
    expect(readoutTestConcentration("% inhibition at 2 µM")).toEqual({ value: "2", unit: "µM" });
    expect(readoutTestConcentration("Growth at 0.5 mg/mL")).toEqual({
      value: "0.5",
      unit: "mg/mL",
    });
  });

  it("spells a typed u as µ", () => {
    expect(readoutTestConcentration("% inhibition at 10 uM")).toEqual({ value: "10", unit: "µM" });
  });

  it("ignores names without one", () => {
    expect(readoutTestConcentration("% inhibition")).toBeNull();
    expect(readoutTestConcentration("Count at 5 minutes")).toBeNull();
    expect(readoutTestConcentration("Signal at 2 µMol")).toBeNull();
  });
});

describe("moveTestConcentration", () => {
  it("strips the phrase and adds the Test concentration condition", () => {
    const out = moveTestConcentration("% inhibition at 2 µM", []);
    expect(out?.name).toBe("% inhibition");
    expect(out?.conditions).toEqual([
      {
        name: "Test concentration",
        data_type: "numeric",
        unit: "µM",
        pick_list_values: [],
        fixed_value: "2",
      },
    ]);
  });

  it("keeps the rest of the name tidy", () => {
    expect(moveTestConcentration("Growth at 5 nM (24 h)", [])?.name).toBe("Growth (24 h)");
  });

  it("updates an existing Test concentration, overwriting a different unit", () => {
    const existing = [
      cond({ name: "Hypoxia" }),
      cond({ name: "Test concentration", data_type: "numeric", unit: "nM", fixed_value: "5" }),
    ];
    const out = moveTestConcentration("Inhibition at 2 uM", existing);
    expect(out?.conditions).toHaveLength(2);
    expect(out?.conditions[1]).toMatchObject({
      unit: "µM",
      fixed_value: "2",
      data_type: "numeric",
    });
    expect(out?.conditions[0]).toBe(existing[0]);
  });

  it("returns null when the name has no concentration", () => {
    expect(moveTestConcentration("% inhibition", [])).toBeNull();
  });
});
