import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import { describe, expect, it } from "vitest";
import { snapshotToDoseResponseCurve } from "./snapshot-adapter";

const MIN_SNAP: CurveSnapshot = {
  fitted_value: 4.5,
  top: 95,
  bottom: -1,
  hill_slope: 1.2,
};

describe("snapshotToDoseResponseCurve", () => {
  it("threads chart fields when present (post-2026-05-14 snapshot)", () => {
    const snap: CurveSnapshot = {
      ...MIN_SNAP,
      r_squared: 0.92,
      curve_class: "full",
      curve_type: "ec50",
      confidence_interval_low: 3.8,
      confidence_interval_high: 5.3,
      fit_quality_warnings: ["wide_confidence_interval"],
      intercept_values: [
        { spec: { kind: "ec", level: 50 }, value: 4.5, at_bound: false },
        { spec: { kind: "ec", level: 90 }, value: 41.2, at_bound: false },
      ],
    };
    const out = snapshotToDoseResponseCurve(snap, {
      moleculeLabel: "CV-00967",
      channelLabel: "Resazurin EC50",
      unit: "uM",
    });
    expect(out.curve_type).toBe("ec50");
    expect(out.confidence_interval_low).toBe(3.8);
    expect(out.confidence_interval_high).toBe(5.3);
    expect(out.fit_quality_warnings).toEqual(["wide_confidence_interval"]);
    expect(out.intercept_values).toHaveLength(2);
    expect(out.fitted_unit).toBe("uM");
    expect(out.registration_number).toBe("CV-00967");
    expect(out.molecule_name).toBe("Resazurin EC50");
  });

  it("degrades gracefully on legacy snapshot without chart fields", () => {
    // Pre-2026-05-14 snapshots only carry the 4 core curve-shape fields
    // plus optional r_squared / curve_class. The chart's SummaryCard
    // falls back to curve_type ("ic50") and shows no chip strip / CI
    // strip / warning badges — the expand dialog still renders, just
    // without the richer chrome.
    const out = snapshotToDoseResponseCurve(MIN_SNAP, {
      moleculeLabel: "CV-00966",
      channelLabel: "EC50",
    });
    expect(out.curve_type).toBe("ic50");
    expect(out.confidence_interval_low).toBeNull();
    expect(out.confidence_interval_high).toBeNull();
    expect(out.fit_quality_warnings).toEqual([]);
    expect(out.intercept_values).toEqual([]);
    expect(out.fitted_unit).toBe("");
  });

  it("uses placeholder UUIDs for FK fields the chart never reads", () => {
    const out = snapshotToDoseResponseCurve(MIN_SNAP, {
      moleculeLabel: "X",
      channelLabel: "Y",
    });
    // Same placeholder for every FK so consumers can detect adapted
    // curves if they ever need to (no expected match against a real id).
    expect(out.id).toBe("00000000-0000-0000-0000-000000000000");
    expect(out.workspace_id).toBe(out.id);
    expect(out.molecule_id).toBe(out.id);
    expect(out.batch_id).toBe(out.id);
    expect(out.protocol_id).toBe(out.id);
    expect(out.run_id).toBe(out.id);
    expect(out.readout_definition_id).toBe(out.id);
  });

  it("derives num_points from raw_data length when present", () => {
    const out = snapshotToDoseResponseCurve(
      {
        ...MIN_SNAP,
        raw_data: [
          { x: 0.1, y: 90 },
          { x: 1, y: 60 },
          { x: 10, y: 10 },
        ],
      },
      { moleculeLabel: "X", channelLabel: "Y" },
    );
    expect(out.num_points).toBe(3);
  });
});
