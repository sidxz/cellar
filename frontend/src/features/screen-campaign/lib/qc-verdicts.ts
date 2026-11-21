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
  if (n === 0) return "";
  return n === 1
    ? " · 1 QC verdict went back to Not tested because its value changed"
    : ` · ${n} QC verdicts went back to Not tested because their values changed`;
}

/** How many cells the call would change: the server's per-cell rule. `note` undefined is a
 *  call that names no note; null or blank names "no note". */
export function qcForecast(
  cells: CampaignMeasurementResponse[],
  verdict: Verdict,
  overwrite: boolean,
  note?: string | null,
): number {
  const named = note === undefined ? undefined : note?.trim() || null;
  return cells.filter((m) => {
    // A clear also removes a verdict from a cell that no longer holds a result.
    if (verdict === "not_tested") return m.qc_verdict !== "not_tested";
    if (!m.holds_result) return false;
    if (m.qc_verdict === verdict) {
      return overwrite && named !== undefined && named !== (m.qc_verdict_note ?? null);
    }
    return m.qc_verdict === "not_tested" || overwrite;
  }).length;
}
