import { describe, expect, it } from "vitest";
import { activityValueToCurveSnapshot } from "./activity-curve-snapshot";

const DR = {
  source: "dose_response",
  value: 1.5,
  r_squared: 0.98,
  unit: "uM",
  raw_data: [{ x: 1, y: 2 }],
  curve_params: { top: 100, bottom: 0, hill_slope: 1, curve_class: "full" },
  additional_curves: null,
  aggregate: null,
} as unknown as Parameters<typeof activityValueToCurveSnapshot>[0];

describe("activityValueToCurveSnapshot", () => {
  it("maps a dose-response value to a CurveSnapshot", () => {
    const snap = activityValueToCurveSnapshot(DR);
    expect(snap).toMatchObject({
      fitted_value: 1.5,
      top: 100,
      bottom: 0,
      hill_slope: 1,
      r_squared: 0.98,
      curve_class: "full",
    });
    expect(snap?.raw_data).toHaveLength(1);
  });

  it("returns null for null / undefined / non-DR / empty-raw / missing-params / missing-value", () => {
    expect(activityValueToCurveSnapshot(null)).toBeNull();
    expect(activityValueToCurveSnapshot(undefined)).toBeNull();
    expect(activityValueToCurveSnapshot({ ...DR, source: "readout" } as never)).toBeNull();
    expect(activityValueToCurveSnapshot({ ...DR, raw_data: [] } as never)).toBeNull();
    expect(activityValueToCurveSnapshot({ ...DR, curve_params: null } as never)).toBeNull();
    expect(activityValueToCurveSnapshot({ ...DR, value: null } as never)).toBeNull();
  });

  it("marks the selected intercept when it differs from the primary fitted_value", () => {
    // Colored by IC90 (5.0) while the primary is 1.5 → a distinct marker at 5.0.
    const snap = activityValueToCurveSnapshot(DR, { value: 5.0, label: "IC90" });
    expect(snap?.fitted_value).toBe(1.5); // primary unchanged
    expect(snap?.selected_intercept).toEqual({ value: 5.0, label: "IC90" });
  });

  it("omits the selected marker when the channel IS the primary (no duplicate line)", () => {
    expect(
      activityValueToCurveSnapshot(DR, { value: 1.5, label: "IC50" })?.selected_intercept,
    ).toBeNull();
    expect(
      activityValueToCurveSnapshot(DR, { value: null, label: "IC50" })?.selected_intercept,
    ).toBeNull();
    expect(activityValueToCurveSnapshot(DR)?.selected_intercept).toBeNull();
  });
});
