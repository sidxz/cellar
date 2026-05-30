"use client";

import { useCallback, useMemo, useState } from "react";

import { type UseUmapClusterInput, useUmapCluster } from "./use-umap-cluster";

export interface UseRegionDiversePickOptions {
  /** Test override forwarded to useUmapCluster. */
  startFn?: UseUmapClusterInput["startFn"];
  /** Test override forwarded to useUmapCluster. */
  pollFn?: UseUmapClusterInput["pollFn"];
}

export interface RegionDiversePick {
  /** Representative ids of the last pick. Empty while loading or idle. */
  pickedIds: Set<string>;
  loading: boolean;
  error: string | null;
  /** True once pick() has been called and not reset. */
  active: boolean;
  /** Run MaxMin over `ids`, selecting `n` diverse representatives. */
  pick: (ids: string[], n: number) => void;
  reset: () => void;
}

/**
 * On-demand MaxMin diversity pick over a lassoed subset. Wraps useUmapCluster
 * (which handles inline + async-poll) and surfaces only the representative ids.
 * The throwaway embedding of a small lasso region is cheap; we ignore the coords.
 */
export function useRegionDiversePick(opts: UseRegionDiversePickOptions = {}): RegionDiversePick {
  const [request, setRequest] = useState<{ ids: string[]; n: number } | null>(null);

  const { result, loading, error } = useUmapCluster({
    moleculeIds: request?.ids,
    picker: "maxmin",
    n: request?.n,
    enabled: request !== null && (request?.ids.length ?? 0) > 0,
    startFn: opts.startFn,
    pollFn: opts.pollFn,
  });

  const pickedIds = useMemo(
    () => new Set((result?.representatives ?? []).map((r) => r.moleculeId)),
    [result],
  );

  const pick = useCallback((ids: string[], n: number) => setRequest({ ids, n }), []);
  const reset = useCallback(() => setRequest(null), []);

  return {
    pickedIds,
    loading: request !== null && loading,
    error,
    active: request !== null,
    pick,
    reset,
  };
}
