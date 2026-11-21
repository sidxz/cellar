import type { CampaignMeasurementResponse, CampaignResponse } from "../types";

type Verdict = CampaignMeasurementResponse["qc_verdict"];

export const QC_LABEL: Record<Verdict, string> = {
  not_tested: "Not tested",
  verified: "Verified",
  failed: "Failed",
};

function verdictsById(c: CampaignResponse | undefined): Map<string, Verdict> {
  const out = new Map<string, Verdict>();
  for (const r of c?.results ?? []) {
    for (const m of r.measurements ?? []) out.set(m.id, m.qc_verdict);
  }
  return out;
}

/** Verdicts a refresh/close/add handed back to Not tested because the value changed. Cells
 *  gone from `after` were removed, not cleared. */
export function qcVerdictsCleared(
  before: CampaignResponse | undefined,
  after: CampaignResponse,
): number {
  const was = verdictsById(before);
  let n = 0;
  for (const [id, v] of verdictsById(after)) {
    const prior = was.get(id);
    if (v === "not_tested" && prior !== undefined && prior !== "not_tested") n++;
  }
  return n;
}

export function clearedVerdictsNote(n: number): string {
  return n === 0
    ? ""
    : ` · ${n} QC verdict${n === 1 ? "" : "s"} went back to Not tested because their values changed`;
}

/** How many cells the call would change (the note re-stamp case is ignored). */
export function qcForecast(
  cells: CampaignMeasurementResponse[],
  verdict: Verdict,
  overwrite: boolean,
): number {
  return cells.filter((m) => {
    if (!m.holds_result || m.qc_verdict === verdict) return false;
    if (verdict === "not_tested") return true;
    return m.qc_verdict === "not_tested" || overwrite;
  }).length;
}
