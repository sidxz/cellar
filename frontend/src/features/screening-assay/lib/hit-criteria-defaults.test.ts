import { describe, expect, it } from "vitest";
import type { HitCriterion } from "../types";
import { deriveChannelHitDefaults } from "./hit-criteria-defaults";

const num = (
  readout_name: string,
  operator: HitCriterion["operator"],
  value: number,
): HitCriterion => ({ readout_name, operator, value });

const curveClass = (...classes: string[]): HitCriterion => ({
  readout_name: "Curve Class",
  operator: "in",
  value: classes,
});

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
});
