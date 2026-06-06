"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  type UmapJob,
  type UmapPicker,
  type UmapResult,
  dtoToUmapJob,
  dtoToUmapResult,
} from "@/features/sar-analysis/types";
import { useJobPoll } from "@/shared/hooks/use-job-poll";
import type { StartUmapClusterBody, StartUmapClusterResponse } from "@/shared/lib/api/model";

// ---------------------------------------------------------------------------
// Input / output types
// ---------------------------------------------------------------------------

export interface UseUmapClusterInput {
  collectionId?: string;
  moleculeIds?: string[];
  picker: UmapPicker;
  n?: number;
  threshold?: number;
  enabled: boolean;
  /** Override for tests — defaults to the orval-generated POST. */
  startFn?: (input: StartUmapClusterBody) => Promise<StartUmapClusterResponse>;
  /** Override for tests — defaults to the orval-generated GET. The route
   *  returns `StartUmapClusterResponse` ({result, job}), not a flat UmapJobDto. */
  pollFn?: (jobId: string) => Promise<StartUmapClusterResponse>;
  /** Override for tests — defaults to the orval-generated cancel POST. */
  cancelFn?: (jobId: string) => Promise<void>;
  pollIntervalMs?: number;
}

export interface UseUmapClusterReturn {
  result: UmapResult | null;
  job: UmapJob | null;
  loading: boolean;
  error: string | null;
  cancel: () => void;
}

// ---------------------------------------------------------------------------
// Defaults (lazy-imported orval functions to avoid circular dep in tests)
// ---------------------------------------------------------------------------

async function defaultStartFn(input: StartUmapClusterBody): Promise<StartUmapClusterResponse> {
  const { startUmapClusterApiV1SarUmapClusterPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return startUmapClusterApiV1SarUmapClusterPost(input);
}

async function defaultPollFn(jobId: string): Promise<StartUmapClusterResponse> {
  const { getUmapClusterJobApiV1SarUmapClusterJobsJobIdGet } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return getUmapClusterJobApiV1SarUmapClusterJobsJobIdGet(jobId);
}

async function defaultCancelFn(jobId: string): Promise<void> {
  const { cancelUmapClusterJobApiV1SarUmapClusterJobsJobIdCancelPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  await cancelUmapClusterJobApiV1SarUmapClusterJobsJobIdCancelPost(jobId);
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const DEFAULT_POLL_MS = 1500;

function sortedKey(ids: string[]): string {
  return [...ids].sort().join(",");
}

export function useUmapCluster(input: UseUmapClusterInput): UseUmapClusterReturn {
  const {
    collectionId,
    moleculeIds,
    picker,
    n,
    threshold,
    enabled,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    cancelFn = defaultCancelFn,
    pollIntervalMs = DEFAULT_POLL_MS,
  } = input;

  // Stable cache key — prefer collectionId, fall back to sorted mol-ids hash.
  const key = useMemo(
    () => (collectionId ? `coll:${collectionId}` : `ids:${sortedKey(moleculeIds ?? [])}`),
    [collectionId, moleculeIds],
  );

  // Only enable when there is something to fetch.
  const queryEnabled = enabled && (collectionId !== undefined || (moleculeIds ?? []).length > 0);

  // Start query — fire the POST and cache the response.
  const start = useQuery({
    queryKey: ["umap-cluster", "start", key, picker, n, threshold],
    queryFn: () =>
      startFn({
        collection_id: collectionId,
        molecule_ids: moleculeIds,
        picker,
        n: n ?? null,
        threshold: threshold ?? null,
      }),
    enabled: queryEnabled,
    staleTime: 5 * 60_000,
  });

  const inlineResult: UmapResult | null = start.data?.result
    ? dtoToUmapResult(start.data.result)
    : null;

  const asyncJobDto = start.data?.job ?? null;
  // MUST be memoized on the (stable, React-Query-cached) DTO. Deriving a fresh
  // object every render would invalidate the poll query's enabled/key inputs
  // and re-fire the poll on EVERY render — a runaway request storm (thousands
  // of polls of the same job id). With the DTO stable, this reference is stable
  // and the poll runs once per job.
  const asyncJob: UmapJob | null = useMemo(
    () => (asyncJobDto ? dtoToUmapJob(asyncJobDto) : null),
    [asyncJobDto],
  );

  // Poll the job until terminal. The polled result/error live in the query
  // cache (not component state). The route returns { result, job } — the job
  // carries status, the result is the payload once status === "ready".
  const {
    result: polledResult,
    error: pollError,
    isPolling,
  } = useJobPoll<StartUmapClusterResponse, UmapResult>({
    job: asyncJob,
    pollFn,
    getStatus: (resp) => resp.job?.status,
    getResult: (resp) =>
      resp.job?.status === "ready" && resp.result ? dtoToUmapResult(resp.result) : null,
    getError: (resp) => {
      // Defensive: the route always returns a job; stop rather than spin if it
      // ever goes missing.
      if (!resp.job) return "Job not found";
      if (resp.job.status === "failed")
        return resp.job.error_message ?? "UMAP cluster compute failed";
      if (resp.job.status === "cancelled") return "UMAP cluster compute cancelled";
      return null;
    },
    pollIntervalMs,
    queryKey: "umap-cluster-poll",
  });

  // Cancel handler — best-effort fire-and-forget.
  const cancel = () => {
    const jobId = asyncJob?.id;
    if (!jobId) return;
    cancelFn(jobId).catch(() => {
      // Cancel is best-effort; swallow errors.
    });
  };

  // Derive exposed state.
  const result = inlineResult ?? polledResult;
  const job = asyncJob;
  const loading = start.isPending || (isPolling && result === null);
  const error = pollError ?? (start.error as Error | null)?.message ?? null;

  return { result, job, loading, error, cancel };
}
