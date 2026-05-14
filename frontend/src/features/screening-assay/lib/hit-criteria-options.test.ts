import { describe, expect, it } from "vitest";
import type { InterceptSpec, ReadoutDefinition } from "../types";
import {
  buildHitCriterionOptions,
  optionIdForRule,
} from "./hit-criteria-options";

function rd(over: Partial<ReadoutDefinition>): ReadoutDefinition {
  return {
    id: "rd-1",
    name: "Resazurin",
    description: null,
    data_type: "numeric",
    unit: null,
    aggregation: "mean",
    precision: null,
    normalizations: [],
    is_calculated: false,
    calculation_formula: null,
    display_order: 0,
    pick_list_values: null,
    dose_response_config: null,
    ...over,
  } as ReadoutDefinition;
}

function spec(over: Partial<InterceptSpec>): InterceptSpec {
  return { kind: "ec", level: 50, basis: "relative_percent", label: null, ...over };
}

function drConfig(intercepts: InterceptSpec[] | undefined): ReadoutDefinition["dose_response_config"] {
  // Minimal fields the option builder consults; other DR fields ignored here.
  return {
    curve_type: "ec50",
    x_readout_name: null,
    y_readout_name: "Resazurin",
    intercepts,
    hill_slope_constraint: "unconstrained",
    activity_threshold: null,
    normalization_scope: "per_run",
    top_constraint: null,
    bottom_constraint: null,
    top_constraint_min: null,
    top_constraint_max: null,
    bottom_constraint_min: null,
    bottom_constraint_max: null,
    hill_slope_min: null,
    hill_slope_max: null,
    outlier_sigma: null,
  } as ReadoutDefinition["dose_response_config"];
}

describe("buildHitCriterionOptions", () => {
  it("emits one option per non-DR readout plus Curve Class", () => {
    const rds = [
      rd({ id: "a", name: "OD600", data_type: "numeric" }),
      rd({ id: "b", name: "Z'", data_type: "numeric" }),
    ];
    const options = buildHitCriterionOptions(rds);
    expect(options.map((o) => o.label)).toEqual(["OD600", "Z'", "Curve Class"]);
    expect(options.every((o) => o.intercept_key === null)).toBe(true);
  });

  it("emits one option per intercept for a DR readout with declared intercepts", () => {
    const rds = [
      rd({
        name: "Resazurin",
        data_type: "dose_response",
        dose_response_config: drConfig([
          spec({ kind: "ec", level: 50 }),
          spec({ kind: "ec", level: 90 }),
        ]),
      }),
    ];
    const options = buildHitCriterionOptions(rds);
    // 2 intercepts + Curve Class
    expect(options).toHaveLength(3);
    expect(options[0].label).toBe("Resazurin EC50");
    expect(options[1].label).toBe("Resazurin EC90");
    expect(options[2].label).toBe("Curve Class");
  });

  it("marks the first DR intercept as the primary (intercept_key=null)", () => {
    const rds = [
      rd({
        name: "Resazurin",
        data_type: "dose_response",
        dose_response_config: drConfig([
          spec({ kind: "ec", level: 50 }),
          spec({ kind: "ec", level: 90 }),
        ]),
      }),
    ];
    const options = buildHitCriterionOptions(rds);
    // Primary stays unkeyed so legacy rules round-trip with intercept_key=null
    expect(options[0].intercept_key).toBeNull();
    expect(options[1].intercept_key).toEqual({ kind: "ec", level: 90 });
  });

  it("uses spec.label when present", () => {
    const rds = [
      rd({
        name: "Resazurin",
        data_type: "dose_response",
        dose_response_config: drConfig([
          spec({ kind: "ec", level: 50, label: "Potency" }),
          spec({ kind: "ec", level: 90, label: "Coverage" }),
        ]),
      }),
    ];
    const labels = buildHitCriterionOptions(rds).map((o) => o.label);
    expect(labels).toEqual(["Resazurin Potency", "Resazurin Coverage", "Curve Class"]);
  });

  it("falls back to a single primary option for DR readouts with no declared intercepts", () => {
    const rds = [
      rd({
        name: "Resazurin",
        data_type: "dose_response",
        dose_response_config: drConfig(undefined),
      }),
    ];
    const options = buildHitCriterionOptions(rds);
    // 1 implicit primary + Curve Class
    expect(options).toHaveLength(2);
    expect(options[0].readout_name).toBe("Resazurin");
    expect(options[0].intercept_key).toBeNull();
  });
});

describe("optionIdForRule", () => {
  const rds: ReadoutDefinition[] = [
    rd({
      name: "Resazurin",
      data_type: "dose_response",
      dose_response_config: drConfig([
        spec({ kind: "ec", level: 50 }),
        spec({ kind: "ec", level: 90 }),
      ]),
    }),
    rd({ id: "b", name: "OD600", data_type: "numeric" }),
  ];

  it("maps a rule with explicit intercept_key to the matching option id", () => {
    const id = optionIdForRule(
      { readout_name: "Resazurin", operator: "lt", value: 50, intercept_key: { kind: "ec", level: 90 } },
      rds,
    );
    // Same id as the option produced by buildHitCriterionOptions for EC90
    const options = buildHitCriterionOptions(rds);
    expect(id).toBe(options[1].id);
  });

  it("maps a legacy DR rule (no intercept_key) to the primary option", () => {
    const id = optionIdForRule(
      { readout_name: "Resazurin", operator: "lt", value: 50 },
      rds,
    );
    const options = buildHitCriterionOptions(rds);
    expect(id).toBe(options[0].id); // primary intercept
  });

  it("maps a numeric readout rule to its own option id", () => {
    const id = optionIdForRule(
      { readout_name: "OD600", operator: "gt", value: 0.5 },
      rds,
    );
    const options = buildHitCriterionOptions(rds);
    const od600 = options.find((o) => o.readout_name === "OD600");
    expect(id).toBe(od600?.id);
  });

  it("maps a Curve Class rule to the Curve Class option", () => {
    const id = optionIdForRule(
      { readout_name: "Curve Class", operator: "in", value: ["full"] },
      rds,
    );
    expect(id).toBe("Curve Class");
  });
});
