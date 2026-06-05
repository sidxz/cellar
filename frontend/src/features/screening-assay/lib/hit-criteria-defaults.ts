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

import type { HitCriterion, InterceptKey } from "../types";

export interface ChannelHitDefaults {
  /** "" means "(no threshold)". */
  hit_operator: "" | "lt" | "lte" | "gt" | "gte" | "between";
  hit_value: string;
  hit_value_low: string;
  hit_value_high: string;
  /** Empty array = "all classes pass" (no filter). */
  allowed_curve_classes: string[];
  /** Which intercept the threshold compares against on a dose-response
   *  curve. `null` = primary (terse wire shape — matches Surface #7's
   *  `HitCriterion.intercept_key` convention). The caller is responsible
   *  for ignoring this on non-DR channels. */
  intercept_key: InterceptKey | null;
}

const EMPTY: ChannelHitDefaults = {
  hit_operator: "",
  hit_value: "",
  hit_value_low: "",
  hit_value_high: "",
  allowed_curve_classes: [],
  intercept_key: null,
};

const LOWERS = new Set(["gt", "gte"]);
const UPPERS = new Set(["lt", "lte"]);

/** Treat `undefined` and `null` as equal (both = "primary"). Matches by
 *  `(kind, level)` for explicit keys. */
function sameInterceptKey(
  a: InterceptKey | null | undefined,
  b: InterceptKey | null | undefined,
): boolean {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return a.kind === b.kind && a.level === b.level;
}

function normalizeKey(k: InterceptKey | null | undefined): InterceptKey | null {
  return k ?? null;
}

export function deriveChannelHitDefaults(
  recommended: HitCriterion[] | null | undefined,
  readout: { name: string; data_type: string },
  /** When set, only criteria targeting this intercept are considered for
   *  the numeric threshold. Used by the add-from-runs flow to derive
   *  per-intercept channels (e.g. one channel for `EC50 < 10` and a
   *  separate one for `EC90 < 50`) — each pulls only its own criterion.
   *
   *  Three modes:
   *    - `undefined` (omitted): no filter, any criterion on the readout
   *       wins — preserves the pre-#7 single-channel-per-readout behavior.
   *    - `null`: only criteria with `intercept_key` null/missing (primary)
   *       pass through.
   *    - `{kind, level}`: only criteria matching that exact intercept.
   *
   *  Curve-class criteria are *not* filtered — they apply to the readout
   *  as a whole, regardless of intercept. */
  interceptKey?: InterceptKey | null,
): ChannelHitDefaults {
  if (!recommended || recommended.length === 0) return { ...EMPTY };

  // Numeric criteria targeting this specific readout (by name). When the
  // caller passes an explicit `interceptKey` (including null = primary),
  // further filter to criteria targeting that intercept; otherwise leave
  // the full set so legacy callers behave unchanged.
  const numeric = recommended.filter((c) => {
    if (c.readout_name !== readout.name) return false;
    if (typeof c.value !== "number") return false;
    if (interceptKey !== undefined && !sameInterceptKey(c.intercept_key, interceptKey)) {
      return false;
    }
    return true;
  });

  // The free-standing Curve Class rule applies to any DR readout in the
  // protocol — it doesn't carry a readout name in the channel sense.
  const curveClass =
    readout.data_type === "dose_response"
      ? recommended.find(
          (c) => c.readout_name === "Curve Class" && c.operator === "in" && Array.isArray(c.value),
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
      intercept_key: normalizeKey(c.intercept_key),
    };
  }

  // Two-or-more numerics: try to pair a lower bound with an upper bound
  // and present as `between`. The pair must target the same intercept —
  // a "between [EC50_low, EC90_high]" range is incoherent and should fall
  // back to keeping only the first criterion.
  const lower = numeric.find((c) => LOWERS.has(c.operator));
  const upper = numeric.find((c) => UPPERS.has(c.operator));
  if (
    lower &&
    upper &&
    lower !== upper &&
    sameInterceptKey(lower.intercept_key, upper.intercept_key)
  ) {
    return {
      hit_operator: "between",
      hit_value: "",
      hit_value_low: String(lower.value as number),
      hit_value_high: String(upper.value as number),
      allowed_curve_classes,
      intercept_key: normalizeKey(lower.intercept_key),
    };
  }

  const first = numeric[0];
  return {
    hit_operator: first.operator as ChannelHitDefaults["hit_operator"],
    hit_value: String(first.value as number),
    hit_value_low: "",
    hit_value_high: "",
    allowed_curve_classes,
    intercept_key: normalizeKey(first.intercept_key),
  };
}
