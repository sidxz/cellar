import { describe, expect, it } from "vitest";
import type { CampaignResultResponse, StageOutcomeResponse } from "../types";
import { outcomeFor, tallyStage } from "./stage-outcomes";

const STAGE_A = "stage-a";
const STAGE_B = "stage-b";

function makeOutcome(overrides: Partial<StageOutcomeResponse>): StageOutcomeResponse {
  return {
    stage_id: STAGE_A,
    outcome: "hit",
    overridden: false,
    checks: [],
    ...overrides,
  };
}

function makeResult(overrides: Partial<CampaignResultResponse>): CampaignResultResponse {
  return {
    id: "result-default",
    molecule_id: "mol-default",
    measurements: [],
    stage_outcomes: [],
    ...overrides,
  };
}

// Three results against STAGE_A: a plain hit, a miss the chemist overrode
// (forced back to a miss with a reason — override still counts as
// overridden even when it agrees with the computed outcome), and one gated
// out by its parent (not_in_stage). A fourth outcome on an unrelated stage
// makes sure tallyStage only counts the stage it's asked about.
const hitResult = makeResult({
  id: "r-hit",
  stage_outcomes: [makeOutcome({ outcome: "hit" })],
});
const missResult = makeResult({
  id: "r-miss",
  stage_outcomes: [
    makeOutcome({ outcome: "miss", overridden: true, override_reason: "Confirmed on retest" }),
  ],
});
const pendingResult = makeResult({
  id: "r-pending",
  stage_outcomes: [makeOutcome({ outcome: "pending" })],
});
const notInStageResult = makeResult({
  id: "r-not-in-stage",
  stage_outcomes: [
    makeOutcome({ outcome: "not_in_stage", checks: [] }),
    makeOutcome({ stage_id: STAGE_B, outcome: "hit" }),
  ],
});

const results = [hitResult, missResult, pendingResult, notInStageResult];

describe("outcomeFor", () => {
  it("finds the result's outcome entry for the given stage", () => {
    expect(outcomeFor(hitResult, STAGE_A)?.outcome).toBe("hit");
    expect(outcomeFor(notInStageResult, STAGE_B)?.outcome).toBe("hit");
  });

  it("returns undefined when the result has no entry for that stage", () => {
    expect(outcomeFor(hitResult, STAGE_B)).toBeUndefined();
  });
});

describe("tallyStage", () => {
  it("tallies hit/miss/untested/pending/not_in_stage/overridden for one stage", () => {
    expect(tallyStage(results, STAGE_A)).toEqual({
      population: 3,
      hit: 1,
      miss: 1,
      untested: 0,
      pending: 1,
      not_in_stage: 1,
      overridden: 1,
    });
  });

  // A manual stage's un-triaged rows are still part of the funnel it was
  // drawn from — the tile reads "1 of 3", not "1 of 2".
  it("counts pending rows inside the population", () => {
    const manualOnly = [pendingResult, pendingResult, hitResult];
    const tally = tallyStage(manualOnly, STAGE_A);
    expect(tally.pending).toBe(2);
    expect(tally.population).toBe(3);
  });

  it("only counts the requested stage", () => {
    expect(tallyStage(results, STAGE_B)).toEqual({
      population: 1,
      hit: 1,
      miss: 0,
      untested: 0,
      pending: 0,
      not_in_stage: 0,
      overridden: 0,
    });
  });

  it("returns all zeros for a stage with no recorded outcomes", () => {
    expect(tallyStage(results, "stage-unknown")).toEqual({
      population: 0,
      hit: 0,
      miss: 0,
      untested: 0,
      pending: 0,
      not_in_stage: 0,
      overridden: 0,
    });
  });
});
