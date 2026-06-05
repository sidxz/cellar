"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  type UmapJob,
  type UmapPicker,
  type UmapResult,
  dtoToUmapJob,
  dtoToUmapResult,
} from "@/features/sar-analysis/types";
import type { UmapJobDto, UmapResultDto } from "@/shared/lib/api/model";

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
  startFn?: (input: {
    collection_id?: string;
    molecule_ids?: string[];
    picker: string;
    n?: number | null;
    threshold?: number | null;
  }) => Promise<{ result: UmapResultDto | null; job: UmapJobDto | null }>;
  /** Override for tests — defaults to the orval-generated GET. The route
   *  returns `StartUmapClusterResponse` ({result, job}), not a flat UmapJobDto. */
  pollFn?: (jobId: string) => Promise<{ result: UmapResultDto | null; job: UmapJobDto | null }>;
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

async function defaultStartFn(input: {
  collection_id?: string;
  molecule_ids?: string[];
  picker: string;
  n?: number | null;
  threshold?: number | null;
}): Promise<{ result: UmapResultDto | null; job: UmapJobDto | null }> {
  const { startUmapClusterApiV1SarUmapClusterPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return startUmapClusterApiV1SarUmapClusterPost(input as any) as any;
}

async function defaultPollFn(
  jobId: string,
): Promise<{ result: UmapResultDto | null; job: UmapJobDto | null }> {
  const { getUmapClusterJobApiV1SarUmapClusterJobsJobIdGet } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return getUmapClusterJobApiV1SarUmapClusterJobsJobIdGet(jobId) as any;
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
  // object every render makes the polling effect below — which depends on
  // `asyncJob` — re-run on EVERY render, firing a new poll each time. That was
  // a runaway request storm (thousands of polls of the same job id). With the
  // DTO stable, this reference is stable and the effect runs once per job.
  const asyncJob: UmapJob | null = useMemo(
    () => (asyncJobDto ? dtoToUmapJob(asyncJobDto) : null),
    [asyncJobDto],
  );

  // Polling state (only used when the initial response returned a job, not a result).
  const [polledResult, setPolledResult] = useState<UmapResult | null>(null);
  const [polledJob, setPolledJob] = useState<UmapJob | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [_cancelRequested, setCancelRequested] = useState(false);

  // Reset polling state whenever the query key changes (new input).
  useEffect(() => {
    setPolledResult(null);
    setPolledJob(null);
    setPollError(null);
    setCancelRequested(false);
  }, [key, picker, n, threshold]);

  // Polling loop — mirrors useScaffoldTree's manual setTimeout approach.
  useEffect(() => {
    if (!asyncJob) return;
    const terminalStatuses = new Set(["ready", "failed", "cancelled"]);
    if (terminalStatuses.has(asyncJob.status)) return;

    let cancelled = false;
    let attempts = 0;

    const tick = async () => {
      try {
        const resp = await pollFn(asyncJob.id);
        if (cancelled) return;

        // Route returns { result, job } — job carries status, result is the
        // payload once status === "ready".
        const jobDto = resp.job;
        if (!jobDto) {
          // Defensive: shouldn't happen (route always returns job), but stop
          // polling if we lose the job entry rather than spin forever.
          setPollError("Job not found");
          return;
        }
        const mappedJob = dtoToUmapJob(jobDto);
        setPolledJob(mappedJob);

        if (jobDto.status === "ready") {
          if (resp.result) setPolledResult(dtoToUmapResult(resp.result));
          return;
        }
        if (jobDto.status === "failed") {
          setPollError(jobDto.error_message ?? "UMAP cluster compute failed");
          return;
        }
        if (jobDto.status === "cancelled") {
          setPollError("UMAP cluster compute cancelled");
          return;
        }

        attempts++;
        const interval = attempts < 3 ? pollIntervalMs : pollIntervalMs * 2;
        window.setTimeout(tick, interval);
      } catch (e) {
        if (!cancelled) setPollError(String(e));
      }
    };

    tick();
    return () => {
      cancelled = true;
    };
  }, [asyncJob, pollFn, pollIntervalMs]);

  // Cancel handler.
  const cancel = () => {
    const jobId = asyncJob?.id ?? polledJob?.id;
    if (!jobId) return;
    setCancelRequested(true);
    cancelFn(jobId).catch(() => {
      // Cancel is best-effort; swallow errors.
    });
  };

  // Derive exposed state.
  const result = inlineResult ?? polledResult;
  const job = asyncJob ?? polledJob;
  const isJobPending =
    job !== null &&
    job.status !== "ready" &&
    job.status !== "failed" &&
    job.status !== "cancelled" &&
    result === null; // once we have a result, stop showing loading
  const loading = start.isPending || isJobPending;
  const error = pollError ?? (start.error as Error | null)?.message ?? null;

  return { result, job, loading, error, cancel };
}
