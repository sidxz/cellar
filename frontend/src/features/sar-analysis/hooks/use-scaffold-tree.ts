import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type {
  ScaffoldTreeJob,
  ScaffoldTreeResult,
  StartScaffoldTreeResponse,
} from "../types/scaffold-tree";

/**
 * Either ``moleculeIds`` (an explicit list — for ad-hoc sets) or
 * ``collectionId`` (server-side expansion to all members of a saved
 * collection — bypasses the search endpoint's 200-row pagination cap so
 * the scaffold tree always sees every member). Exactly one must be set.
 */
export type UseScaffoldTreeParams = {
  moleculeIds?: string[];
  collectionId?: string;
  /** Override for tests — defaults to the orval-generated POST. */
  startFn?: (input: {
    molecule_ids?: string[];
    collection_id?: string;
  }) => Promise<StartScaffoldTreeResponse>;
  /** Override for tests — defaults to the orval-generated GET. */
  pollFn?: (job_id: string) => Promise<ScaffoldTreeJob>;
  pollIntervalMs?: number;
  enabled?: boolean;
};

export type UseScaffoldTreeReturn = {
  tree: ScaffoldTreeResult | null;
  jobId: string | null;
  isStarting: boolean;
  isPolling: boolean;
  error: Error | null;
};

const DEFAULT_POLL_MS = 1500;

function sortedKey(ids: string[]): string {
  return [...ids].sort().join(",");
}

export function useScaffoldTree(params: UseScaffoldTreeParams): UseScaffoldTreeReturn {
  const {
    moleculeIds,
    collectionId,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    pollIntervalMs = DEFAULT_POLL_MS,
    enabled = true,
  } = params;

  // Query key prefers the (stable) collectionId when available — otherwise
  // a sorted hash of explicit mol ids.
  const key = useMemo(
    () =>
      collectionId
        ? `coll:${collectionId}`
        : `ids:${sortedKey(moleculeIds ?? [])}`,
    [collectionId, moleculeIds],
  );

  // Either path must be enabled, but not both (the BE rejects {neither, both}).
  const queryEnabled =
    enabled &&
    (collectionId !== undefined || (moleculeIds ?? []).length > 0);

  const start = useQuery({
    queryKey: ["scaffold-tree", "start", key],
    queryFn: () =>
      startFn(
        collectionId
          ? { collection_id: collectionId }
          : { molecule_ids: moleculeIds ?? [] },
      ),
    enabled: queryEnabled,
    staleTime: 5 * 60_000,
  });

  const inlineTree = start.data?.tree ?? null;
  const job = start.data?.job ?? null;

  const [jobTreeResult, setJobTreeResult] = useState<ScaffoldTreeResult | null>(null);
  const [jobError, setJobError] = useState<Error | null>(null);

  useEffect(() => {
    if (!job) return;
    if (job.status === "ready" || job.status === "failed" || job.status === "cancelled") {
      return;
    }
    let cancelled = false;
    let attempts = 0;
    const tick = async () => {
      try {
        const status = await pollFn(job.id);
        if (cancelled) return;
        if (status.status === "ready" && status.tree) {
          setJobTreeResult(status.tree);
          return;
        }
        if (status.status === "failed") {
          setJobError(new Error(status.error_message ?? "scaffold tree compute failed"));
          return;
        }
        if (status.status === "cancelled") {
          setJobError(new Error("scaffold tree compute cancelled"));
          return;
        }
        attempts++;
        const interval = attempts < 3 ? pollIntervalMs : pollIntervalMs * 2;
        window.setTimeout(tick, interval);
      } catch (e) {
        if (!cancelled) setJobError(e as Error);
      }
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [job, pollFn, pollIntervalMs]);

  return {
    tree: inlineTree ?? jobTreeResult,
    jobId: job?.id ?? null,
    isStarting: start.isPending,
    isPolling: job != null && jobTreeResult === null && jobError === null,
    error: jobError ?? (start.error as Error | null) ?? null,
  };
}

async function defaultStartFn(input: {
  molecule_ids?: string[];
  collection_id?: string;
}): Promise<StartScaffoldTreeResponse> {
  const { startScaffoldTreeApiV1ScaffoldTreePost } = await import(
    "@/shared/lib/api/scaffold-tree/scaffold-tree"
  );
  const res = await startScaffoldTreeApiV1ScaffoldTreePost(input);
  return res as unknown as StartScaffoldTreeResponse;
}

async function defaultPollFn(job_id: string): Promise<ScaffoldTreeJob> {
  const { getScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdGet } = await import(
    "@/shared/lib/api/scaffold-tree/scaffold-tree"
  );
  const res = await getScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdGet(job_id);
  return res as unknown as ScaffoldTreeJob;
}
