/** A run's hit rule applied to its thermal shift results. Pure.
 *
 *  The rule is the run's recorded `hit_criteria` (an attributable per-run
 *  decision). Only rules on per-position melt readouts (Tm, ΔTm of a window)
 *  can be evaluated against positions; the rest are set aside for the caller
 *  to list, so a partial evaluation is never silent. */

import type { HitCriterion, MeltingAnalysis, ReadoutDefinition } from "../types";
import type { CurvePosition } from "./curve-plot";

type PerPosition = "tm" | "delta_tm";

export interface ApplicableRule {
  rule: HitCriterion;
  window: string;
  measure: PerPosition;
}

export type Band = { kind: "outside"; low: number; high: number } | { kind: "line"; at: number };

const bounds = (v: HitCriterion["value"]): [number, number] | null =>
  Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === "number")
    ? [v[0] as number, v[1] as number]
    : null;

/** gt/lt/gte/lte, and "outside" strictly outside [low, high]. */
export function meetsRule(value: number, rule: HitCriterion): boolean {
  const t = typeof rule.value === "number" ? rule.value : null;
  switch (rule.operator) {
    case "gt":
      return t != null && value > t;
    case "gte":
      return t != null && value >= t;
    case "lt":
      return t != null && value < t;
    case "lte":
      return t != null && value <= t;
    case "not_between": {
      const b = bounds(rule.value);
      return b != null && (value < b[0] || value > b[1]);
    }
    default:
      return false;
  }
}

/** One value per batch (Max ΔTm and the like), not per position. */
export function isSeriesReadout(rd: Pick<ReadoutDefinition, "melt_config">): boolean {
  const m = rd.melt_config?.measure;
  return m != null && m !== "tm" && m !== "delta_tm";
}

/** A run may not record a rule on a series value (one number per batch; the
 *  server refuses it). Splits a rule set, such as a protocol recommendation,
 *  into what a run can take and what it cannot. */
export function runRulesOf(
  criteria: readonly HitCriterion[],
  readouts: readonly ReadoutDefinition[],
): { kept: HitCriterion[]; dropped: HitCriterion[] } {
  const series = new Set(readouts.filter(isSeriesReadout).map((rd) => rd.name));
  return {
    kept: criteria.filter((r) => !series.has(r.readout_name)),
    dropped: criteria.filter((r) => series.has(r.readout_name)),
  };
}

export function splitRunRules(
  criteria: readonly HitCriterion[],
  readouts: readonly ReadoutDefinition[],
): { applicable: ApplicableRule[]; other: HitCriterion[] } {
  const byName = new Map(readouts.map((rd) => [rd.name, rd]));
  const applicable: ApplicableRule[] = [];
  const other: HitCriterion[] = [];
  for (const rule of criteria) {
    const mc = byName.get(rule.readout_name)?.melt_config;
    if (mc && (mc.measure === "tm" || mc.measure === "delta_tm")) {
      applicable.push({ rule, window: mc.window, measure: mc.measure });
    } else {
      other.push(rule);
    }
  }
  return { applicable, other };
}

/** Sample positions meeting every applicable rule; a missing value fails its rule. */
export function hitWells(
  analysis: MeltingAnalysis,
  positions: readonly CurvePosition[],
  applicable: readonly ApplicableRule[],
): ReadonlySet<string> {
  if (applicable.length === 0) return new Set();
  const cells = new Map(
    analysis.windows.map((w) => [w.window, new Map(w.positions.map((p) => [p.well_id, p]))]),
  );
  const hits = new Set<string>();
  for (const p of positions) {
    if (p.well_type !== "sample") continue;
    const met = applicable.every(({ rule, window, measure }) => {
      const v = cells.get(window)?.get(p.well_id)?.[measure];
      return typeof v === "number" && meetsRule(v, rule);
    });
    if (met) hits.add(p.well_id);
  }
  return hits;
}

/** The band to draw on a window's ΔTm figures, from the first rule on its ΔTm. */
export function bandFor(applicable: readonly ApplicableRule[], windowName: string): Band | null {
  const r = applicable.find((a) => a.window === windowName && a.measure === "delta_tm")?.rule;
  if (!r) return null;
  if (r.operator === "not_between") {
    const b = bounds(r.value);
    return b ? { kind: "outside", low: b[0], high: b[1] } : null;
  }
  return typeof r.value === "number" ? { kind: "line", at: r.value } : null;
}
