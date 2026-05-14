import { describe, expect, it } from "vitest";
import type { HitCriterion, InterceptKey } from "../types";
import { deriveChannelHitDefaults } from "./hit-criteria-defaults";

const num = (
  readout_name: string,
  operator: HitCriterion["operator"],
  value: number,
  intercept_key?: InterceptKey,
): HitCriterion => ({
  readout_name,
  operator,
  value,
  ...(intercept_key ? { intercept_key } : {}),
});

const curveClass = (...classes: string[]): HitCriterion => ({
  readout_name: "Curve Class",
  operator: "in",
  value: classes,
});

const EC90: InterceptKey = { kind: "ec", level: 90 };
const EC50: InterceptKey = { kind: "ec", level: 50 };

describe("deriveChannelHitDefaults", () => {
  it("returns empty defaults when no criteria are provided", () => {
    const d = deriveChannelHitDefaults([], { name: "IC50", data_type: "dose_response" });
    expect(d.hit_operator).toBe("");
    expect(d.allowed_curve_classes).toEqual([]);
  });

  it("carries a single numeric criterion verbatim", () => {
    const d = deriveChannelHitDefaults(
      [num("IC50", "lt", 100)],
      { name: "IC50", data_type: "dose_response" },
    );
    expect(d).toMatchObject({
      hit_operator: "lt",
      hit_value: "100",
      hit_value_low: "",
      hit_value_high: "",
    });
  });

  it("pairs gt+lt into `between` (the bug the user caught)", () => {
    const d = deriveChannelHitDefaults(
      [num("IC50", "gt", 10), num("IC50", "lt", 100)],
      { name: "IC50", data_type: "dose_response" },
    );
    expect(d).toMatchObject({
      hit_operator: "between",
      hit_value: "",
      hit_value_low: "10",
      hit_value_high: "100",
    });
  });

  it("pairs gte+lte the same way", () => {
    const d = deriveChannelHitDefaults(
      [num("IC50", "lte", 50), num("IC50", "gte", 5)],
      { name: "IC50", data_type: "dose_response" },
    );
    expect(d.hit_operator).toBe("between");
    expect(d.hit_value_low).toBe("5");
    expect(d.hit_value_high).toBe("50");
  });

  it("only matches numeric criteria for the named readout", () => {
    const d = deriveChannelHitDefaults(
      [num("EC50", "gt", 10), num("IC50", "lt", 100)],
      { name: "IC50", data_type: "dose_response" },
    );
    expect(d.hit_operator).toBe("lt");
    expect(d.hit_value).toBe("100");
  });

  it("carries the Curve Class filter for dose-response readouts", () => {
    const d = deriveChannelHitDefaults(
      [num("IC50", "lt", 100), curveClass("full", "partial")],
      { name: "IC50", data_type: "dose_response" },
    );
    expect(d.allowed_curve_classes).toEqual(["full", "partial"]);
  });

  it("ignores Curve Class for non-DR readouts (the chip filter would dangle otherwise)", () => {
    const d = deriveChannelHitDefaults(
      [curveClass("full")],
      { name: "Raw Data", data_type: "numeric" },
    );
    expect(d.allowed_curve_classes).toEqual([]);
  });

  it("returns curve-class even when no numeric threshold matches", () => {
    const d = deriveChannelHitDefaults(
      [curveClass("full")],
      { name: "IC50", data_type: "dose_response" },
    );
    expect(d.hit_operator).toBe("");
    expect(d.allowed_curve_classes).toEqual(["full"]);
  });

  // ── intercept_key carry-forward (Surface #7 follow-on) ──────────────────────

  it("defaults intercept_key to null when no criterion specifies one", () => {
    const d = deriveChannelHitDefaults(
      [num("IC50", "lt", 100)],
      { name: "IC50", data_type: "dose_response" },
    );
    expect(d.intercept_key).toBeNull();
  });

  it("carries intercept_key from a single-criterion threshold", () => {
    const d = deriveChannelHitDefaults(
      [num("Resazurin", "lt", 50, EC90)],
      { name: "Resazurin", data_type: "dose_response" },
    );
    expect(d.hit_operator).toBe("lt");
    expect(d.hit_value).toBe("50");
    expect(d.intercept_key).toEqual(EC90);
  });

  it("carries matching intercept_key through a between pair", () => {
    const d = deriveChannelHitDefaults(
      [num("Resazurin", "gt", 5, EC90), num("Resazurin", "lt", 50, EC90)],
      { name: "Resazurin", data_type: "dose_response" },
    );
    expect(d.hit_operator).toBe("between");
    expect(d.intercept_key).toEqual(EC90);
  });

  it("refuses to pair lower/upper into `between` when their intercepts differ — keeps first criterion only", () => {
    const d = deriveChannelHitDefaults(
      // EC50 > 5 AND EC90 < 50 — semantically distinct intercepts; cannot
      // collapse to "EC50 between 5 and 50" or similar. Falls back to first.
      [num("Resazurin", "gt", 5, EC50), num("Resazurin", "lt", 50, EC90)],
      { name: "Resazurin", data_type: "dose_response" },
    );
    expect(d.hit_operator).toBe("gt");
    expect(d.hit_value).toBe("5");
    expect(d.intercept_key).toEqual(EC50);
  });

  it("treats missing intercept_key on one side as equal to null on the other (legacy pairing)", () => {
    // Pre-Surface-#7 criterion has no intercept_key (= primary = null);
    // post-Surface-#7 also-primary criterion stores explicit null. Both
    // should be treated as the same intercept and pair into `between`.
    const d = deriveChannelHitDefaults(
      [
        { readout_name: "IC50", operator: "gt", value: 10 },                   // undefined
        { readout_name: "IC50", operator: "lt", value: 100, intercept_key: null }, // explicit null
      ],
      { name: "IC50", data_type: "dose_response" },
    );
    expect(d.hit_operator).toBe("between");
    expect(d.intercept_key).toBeNull();
  });
});
