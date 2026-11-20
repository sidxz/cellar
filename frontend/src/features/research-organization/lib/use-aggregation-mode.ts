"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import type { SelectionRule } from "@/shared/lib/api/model";
import type { SearchCriterion } from "../types";

/** `all` ("Show all runs") is search-only: each cell lists every run, while
 *  the headline, sorting and export follow the latest run. */
export type AggregationMode = "latest" | "gmean" | "mean" | "best_r2" | "all";

/** The rules that reduce a cell to one value — what SAR colouring offers. */
export const AGGREGATION_MODES: readonly AggregationMode[] = [
  "latest",
  "gmean",
  "mean",
  "best_r2",
] as const;

/** The search grid's options: the rules plus Show all runs. */
export const SEARCH_AGGREGATION_MODES: readonly AggregationMode[] = [
  ...AGGREGATION_MODES,
  "all",
] as const;

export const AGGREGATION_LABELS: Record<AggregationMode, string> = {
  latest: "Latest run",
  gmean: "Geometric mean",
  mean: "Arithmetic mean",
  best_r2: "Highest R²",
  all: "Show all runs",
};

const URL_TO_MODE: Record<string, AggregationMode> = {
  latest: "latest",
  gmean: "gmean",
  mean: "mean",
  best_r2: "best_r2",
  all: "all",
};

const WIRE_TO_MODE: Record<string, AggregationMode> = {
  latest_run: "latest",
  geometric_mean: "gmean",
  mean_across_runs: "mean",
  best_r_squared: "best_r2",
  // Never sent to the server: only a stored search's `aggregation` holds it.
  all_runs: "all",
};

const MODE_TO_WIRE: Record<AggregationMode, SelectionRule> = {
  latest: "latest_run" as SelectionRule,
  gmean: "geometric_mean" as SelectionRule,
  mean: "mean_across_runs" as SelectionRule,
  best_r2: "best_r_squared" as SelectionRule,
  all: "latest_run" as SelectionRule,
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

/** True when each cell lists every run (the request's `list_runs`). */
export function listsRuns(mode: AggregationMode): boolean {
  return mode === "all";
}

/** The `aggregation` a saved or recent search stores inside its query: the
 *  wire rule, except Show all runs, which must reload as itself. */
export function aggregationModeToStored(mode: AggregationMode): string {
  return mode === "all" ? "all_runs" : MODE_TO_WIRE[mode];
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
  // First value: the live URL in the browser, so a control that mounts after
  // `setMode` rewrote it (the results toolbar, once a stored search's results
  // arrive) starts on that mode; Next's snapshot only knows the loaded URL.
  // On the server, the snapshot (the same URL the client hydrates with).
  const params = useSearchParams();
  const [mode, setModeState] = useState<AggregationMode>(() =>
    typeof window === "undefined"
      ? aggregationModeFromUrl(params.get("agg"))
      : readModeFromWindow(),
  );

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
