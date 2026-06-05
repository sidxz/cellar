"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import type { SelectionRule } from "@/shared/lib/api/model";
import type { SearchCriterion } from "../types";

export type AggregationMode = "latest" | "gmean" | "mean" | "best_r2";

export const AGGREGATION_MODES: readonly AggregationMode[] = [
  "latest",
  "gmean",
  "mean",
  "best_r2",
] as const;

export const AGGREGATION_LABELS: Record<AggregationMode, string> = {
  latest: "Latest run",
  gmean: "Geometric mean",
  mean: "Arithmetic mean",
  best_r2: "Best fit (R²)",
};

const URL_TO_MODE: Record<string, AggregationMode> = {
  latest: "latest",
  gmean: "gmean",
  mean: "mean",
  best_r2: "best_r2",
};

const WIRE_TO_MODE: Record<string, AggregationMode> = {
  latest_approved_run: "latest",
  geometric_mean: "gmean",
  mean_across_runs: "mean",
  best_r_squared: "best_r2",
};

const MODE_TO_WIRE: Record<AggregationMode, SelectionRule> = {
  latest: "latest_approved_run" as SelectionRule,
  gmean: "geometric_mean" as SelectionRule,
  mean: "mean_across_runs" as SelectionRule,
  best_r2: "best_r_squared" as SelectionRule,
};

export function isAggregationMode(value: string): value is AggregationMode {
  return value in URL_TO_MODE;
}

export function aggregationModeFromUrl(raw: string | null): AggregationMode {
  if (!raw) return "latest";
  return URL_TO_MODE[raw] ?? "latest";
}

export function aggregationModeToUrl(mode: AggregationMode): string {
  return mode;
}

export function wireToAggregationMode(wire: string): AggregationMode {
  return WIRE_TO_MODE[wire] ?? "latest";
}

export function aggregationModeToWire(mode: AggregationMode): SelectionRule {
  return MODE_TO_WIRE[mode];
}

/**
 * `true` iff the chemist's query has narrowed every activity criterion to a
 * single run (mode `latest`, or mode `specific` with exactly one id between
 * the multi-shape `run_ids[]` and the legacy single-shape `run_id`). In that
 * state every cell deterministically reduces to one value and the toolbar
 * "Summarize:" dropdown becomes dishonest UI — the page replaces it with a
 * static "Single run per compound" label.
 *
 * Requires at least one activity criterion to fire — a structure-only or
 * property-only search returns `false` (nothing to summarize, but also
 * nothing dishonest about leaving the toolbar live for when the chemist
 * adds an activity column next).
 *
 * Walks into `group` criteria recursively because activity criteria can
 * nest inside boolean groups.
 */
export function computeScopeForcesSingleRun(criteria: SearchCriterion[]): boolean {
  let sawActivity = false;
  let allNarrow = true;

  function walk(list: SearchCriterion[]): void {
    for (const c of list) {
      if (c.type === "activity") {
        sawActivity = true;
        if (!isSingleRunScope(c.run_scope)) {
          allNarrow = false;
        }
      } else if (c.type === "group") {
        walk(c.criteria);
      }
    }
  }

  walk(criteria);
  return sawActivity && allNarrow;
}

function isSingleRunScope(
  scope: Extract<SearchCriterion, { type: "activity" }>["run_scope"],
): boolean {
  if (!scope) return false;
  if (scope.mode === "latest") return true;
  if (scope.mode === "specific") {
    const fromList = scope.run_ids?.length ?? 0;
    const fromLegacy = scope.run_id ? 1 : 0;
    return fromList + fromLegacy === 1;
  }
  return false;
}

type ActivityRunScope = Extract<SearchCriterion, { type: "activity" }>["run_scope"];

/**
 * Walk the criteria tree and collect each activity criterion's `run_scope`
 * keyed by `protocol_id`. Twin of the backend's `_collect_run_scopes` so
 * the search detail drawer (a FE surface that fetches all curves for a
 * molecule independently of the search) can filter its per-protocol curve
 * list to the same set the grid cell saw, keeping the chart and the cell
 * value in lock-step.
 *
 * Skips criteria whose scope is `any` / `all` / omitted (those mean "no
 * filter", so they don't belong in the map). On duplicate protocol IDs the
 * LAST wins, matching the backend's deterministic insertion-order rule —
 * the chemist's tightest query is the source of truth.
 */
export function collectRunScopesByProtocol(
  criteria: SearchCriterion[],
): Map<string, NonNullable<ActivityRunScope>> {
  const out = new Map<string, NonNullable<ActivityRunScope>>();

  function walk(list: SearchCriterion[]): void {
    for (const c of list) {
      if (c.type === "activity") {
        if (!c.run_scope) continue;
        if (c.run_scope.mode === "any" || c.run_scope.mode === "all") continue;
        out.set(c.protocol_id, c.run_scope);
      } else if (c.type === "group") {
        walk(c.criteria);
      }
    }
  }

  walk(criteria);
  return out;
}

// ─── Cross-subscriber sync ──────────────────────────────────────────────────
// `window.history.replaceState` is a shallow URL rewrite that does NOT
// notify Next's `useSearchParams` consumers — a second hook caller
// (e.g. the search-page reading the same `?agg=` URL the toolbar wrote)
// would silently see a stale value. A module-level pub/sub keeps every
// `useAggregationMode()` subscriber in lock-step on the tick the URL is
// rewritten. The hook reads `window.location.search` directly inside
// the broadcast handler so it sees the just-written URL.

type Listener = () => void;
const _listeners = new Set<Listener>();
function notifySubscribers() {
  for (const l of _listeners) l();
}

function readModeFromWindow(): AggregationMode {
  if (typeof window === "undefined") return "latest";
  const params = new URLSearchParams(window.location.search);
  return aggregationModeFromUrl(params.get("agg"));
}

/** Hook returning the current mode + a setter that updates the URL. */
export function useAggregationMode(): {
  mode: AggregationMode;
  setMode: (next: AggregationMode) => void;
} {
  // Reads on first render from Next's snapshot (SSR-safe) so the initial
  // value matches the URL the page was loaded with.
  const params = useSearchParams();
  const initialMode = aggregationModeFromUrl(params.get("agg"));
  const [mode, setModeState] = useState<AggregationMode>(initialMode);

  useEffect(() => {
    const listener = () => setModeState(readModeFromWindow());
    _listeners.add(listener);
    // Also listen for back/forward navigation that flips ?agg= out of
    // band of `setMode`.
    const onPopState = () => setModeState(readModeFromWindow());
    window.addEventListener("popstate", onPopState);
    return () => {
      _listeners.delete(listener);
      window.removeEventListener("popstate", onPopState);
    };
  }, []);

  const setMode = useCallback((next: AggregationMode) => {
    const url = new URL(window.location.href);
    if (next === "latest") {
      url.searchParams.delete("agg");
    } else {
      url.searchParams.set("agg", aggregationModeToUrl(next));
    }
    window.history.replaceState({}, "", url.toString());
    notifySubscribers();
  }, []);
  return { mode, setMode };
}
