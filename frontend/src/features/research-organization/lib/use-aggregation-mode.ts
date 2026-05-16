"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import type { SelectionRule } from "@/shared/lib/api/model";

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
  _listeners.forEach((l) => l());
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
