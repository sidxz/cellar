import { describe, expect, it } from "vitest";

import { tallyStage } from "../lib/stage-outcomes";
import type {
  CampaignMeasurementResponse,
  CampaignResultResponse,
  StageOutcomeResponse,
} from "../types";
import {
  type CampaignFilters,
  emptyFilters,
  filtersActive,
  rowPassesFilters,
} from "./campaign-filter-bar";

const STAGE = "stage-confirmed";
const OTHER_STAGE = "stage-screening";

function makeOutcome(overrides: Partial<StageOutcomeResponse> = {}): StageOutcomeResponse {
  return { stage_id: STAGE, outcome: "hit", overridden: false, checks: [], ...overrides };
}

function makeMeasurement(
  overrides: Partial<CampaignMeasurementResponse> = {},
): CampaignMeasurementResponse {
  return {
    id: "m-1",
    channel_id: "ch-1",
    value: 1,
    value_qualifier: "=",
    unit: "uM",
    is_manual_override: false,
    protocol_name_snapshot: "NadD-Sumo HTS",
    protocol_version_snapshot: 1,
    ...overrides,
  };
}

function makeResult(overrides: Partial<CampaignResultResponse> = {}): CampaignResultResponse {
  return {
    id: "r-default",
    molecule_id: "mol-default",
    measurements: [],
    stage_outcomes: [],
    ...overrides,
  };
}

function withFilters(overrides: Partial<CampaignFilters> = {}): CampaignFilters {
  return { ...emptyFilters(), ...overrides };
}

// One result per outcome, plus a cell-overridden one and a stage-overridden
// one, so every branch of rowPassesFilters has a row that exercises it.
const hitRow = makeResult({ id: "r-hit", stage_outcomes: [makeOutcome({ outcome: "hit" })] });
const missRow = makeResult({ id: "r-miss", stage_outcomes: [makeOutcome({ outcome: "miss" })] });
const untestedRow = makeResult({
  id: "r-untested",
  stage_outcomes: [makeOutcome({ outcome: "untested" })],
});
const gatedRow = makeResult({
  id: "r-gated",
  stage_outcomes: [makeOutcome({ outcome: "not_in_stage" })],
});
const cellOverrideRow = makeResult({
  id: "r-cell-override",
  measurements: [makeMeasurement({ is_manual_override: true })],
  stage_outcomes: [makeOutcome({ outcome: "miss" })],
});
const stageOverrideRow = makeResult({
  id: "r-stage-override",
  stage_outcomes: [
    makeOutcome({ outcome: "hit", overridden: true, override_reason: "Confirmed on retest" }),
  ],
});
// Carries no entry for STAGE at all — treated as not_in_stage.
const otherStageRow = makeResult({
  id: "r-other-stage",
  stage_outcomes: [makeOutcome({ stage_id: OTHER_STAGE, outcome: "hit" })],
});

const allRows = [
  hitRow,
  missRow,
  untestedRow,
  gatedRow,
  cellOverrideRow,
  stageOverrideRow,
  otherStageRow,
];

function passing(filters: CampaignFilters, selectedStageId: string | null): string[] {
  return allRows.filter((r) => rowPassesFilters(r, filters, selectedStageId)).map((r) => r.id);
}

describe("filtersActive", () => {
  it("is false for the empty filter set", () => {
    expect(filtersActive(emptyFilters(), STAGE)).toBe(false);
    expect(filtersActive(emptyFilters(), null)).toBe(false);
  });

  it("only counts stage outcomes when a stage is selected", () => {
    const f = withFilters({ stageOutcomes: new Set(["hit"]) });
    expect(filtersActive(f, STAGE)).toBe(true);
    expect(filtersActive(f, null)).toBe(false);
  });

  it("counts the overridden toggle regardless of stage", () => {
    expect(filtersActive(withFilters({ overriddenOnly: true }), null)).toBe(true);
    expect(filtersActive(withFilters({ overriddenOnly: true }), STAGE)).toBe(true);
  });
});

describe("rowPassesFilters — stage outcomes", () => {
  it("shows the stage population and hides gated rows (the tab-change default)", () => {
    const f = withFilters({ stageOutcomes: new Set(["hit", "miss", "untested"]) });
    expect(passing(f, STAGE)).toEqual([
      "r-hit",
      "r-miss",
      "r-untested",
      "r-cell-override",
      "r-stage-override",
    ]);
  });

  it("treats a result with no outcome for the stage as not_in_stage", () => {
    expect(passing(withFilters({ stageOutcomes: new Set(["not_in_stage"]) }), STAGE)).toEqual([
      "r-gated",
      "r-other-stage",
    ]);
  });

  it("ignores stage outcomes entirely when no stage is selected", () => {
    expect(passing(withFilters({ stageOutcomes: new Set(["hit"]) }), null)).toEqual(
      allRows.map((r) => r.id),
    );
  });

  it("narrows to one outcome when a single chip is on", () => {
    expect(passing(withFilters({ stageOutcomes: new Set(["hit"]) }), STAGE)).toEqual([
      "r-hit",
      "r-stage-override",
    ]);
  });

  it("intersects with the overridden toggle", () => {
    const f = withFilters({
      overriddenOnly: true,
      stageOutcomes: new Set(["miss"]),
    });
    expect(passing(f, STAGE)).toEqual(["r-cell-override"]);
  });
});

describe("rowPassesFilters — overridden", () => {
  it("matches cell overrides only when no stage is selected", () => {
    expect(passing(withFilters({ overriddenOnly: true }), null)).toEqual(["r-cell-override"]);
  });

  it("also matches an override on the selected stage", () => {
    expect(passing(withFilters({ overriddenOnly: true }), STAGE)).toEqual([
      "r-cell-override",
      "r-stage-override",
    ]);
  });

  it("does not match an override recorded on a different stage", () => {
    expect(passing(withFilters({ overriddenOnly: true }), OTHER_STAGE)).toEqual([
      "r-cell-override",
    ]);
  });
});

describe("chip counts", () => {
  it("tallies the chips the filter bar renders for the selected stage", () => {
    expect(tallyStage(allRows, STAGE)).toEqual({
      population: 5,
      hit: 2,
      miss: 2,
      untested: 1,
      not_in_stage: 1,
      overridden: 1,
    });
  });
});
