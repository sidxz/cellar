import { describe, expect, it } from "vitest";
import { colorSpecScalar, whereOptionToColorSpec } from "./sar-color-spec";

// WhereOption fixtures — source of truth: activity-where-options.ts WhereOption type.
// intercept_key must be InterceptKey | null  ({kind:"ec"|"ic", level:number} | null).
const drOpt = {
  id: "dr_curve:rd1",
  label: "IC50",
  source: "dr_curve" as const,
  readout_definition_id: "rd1",
  intercept_key: null,
  group: "dose_response" as const,
};

const numOpt = {
  id: "readout_data:rd2",
  label: "%Inh",
  source: "readout_data" as const,
  readout_definition_id: "rd2",
  intercept_key: null,
  group: "numeric_readout" as const,
};

// CurveInterceptValue fixture — matches research-organization types:
// { spec: CurveInterceptSpec, value: number, confidence_interval_low, confidence_interval_high, at_bound }
const interceptValueFixture = {
  spec: { kind: "ic" as const, level: 90, basis: "relative_percent" as const },
  value: 7,
  confidence_interval_low: null,
  confidence_interval_high: null,
  at_bound: false,
};

describe("sar-color-spec", () => {
  it("maps a DR where-option to a drc column", () => {
    const s = whereOptionToColorSpec("p1", "EGFR", drOpt);
    expect(s.column).toBe("drc:rd1");
    expect(s.source).toBe("dr_curve");
    expect(s.label).toMatch(/EGFR/);
  });

  it("maps a numeric where-option to an rd column", () => {
    const s = whereOptionToColorSpec("p1", "EGFR", numOpt);
    expect(s.column).toBe("rd:p1:rd2");
  });

  it("reads the primary scalar from av.value when interceptKey is null", () => {
    const av = {
      value: 42,
      qualifier: null,
      unit: null,
      source: "dose_response" as const,
      curve_type: null,
      r_squared: null,
      data_point_count: 1,
      raw_data: null,
      curve_params: null,
      intercept_values: null,
    };
    expect(colorSpecScalar(av, { interceptKey: null } as never)).toBe(42);
  });

  it("reads a keyed intercept scalar via findInterceptValue", () => {
    const av = {
      value: 1,
      qualifier: null,
      unit: null,
      source: "dose_response" as const,
      curve_type: null,
      r_squared: null,
      data_point_count: 1,
      raw_data: null,
      curve_params: null,
      intercept_values: [interceptValueFixture],
    };
    expect(colorSpecScalar(av, { interceptKey: { kind: "ic", level: 90 } } as never)).toBe(7);
  });
});
