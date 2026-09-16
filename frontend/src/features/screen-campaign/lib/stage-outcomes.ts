/**
 * Pure helpers over `CampaignResultResponse.stage_outcomes` — no I/O, no
 * React. `stage_outcomes` is computed server-side by `evaluate_stages` and
 * shipped on every result; the frontend only ever looks it up and tallies
 * it, never recomputes hit/miss itself.
 */

import type { CampaignResultResponse, StageOutcomeResponse } from "../types";

/** This result's outcome for the given stage, or `undefined` if the result
 *  carries no entry for it (stale fixture / stage removed mid-request). */
export function outcomeFor(
  result: CampaignResultResponse,
  stageId: string,
): StageOutcomeResponse | undefined {
  return result.stage_outcomes.find((o) => o.stage_id === stageId);
}

export interface StageTally {
  population: number;
  hit: number;
  miss: number;
  untested: number;
  pending: number;
  not_in_stage: number;
  overridden: number;
}

/** Tallies one stage's outcomes across a result set. `population` is
 *  `hit + miss + untested + pending` (every result actually evaluated
 *  against the stage's own criteria, plus a manual stage's un-triaged
 *  rows) — `not_in_stage` rows are gated out by a parent
 *  that isn't a hit and sit outside the population, per the spec's worked
 *  example. Results with no recorded outcome for this stage are skipped. */
export function tallyStage(results: CampaignResultResponse[], stageId: string): StageTally {
  const tally: StageTally = {
    population: 0,
    hit: 0,
    miss: 0,
    untested: 0,
    pending: 0,
    not_in_stage: 0,
    overridden: 0,
  };
  for (const result of results) {
    const outcome = outcomeFor(result, stageId);
    if (!outcome) continue;
    if (outcome.outcome === "hit") tally.hit++;
    else if (outcome.outcome === "miss") tally.miss++;
    else if (outcome.outcome === "untested") tally.untested++;
    else if (outcome.outcome === "pending") tally.pending++;
    else if (outcome.outcome === "not_in_stage") tally.not_in_stage++;
    if (outcome.overridden) tally.overridden++;
  }
  tally.population = tally.hit + tally.miss + tally.untested + tally.pending;
  return tally;
}
