/**
 * Carry-forward of protocol `recommended_hit_criteria` into a channel's
 * hit-threshold defaults. Used by both the campaign "Add from runs" dialog
 * and the manual channel popover so a chemist sees the same auto-prefill in
 * either path.
 *
 * Rules (mirrors what protocol Activity-tab filtering does at runtime):
 *   - All numeric criteria whose `readout_name` matches the readout def's
 *     `name` are collected together (a readout can have several criteria —
 *     e.g. `IC50 > 10` AND `IC50 < 100`).
 *   - Exactly one numeric ⇒ single-sided threshold (`lt`/`gt`/`lte`/`gte`).
 *   - Exactly one lower-bound (`gt`/`gte`) + one upper-bound (`lt`/`lte`)
 *     pair ⇒ `between` with [lower, upper]. Any other shape (two lowers,
 *     three criteria, etc.) keeps the first one and ignores the rest;
 *     callers can refine in the UI.
 *   - The free-standing "Curve Class" criterion (operator "in",
 *     readout_name literally "Curve Class") only applies to DR readouts
 *     and seeds `allowed_curve_classes`.
 */

import type { HitCriterion } from "../types";

export interface ChannelHitDefaults {
  /** "" means "(no threshold)". */
  hit_operator: "" | "lt" | "lte" | "gt" | "gte" | "between";
  hit_value: string;
  hit_value_low: string;
  hit_value_high: string;
  /** Empty array = "all classes pass" (no filter). */
  allowed_curve_classes: string[];
}

const EMPTY: ChannelHitDefaults = {
  hit_operator: "",
  hit_value: "",
  hit_value_low: "",
  hit_value_high: "",
  allowed_curve_classes: [],
};

const LOWERS = new Set(["gt", "gte"]);
const UPPERS = new Set(["lt", "lte"]);

export function deriveChannelHitDefaults(
  recommended: HitCriterion[] | null | undefined,
  readout: { name: string; data_type: string },
): ChannelHitDefaults {
  if (!recommended || recommended.length === 0) return { ...EMPTY };

  // Numeric criteria targeting this specific readout (by name).
  const numeric = recommended.filter(
    (c) => c.readout_name === readout.name && typeof c.value === "number",
  );

  // The free-standing Curve Class rule applies to any DR readout in the
  // protocol — it doesn't carry a readout name in the channel sense.
  const curveClass =
    readout.data_type === "dose_response"
      ? recommended.find(
          (c) =>
            c.readout_name === "Curve Class" &&
            c.operator === "in" &&
            Array.isArray(c.value),
        )
      : undefined;
  const allowed_curve_classes = (curveClass?.value as string[] | undefined) ?? [];

  if (numeric.length === 0) {
    return { ...EMPTY, allowed_curve_classes };
  }

  if (numeric.length === 1) {
    const c = numeric[0];
    return {
      hit_operator: c.operator as ChannelHitDefaults["hit_operator"],
      hit_value: String(c.value as number),
      hit_value_low: "",
      hit_value_high: "",
      allowed_curve_classes,
    };
  }

  // Two-or-more numerics: try to pair a lower bound with an upper bound
  // and present as `between`. Anything else collapses to the first criterion.
  const lower = numeric.find((c) => LOWERS.has(c.operator));
  const upper = numeric.find((c) => UPPERS.has(c.operator));
  if (lower && upper && lower !== upper) {
    return {
      hit_operator: "between",
      hit_value: "",
      hit_value_low: String(lower.value as number),
      hit_value_high: String(upper.value as number),
      allowed_curve_classes,
    };
  }

  const first = numeric[0];
  return {
    hit_operator: first.operator as ChannelHitDefaults["hit_operator"],
    hit_value: String(first.value as number),
    hit_value_low: "",
    hit_value_high: "",
    allowed_curve_classes,
  };
}
