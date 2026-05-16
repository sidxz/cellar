"use client";

import { useSearchParams } from "next/navigation";
import { useCallback } from "react";

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

/** Hook returning the current mode + a setter that updates the URL. */
export function useAggregationMode(): {
  mode: AggregationMode;
  setMode: (next: AggregationMode) => void;
} {
  const params = useSearchParams();
  const mode = aggregationModeFromUrl(params.get("agg"));
  const setMode = useCallback((next: AggregationMode) => {
    const url = new URL(window.location.href);
    if (next === "latest") {
      url.searchParams.delete("agg");
    } else {
      url.searchParams.set("agg", aggregationModeToUrl(next));
    }
    window.history.replaceState({}, "", url.toString());
  }, []);
  return { mode, setMode };
}
