import { describe, it, expect } from "vitest";
import { measurementToActivity } from "./measurement-to-activity";

describe("measurementToActivity", () => {
  it("returns null for nd qualifier", () => {
    const m = { value: null, value_qualifier: "nd", unit: "", hit_call: null, source_curve_id: null };
    expect(measurementToActivity(m as any, null)).toBeNull();
  });
  it("returns null for excluded qualifier", () => {
    const m = { value: null, value_qualifier: "excluded", unit: "", hit_call: null, source_curve_id: null };
    expect(measurementToActivity(m as any, null)).toBeNull();
  });
  it("returns readout ActivityValue when source_kind=readout_data", () => {
    const m = { value: 53.4, value_qualifier: "=", unit: "uM", hit_call: "hit", source_curve_id: null };
    const av = measurementToActivity(m as any, null);
    expect(av).toEqual(
      expect.objectContaining({
        value: 53.4,
        qualifier: "=",
        unit: "uM",
        source: "readout",
        raw_data: null,
        curve_params: null,
      }),
    );
    expect(av?.data_point_count).toBe(1);
  });
  it("uses replicate_count for data_point_count in readout branch when present", () => {
    const m = { value: 53.4, value_qualifier: "=", unit: "uM", hit_call: "hit", source_curve_id: null, replicate_count: 3 };
    const av = measurementToActivity(m as any, null);
    expect(av?.data_point_count).toBe(3);
  });
  it("returns dose_response ActivityValue when curve is provided", () => {
    const m = {
      value: 2.24, value_qualifier: "=", unit: "uM", hit_call: "miss",
      source_curve_id: "curve-1",
    };
    const curve = {
      id: "curve-1", raw_data: [{ x: 0.1, y: 5 }, { x: 100, y: 95 }],
      top: 100, bottom: 0, hill_slope: 1, fitted_value: 2.24,
      curve_class: "F", r_squared: 0.99, num_points: 2, fit_quality_warnings: [],
    };
    const av = measurementToActivity(m as any, curve as any);
    expect(av).toEqual(
      expect.objectContaining({
        source: "dose_response",
        value: 2.24,
        raw_data: [{ x: 0.1, y: 5 }, { x: 100, y: 95 }],
        curve_params: expect.objectContaining({ top: 100, bottom: 0, hill_slope: 1, curve_class: "F" }),
      }),
    );
  });
  it("falls back to readout shape when source_curve_id is set but curve is missing", () => {
    const m = { value: 100, value_qualifier: "=", unit: "uM", hit_call: "hit", source_curve_id: "curve-missing" };
    const av = measurementToActivity(m as any, null);
    expect(av?.source).toBe("readout");
    expect(av?.value).toBe(100);
    expect(av?.raw_data).toBeNull();
  });
});
