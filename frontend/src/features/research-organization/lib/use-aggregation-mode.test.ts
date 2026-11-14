import { describe, expect, it } from "vitest";
import type { RunScope, SearchCriterion } from "../types";
import {
  AGGREGATION_MODES,
  aggregationModeFromUrl,
  aggregationModeToUrl,
  aggregationModeToWire,
  computeScopeForcesSingleRun,
  isAggregationMode,
  wireToAggregationMode,
} from "./use-aggregation-mode";

describe("AggregationMode helpers", () => {
  it("default mode is latest", () => {
    expect(aggregationModeFromUrl(null)).toBe("latest");
    expect(aggregationModeFromUrl("")).toBe("latest");
    expect(aggregationModeFromUrl("garbage")).toBe("latest");
  });

  it("URL <-> mode round-trip", () => {
    for (const mode of AGGREGATION_MODES) {
      expect(aggregationModeFromUrl(aggregationModeToUrl(mode))).toBe(mode);
    }
  });

  it("wire <-> mode round-trip", () => {
    expect(wireToAggregationMode("latest_run")).toBe("latest");
    expect(wireToAggregationMode("geometric_mean")).toBe("gmean");
    expect(wireToAggregationMode("mean_across_runs")).toBe("mean");
    expect(wireToAggregationMode("best_r_squared")).toBe("best_r2");

    expect(aggregationModeToWire("latest")).toBe("latest_run");
    expect(aggregationModeToWire("gmean")).toBe("geometric_mean");
    expect(aggregationModeToWire("mean")).toBe("mean_across_runs");
    expect(aggregationModeToWire("best_r2")).toBe("best_r_squared");
  });

  it("isAggregationMode narrows correctly", () => {
    expect(isAggregationMode("latest")).toBe(true);
    expect(isAggregationMode("gmean")).toBe(true);
    expect(isAggregationMode("nonsense")).toBe(false);
  });
});

// ─── computeScopeForcesSingleRun ───────────────────────────────────────────
// Trigger condition for the toolbar "Summarize:" dropdown being replaced by
// the static "Single run per compound" label. Returns true iff at least one
// activity criterion exists AND every one of them is unambiguously narrowed
// to one run (mode `latest`, or mode `specific` with exactly one id between
// the multi-shape `run_ids[]` and the legacy single-shape `run_id`).
describe("computeScopeForcesSingleRun", () => {
  const activity = (run_scope: RunScope | undefined): SearchCriterion =>
    ({
      type: "activity",
      protocol_id: "p1",
      run_scope,
    }) as SearchCriterion;

  it("returns false when criteria list is empty", () => {
    expect(computeScopeForcesSingleRun([])).toBe(false);
  });

  it("returns false when there are no activity criteria (structure-only search)", () => {
    const structOnly: SearchCriterion[] = [
      {
        type: "structure",
        kind: "substructure",
        smiles_or_smarts: "c1ccccc1",
      } as SearchCriterion,
    ];
    expect(computeScopeForcesSingleRun(structOnly)).toBe(false);
  });

  it("returns true for a single activity criterion with run_scope.mode='latest'", () => {
    expect(computeScopeForcesSingleRun([activity({ mode: "latest" })])).toBe(true);
  });

  it("returns true for run_scope.mode='specific' with exactly one run_id (multi-shape)", () => {
    expect(
      computeScopeForcesSingleRun([
        activity({ mode: "specific", run_ids: ["00000000-0000-0000-0000-000000000001"] }),
      ]),
    ).toBe(true);
  });

  it("returns true for the legacy single-shape (run_id set, run_ids absent)", () => {
    expect(
      computeScopeForcesSingleRun([
        activity({ mode: "specific", run_id: "00000000-0000-0000-0000-000000000001" }),
      ]),
    ).toBe(true);
  });

  it("returns false for run_scope.mode='specific' with multiple run_ids", () => {
    expect(
      computeScopeForcesSingleRun([
        activity({
          mode: "specific",
          run_ids: ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"],
        }),
      ]),
    ).toBe(false);
  });

  it("returns false for run_scope.mode='specific' with empty run_ids (invalid state still keeps toolbar live)", () => {
    expect(computeScopeForcesSingleRun([activity({ mode: "specific", run_ids: [] })])).toBe(false);
  });

  it("returns false for range scopes — past_n_days and date_range can yield multiple in-scope runs", () => {
    expect(computeScopeForcesSingleRun([activity({ mode: "past_n_days", days: 30 })])).toBe(false);
    expect(
      computeScopeForcesSingleRun([
        activity({ mode: "date_range", date_from: "2026-01-01", date_to: "2026-05-01" }),
      ]),
    ).toBe(false);
  });

  it("returns false for the explicit 'any' / 'all' modes", () => {
    expect(computeScopeForcesSingleRun([activity({ mode: "any" })])).toBe(false);
    expect(computeScopeForcesSingleRun([activity({ mode: "all" })])).toBe(false);
  });

  it("returns false when run_scope is omitted (unset === any)", () => {
    expect(computeScopeForcesSingleRun([activity(undefined)])).toBe(false);
  });

  it("returns false when one criterion is narrow and another is open (mixed)", () => {
    expect(
      computeScopeForcesSingleRun([activity({ mode: "latest" }), activity({ mode: "any" })]),
    ).toBe(false);
  });

  it("returns true when every activity criterion is single-run-scoped", () => {
    expect(
      computeScopeForcesSingleRun([
        activity({ mode: "latest" }),
        activity({ mode: "specific", run_ids: ["00000000-0000-0000-0000-000000000003"] }),
      ]),
    ).toBe(true);
  });

  it("recurses into group criteria to find activity criteria nested inside", () => {
    const grouped: SearchCriterion[] = [
      {
        type: "group",
        logic: "and",
        criteria: [
          activity({ mode: "latest" }),
          activity({ mode: "specific", run_ids: ["00000000-0000-0000-0000-000000000003"] }),
        ],
      } as SearchCriterion,
    ];
    expect(computeScopeForcesSingleRun(grouped)).toBe(true);
  });

  it("returns false when a group contains a non-narrow activity criterion", () => {
    const grouped: SearchCriterion[] = [
      {
        type: "group",
        logic: "or",
        criteria: [activity({ mode: "latest" }), activity({ mode: "any" })],
      } as SearchCriterion,
    ];
    expect(computeScopeForcesSingleRun(grouped)).toBe(false);
  });
});
