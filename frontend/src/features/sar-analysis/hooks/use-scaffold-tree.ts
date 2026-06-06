import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { useJobPoll } from "@/shared/hooks/use-job-poll";
import { STALE_TIME } from "@/shared/lib/query-defaults";
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
    () => (collectionId ? `coll:${collectionId}` : `ids:${sortedKey(moleculeIds ?? [])}`),
    [collectionId, moleculeIds],
  );

  // Either path must be enabled, but not both (the BE rejects {neither, both}).
  const queryEnabled = enabled && (collectionId !== undefined || (moleculeIds ?? []).length > 0);

  const start = useQuery({
    queryKey: ["scaffold-tree", "start", key],
    queryFn: () =>
      startFn(collectionId ? { collection_id: collectionId } : { molecule_ids: moleculeIds ?? [] }),
    enabled: queryEnabled,
    staleTime: STALE_TIME.MEDIUM,
  });

  const inlineTree = start.data?.tree ?? null;
  const startJob = start.data?.job ?? null;

  // Stable job reference for the poller (memoized on the React-Query-cached
  // start response) — an inline-mapped object would re-fire the poll.
  const job = useMemo(
    () => (startJob ? { id: startJob.id, status: startJob.status } : null),
    [startJob],
  );

  // Poll the job until terminal. The polled tree lives in the query cache, not
  // in component state. The GET returns the full ScaffoldTreeJob (status + tree).
  const { result: polledTree, error: pollError } = useJobPoll<ScaffoldTreeJob, ScaffoldTreeResult>({
    job,
    pollFn,
    getStatus: (j) => j.status,
    getResult: (j) => (j.status === "ready" ? (j.tree ?? null) : null),
    getError: (j) => {
      if (j.status === "failed") return j.error_message ?? "scaffold tree compute failed";
      if (j.status === "cancelled") return "scaffold tree compute cancelled";
      return null;
    },
    pollIntervalMs,
    queryKey: "scaffold-tree-poll",
  });

  const tree = inlineTree ?? polledTree;

  return {
    tree,
    jobId: job?.id ?? null,
    isStarting: start.isPending,
    isPolling: job != null && tree === null && pollError === null,
    error: (pollError ? new Error(pollError) : null) ?? (start.error as Error | null) ?? null,
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
