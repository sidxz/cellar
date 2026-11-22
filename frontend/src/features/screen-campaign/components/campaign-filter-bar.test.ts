import { describe, expect, it } from "vitest";

import { tallyStage } from "../lib/stage-outcomes";
import type {
  CampaignMeasurementResponse,
  CampaignResultResponse,
  StageOutcomeResponse,
} from "../types";
import {
  type CampaignFilters,
  type MeasurementFilter,
  type SearchableMolecule,
  emptyFilters,
  filtersActive,
  measurementPasses,
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
    qc_verdict: "not_tested",
    holds_result: true,
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
const pendingRow = makeResult({
  id: "r-pending",
  stage_outcomes: [makeOutcome({ outcome: "pending" })],
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
  pendingRow,
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

  // A manual stage's rows sit at "pending" until triaged; the tab-change
  // default turns the chip on so they aren't invisible on arrival.
  it("passes a pending row when the Pending chip is on, and hides it when off", () => {
    const on = withFilters({ stageOutcomes: new Set(["hit", "miss", "untested", "pending"]) });
    expect(passing(on, STAGE)).toContain("r-pending");

    const off = withFilters({ stageOutcomes: new Set(["hit", "miss", "untested"]) });
    expect(passing(off, STAGE)).not.toContain("r-pending");
  });

  it("narrows to pending rows alone when only that chip is on", () => {
    expect(passing(withFilters({ stageOutcomes: new Set(["pending"]) }), STAGE)).toEqual([
      "r-pending",
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
      population: 6,
      hit: 2,
      miss: 2,
      untested: 1,
      pending: 1,
      not_in_stage: 1,
      overridden: 1,
    });
  });
});

describe("rowPassesFilters — search", () => {
  const row = { id: "r", molecule_id: "mol-1", measurements: [], stage_outcomes: [] };
  const molecules = new Map<string, SearchableMolecule>([
    [
      "mol-1",
      {
        registration_number: "CC-027709",
        name: "Quinmide",
        identifiers: [
          { identifier: "SACC-0027901", identifier_type: "supplier" },
          { identifier: "41134477", identifier_type: "cdd_molecule_id" },
        ],
      } as unknown as SearchableMolecule,
    ],
  ]);
  const search = (text: string) => ({ ...emptyFilters(), search: text });

  it("finds a compound by ID, name or any identifier, ignoring case", () => {
    for (const text of ["cc-0277", "QUINMIDE", "sacc-002", "41134477"]) {
      expect(rowPassesFilters(row, search(text), null, molecules)).toBe(true);
    }
    expect(rowPassesFilters(row, search("CC-0999"), null, molecules)).toBe(false);
  });

  it("matches nothing while the compounds are unknown, so no bulk gesture reaches a hidden row", () => {
    expect(rowPassesFilters(row, search("CC"), null)).toBe(false);
    expect(rowPassesFilters(row, search("CC"), null, new Map())).toBe(false);
  });

  it("counts as an active filter", () => {
    expect(filtersActive(search("CC"), null)).toBe(true);
  });
});

describe("measurementPasses", () => {
  const f = (over: Partial<MeasurementFilter>): MeasurementFilter => ({
    channelId: "ch-1",
    minimum: null,
    maximum: null,
    unit: "µM",
    qc: "any",
    ...over,
  });

  it("holds a range inclusively, in the filter's unit (uM and µM alike)", () => {
    expect(measurementPasses(makeMeasurement({ value: 5 }), f({ maximum: 5 }))).toBe(true);
    expect(measurementPasses(makeMeasurement({ value: 5 }), f({ minimum: 5 }))).toBe(true);
    expect(measurementPasses(makeMeasurement({ value: 5.1 }), f({ maximum: 5 }))).toBe(false);
    expect(measurementPasses(makeMeasurement({ value: 1, unit: "nM" }), f({ maximum: 5 }))).toBe(
      false,
    );
  });

  it("lets an unknown unit (-) through, as the server does", () => {
    expect(measurementPasses(makeMeasurement({ value: 3, unit: "-" }), f({ maximum: 5 }))).toBe(
      true,
    );
  });

  it("never puts a limit, ND or excluded value in a range", () => {
    for (const value_qualifier of ["<", ">", "nd", "excluded"]) {
      expect(
        measurementPasses(makeMeasurement({ value: 1, value_qualifier }), f({ maximum: 5 })),
      ).toBe(false);
    }
  });

  it("matches a QC state; not tested only where there is a result to check", () => {
    const verified = makeMeasurement({ qc_verdict: "verified" });
    expect(measurementPasses(verified, f({ qc: "verified" }))).toBe(true);
    expect(measurementPasses(verified, f({ qc: "failed" }))).toBe(false);
    expect(measurementPasses(makeMeasurement(), f({ qc: "not_tested" }))).toBe(true);
    expect(
      measurementPasses(makeMeasurement({ holds_result: false }), f({ qc: "not_tested" })),
    ).toBe(false);
  });

  it("fails a row with no value for the readout", () => {
    expect(measurementPasses(undefined, f({ qc: "any" }))).toBe(false);
  });

  it("needs every condition on the row to hold", () => {
    const row = {
      id: "r",
      molecule_id: "mol-1",
      measurements: [
        makeMeasurement({ value: 2 }),
        makeMeasurement({ channel_id: "ch-2", value: 9 }),
      ],
      stage_outcomes: [],
    };
    const both = (max2: number) => ({
      ...emptyFilters(),
      measurements: [f({ maximum: 5 }), f({ channelId: "ch-2", maximum: max2 })],
    });
    expect(rowPassesFilters(row, both(10), null)).toBe(true);
    expect(rowPassesFilters(row, both(8), null)).toBe(false);
  });
});
