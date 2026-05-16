import { describe, expect, it } from "vitest";
import type { RunScope, SearchCriterion } from "../types";
import {
  AGGREGATION_MODES,
  aggregationModeFromUrl,
  aggregationModeToUrl,
  aggregationModeToWire,
  collectRunScopesByProtocol,
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
    expect(wireToAggregationMode("latest_approved_run")).toBe("latest");
    expect(wireToAggregationMode("geometric_mean")).toBe("gmean");
    expect(wireToAggregationMode("mean_across_runs")).toBe("mean");
    expect(wireToAggregationMode("best_r_squared")).toBe("best_r2");

    expect(aggregationModeToWire("latest")).toBe("latest_approved_run");
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
          run_ids: [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
          ],
        }),
      ]),
    ).toBe(false);
  });

  it("returns false for run_scope.mode='specific' with empty run_ids (invalid state still keeps toolbar live)", () => {
    expect(
      computeScopeForcesSingleRun([activity({ mode: "specific", run_ids: [] })]),
    ).toBe(false);
  });

  it("returns false for range scopes — past_n_days and date_range can yield multiple in-scope runs", () => {
    expect(
      computeScopeForcesSingleRun([activity({ mode: "past_n_days", days: 30 })]),
    ).toBe(false);
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
      computeScopeForcesSingleRun([
        activity({ mode: "latest" }),
        activity({ mode: "any" }),
      ]),
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

// ─── collectRunScopesByProtocol ────────────────────────────────────────────
// Twin of the backend's `_collect_run_scopes`: walks criteria (incl. nested
// groups) and returns Map<protocol_id, RunScope> for every activity criterion
// that has a non-`any` scope. Used by the search detail drawer to filter its
// per-protocol curve list so the drawer chart agrees with the grid cell.
describe("collectRunScopesByProtocol", () => {
  const activity = (
    protocol_id: string,
    run_scope: RunScope | undefined,
  ): SearchCriterion =>
    ({
      type: "activity",
      protocol_id,
      run_scope,
    }) as SearchCriterion;

  it("returns an empty map for empty criteria", () => {
    const m = collectRunScopesByProtocol([]);
    expect(m.size).toBe(0);
  });

  it("ignores non-activity criteria", () => {
    const m = collectRunScopesByProtocol([
      {
        type: "structure",
        kind: "substructure",
        smiles_or_smarts: "c1ccccc1",
      } as SearchCriterion,
    ]);
    expect(m.size).toBe(0);
  });

  it("records a non-any scope for the criterion's protocol_id", () => {
    const m = collectRunScopesByProtocol([
      activity("p1", { mode: "specific", run_ids: ["r1"] }),
    ]);
    expect(m.get("p1")).toEqual({ mode: "specific", run_ids: ["r1"] });
  });

  it("skips activity criteria with `any` / `all` / omitted scope", () => {
    const m = collectRunScopesByProtocol([
      activity("p1", { mode: "any" }),
      activity("p2", { mode: "all" }),
      activity("p3", undefined),
    ]);
    expect(m.size).toBe(0);
  });

  it("records multiple criteria on different protocols", () => {
    const m = collectRunScopesByProtocol([
      activity("p1", { mode: "latest" }),
      activity("p2", { mode: "specific", run_ids: ["r9"] }),
    ]);
    expect(m.size).toBe(2);
    expect(m.get("p1")).toEqual({ mode: "latest" });
    expect(m.get("p2")).toEqual({ mode: "specific", run_ids: ["r9"] });
  });

  it("LAST-wins when two criteria target the same protocol", () => {
    // Matches the backend's `_collect_run_scopes` semantics: deterministic
    // (insertion order), and forces the chemist to write a tighter query
    // if they want anything else.
    const m = collectRunScopesByProtocol([
      activity("p1", { mode: "latest" }),
      activity("p1", { mode: "specific", run_ids: ["r9"] }),
    ]);
    expect(m.size).toBe(1);
    expect(m.get("p1")).toEqual({ mode: "specific", run_ids: ["r9"] });
  });

  it("walks into nested groups to find activity criteria", () => {
    const grouped: SearchCriterion[] = [
      {
        type: "group",
        logic: "and",
        criteria: [activity("p1", { mode: "latest" })],
      } as SearchCriterion,
    ];
    const m = collectRunScopesByProtocol(grouped);
    expect(m.get("p1")).toEqual({ mode: "latest" });
  });
});
