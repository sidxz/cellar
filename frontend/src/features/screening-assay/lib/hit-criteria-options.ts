/**
 * Hit-criteria LHS option builder + rule→option resolver.
 *
 * Spec: docs/superpowers/specs/2026-05-13-dynamic-intercept-columns-design.md (Surface #7)
 *
 * Today's hit-criteria dialog shows one entry per readout-definition name
 * plus "Curve Class". A criterion for a DR readout silently meant "primary
 * intercept (the headline fitted_value)". With the protocol now declaring
 * multiple intercepts per DR readout (EC50, EC90, IC10, …), the LHS picker
 * needs to surface each intercept as its own option so a chemist can author
 * an "EC90 < 50" rule directly.
 *
 * Wire contract: storing the primary intercept as `intercept_key=null` keeps
 * legacy criteria round-tripping unchanged; only secondary intercepts persist
 * an explicit `{kind, level}` key. The backend resolver and the FE filters
 * both fall back to the curve's `fitted_value` (= primary intercept) when
 * `intercept_key` is absent.
 */

import type {
  HitCriterion,
  InterceptKey,
  ReadoutDefinition,
} from "../types";
import { interceptOptionLabel } from "./intercept-label";

export interface HitCriterionOption {
  /** Stable id used as the Select value. */
  id: string;
  /** Human label rendered in the dropdown. */
  label: string;
  /** The criterion's `readout_name` slot. */
  readout_name: string;
  /** The criterion's `intercept_key` slot. `null` for non-DR readouts, the
   *  Curve Class option, and the *primary* intercept of a DR readout. */
  intercept_key: InterceptKey | null;
}

const CURVE_CLASS_OPTION: HitCriterionOption = {
  id: "Curve Class",
  label: "Curve Class",
  readout_name: "Curve Class",
  intercept_key: null,
};

function interceptOptionId(readoutName: string, kind: string, level: number): string {
  return `${readoutName}::${kind}::${level}`;
}

export function buildHitCriterionOptions(
  readouts: ReadoutDefinition[],
): HitCriterionOption[] {
  const out: HitCriterionOption[] = [];
  for (const rd of readouts) {
    const dr = rd.dose_response_config;
    if (dr) {
      const specs = dr.intercepts ?? [];
      if (specs.length === 0) {
        // Legacy DR readout with no declared intercepts — single implicit
        // primary at level 50; treat it as the (unkeyed) primary slot.
        out.push({
          id: rd.name,
          label: rd.name,
          readout_name: rd.name,
          intercept_key: null,
        });
        continue;
      }
      const primary = specs[0];
      for (let i = 0; i < specs.length; i++) {
        const s = specs[i];
        out.push({
          id: interceptOptionId(rd.name, s.kind, s.level),
          // Dedupe-aware: a readout named "EC50" with intercepts [EC50, EC90]
          // shows as "EC50" / "EC90" rather than "EC50 EC50" / "EC50 EC90".
          label: interceptOptionLabel(rd.name, primary, s),
          readout_name: rd.name,
          // Primary stays unkeyed so a saved rule survives a protocol relabel
          // and so legacy criteria don't grow an intercept_key just by being
          // re-saved.
          intercept_key: i === 0 ? null : { kind: s.kind, level: s.level },
        });
      }
    } else {
      out.push({
        id: rd.name,
        label: rd.name,
        readout_name: rd.name,
        intercept_key: null,
      });
    }
  }
  out.push(CURVE_CLASS_OPTION);
  return out;
}

export function optionIdForRule(
  rule: HitCriterion,
  readouts: ReadoutDefinition[],
): string {
  if (rule.intercept_key) {
    return interceptOptionId(
      rule.readout_name,
      rule.intercept_key.kind,
      rule.intercept_key.level,
    );
  }
  // No intercept_key. For a DR readout, this means "the primary intercept" —
  // map onto the first option in the readout's spec list. For non-DR readouts
  // (and Curve Class) the option id is just the readout name.
  const rd = readouts.find((r) => r.name === rule.readout_name);
  const firstSpec = rd?.dose_response_config?.intercepts?.[0];
  if (rd && firstSpec) {
    return interceptOptionId(rd.name, firstSpec.kind, firstSpec.level);
  }
  return rule.readout_name;
}
