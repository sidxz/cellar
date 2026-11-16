import { describe, expect, it } from "vitest";
import type { ActivityValue } from "../types";
import { activityEndpoint, selectivityRatio } from "./assay-evidence";

const av: ActivityValue = {
  value: 100,
  qualifier: "=",
  unit: "nM",
  source: "dose_response",
  curve_type: "ic50",
  r_squared: 0.98,
  data_point_count: 8,
  raw_data: null,
  curve_params: null,
};
const spec = { kind: "ic", level: 50 } as const;
const endpoint = (overrides: Partial<ActivityValue> = {}) => ({
  av: { ...av, ...overrides },
  spec: null,
  isPrimary: true,
});

describe("assay endpoint evidence", () => {
  it("does not substitute a fitted value for an explicitly unresolved aggregate", () => {
    const value = activityEndpoint(
      {
        ...av,
        intercept_aggregates: [
          {
            spec,
            selected_value: null,
            selected_qualifier: "nd",
            aggregate_stats: null,
            disagreement_flag: false,
          },
        ],
      },
      spec,
      true,
      "latest",
    );
    expect(value.value).toBeNull();
    expect(value.display.primary).toBe("ND");
    expect(value.display.sortValue).toBeNull();
  });
  it("uses the aggregate value and qualifier rather than the representative curve bound", () => {
    const value = activityEndpoint(
      {
        ...av,
        intercept_values: [
          {
            spec: { ...spec, basis: "relative_percent" },
            value: 900,
            at_bound: true,
            confidence_interval_low: null,
            confidence_interval_high: null,
          },
        ],
        intercept_aggregates: [
          {
            spec,
            selected_value: 200,
            selected_qualifier: "=",
            aggregate_stats: null,
            disagreement_flag: false,
          },
        ],
      },
      spec,
      true,
      "gmean",
    );
    expect(value.value).toBe(200);
    expect(value.display.kind).toBe("scalar");
  });
  it("keeps an aggregate's resolved value: one representative run's doses do not censor it", () => {
    // Three runs summarized as 50; the representative run's top dose is 10.
    const aggregated = endpoint({
      value: 50,
      run_count: 3,
      raw_data: [
        { x: 0.1, y: 5 },
        { x: 10, y: 40 },
      ],
      intercept_aggregates: [
        {
          spec: { kind: "primary" },
          selected_value: 50,
          selected_qualifier: "=",
          aggregate_stats: null,
          disagreement_flag: false,
        },
      ],
    });
    const value = activityEndpoint(aggregated.av, null, true, "gmean");

    expect(value.display.kind).toBe("scalar");
    expect(value.display.text).toBe("50.00");
    expect(selectivityRatio(aggregated, endpoint(), "gmean").value).toBeCloseTo(2);
  });
  it("still reads one curve's value above its top dose as a bound", () => {
    const single = endpoint({
      value: 50,
      raw_data: [
        { x: 0.1, y: 5 },
        { x: 10, y: 40 },
      ],
    });
    expect(activityEndpoint(single.av, null, true, "latest").display.text).toBe("> 10");
  });
  it.each(["nd", "excluded", ">", "<"])("preserves %s wire qualifiers", (qualifier) => {
    const value = activityEndpoint({ ...av, qualifier }, null, true, "latest");
    expect(value.display.kind).not.toBe("scalar");
    expect(selectivityRatio(endpoint({ qualifier }), endpoint(), "latest").value).toBeNull();
  });
});

describe("selectivity ratio", () => {
  it("converts mixed concentration units before dividing counter by target", () => {
    expect(
      selectivityRatio(endpoint(), endpoint({ value: 2, unit: "µM" }), "latest").value,
    ).toBeCloseTo(20);
  });
  it.each([null, "%", "mg/mL"])("rejects unknown/incompatible units %s", (unit) => {
    expect(selectivityRatio(endpoint({ unit }), endpoint(), "latest").value).toBeNull();
  });
  it.each([0, -1, null, Number.NaN, Number.POSITIVE_INFINITY])(
    "rejects invalid potency %s",
    (value) => {
      expect(selectivityRatio(endpoint({ value }), endpoint(), "latest").value).toBeNull();
    },
  );
  it("rejects a missing counter assay", () => {
    expect(selectivityRatio(endpoint(), { spec: null, isPrimary: true }, "latest").reason).toBe(
      "Missing assay result",
    );
  });
  it("rejects a fit at a bound even without a wire qualifier", () => {
    const target = {
      ...endpoint({
        intercept_values: [
          {
            spec: { ...spec, basis: "relative_percent" },
            value: 100,
            at_bound: true,
            confidence_interval_low: null,
            confidence_interval_high: null,
          },
        ],
        raw_data: [{ x: 20, y: 10 }],
      }),
      spec,
    };
    expect(selectivityRatio(target, endpoint(), "latest").value).toBeNull();
  });
});
