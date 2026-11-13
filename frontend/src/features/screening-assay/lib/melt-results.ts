/** A temperature window's results as grid rows and ΔTm-against-concentration
 *  series. Pure. */

import type { MeltWindow, StepCheck, WellType } from "../types";
import { WELL_TYPE_LABELS } from "../types";
import type { CurvePosition } from "./curve-plot";

export interface WindowRow {
  wellId: string;
  position: string;
  role: string;
  batch: string;
  concentration: number | null;
  tm: number | null;
  deltaTm: number | null;
  flags: string;
}

const FLAG_TEXT: Record<string, string> = {
  no_step_in_window: "No step in window",
  several_steps_in_window: "Several steps in window",
  no_reference_value: "No reference value",
};
const DIFFERS_TEXT = "Step count differs from the reference";

export function windowRows(
  window: MeltWindow,
  positions: CurvePosition[],
  checks: StepCheck[],
): WindowRow[] {
  const byId = new Map(positions.map((p) => [p.well_id, p]));
  const differs = new Set(
    checks.filter((c) => c.channel_key === window.channel_key).flatMap((c) => c.differs),
  );
  return window.positions.flatMap((r) => {
    const p = byId.get(r.well_id);
    if (!p) return [];
    const flags = r.flags.map((f) => FLAG_TEXT[f] ?? f);
    if (differs.has(r.well_id)) flags.push(DIFFERS_TEXT);
    return {
      wellId: r.well_id,
      position: p.label ?? p.position_label,
      role: WELL_TYPE_LABELS[p.well_type as WellType] ?? p.well_type,
      batch: p.batch_number ?? "",
      concentration: p.dose ?? null,
      tm: r.tm ?? null,
      deltaTm: r.delta_tm ?? null,
      flags: flags.join(", "),
    };
  });
}

export interface ConcentrationSeries {
  batchLabel: string;
  points: { dose: number; deltaTm: number }[];
}

/** One series per batch with at least two distinct doses above zero. */
export function concentrationSeries(
  window: MeltWindow,
  positions: CurvePosition[],
): ConcentrationSeries[] {
  const byId = new Map(positions.map((p) => [p.well_id, p]));
  const batches = new Map<string, { dose: number; deltaTm: number }[]>();
  for (const r of window.positions) {
    const p = byId.get(r.well_id);
    if (!p || r.delta_tm == null || p.dose == null || p.dose <= 0) continue;
    const key = p.batch_number ?? "No batch";
    batches.set(key, [...(batches.get(key) ?? []), { dose: p.dose, deltaTm: r.delta_tm }]);
  }
  return [...batches]
    .filter(([, pts]) => new Set(pts.map((x) => x.dose)).size >= 2)
    .map(([batchLabel, pts]) => ({ batchLabel, points: pts.sort((a, b) => a.dose - b.dose) }));
}
