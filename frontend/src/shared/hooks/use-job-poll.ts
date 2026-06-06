import { useQuery } from "@tanstack/react-query";

/**
 * Shared async-job poller for the "start returns a job, then poll until
 * terminal" pattern (scaffold-tree, UMAP cluster, …).
 *
 * The poll runs as a TanStack Query keyed on the job id, so the polled result
 * lives in the query cache (not in component useState) and `refetchInterval`
 * drives the cadence — returning `false` once the job reaches a terminal state.
 * This avoids the manual `setTimeout` recursion that previously caused runaway
 * poll storms when the job object was re-derived on every render.
 *
 * The `job` passed in MUST be a stable, memoized reference (e.g. derived from
 * React-Query-cached data via `useMemo`) — an inline-mapped object every render
 * would invalidate the query key / enabled flag and re-fire the poll.
 *
 * Generic over the poll response shape (`TPoll`) and the extracted result
 * (`TResult`). Callers supply small extractor functions so the hook stays
 * agnostic to whether the poll returns the job itself or a `{ result, job }`
 * envelope.
 */

/** Job statuses that stop the poll. */
const TERMINAL_STATUSES = new Set(["ready", "failed", "cancelled"]);

export function isTerminalJobStatus(status: string | null | undefined): boolean {
  return status != null && TERMINAL_STATUSES.has(status);
}

export interface UseJobPollParams<TPoll, TResult> {
  /** Job id + current status, or null when there is no async job to poll. */
  job: { id: string; status: string } | null;
  /** Fetch the latest poll response for the given job id. */
  pollFn: (jobId: string) => Promise<TPoll>;
  /** Read the job status out of a poll response (drives terminal detection). */
  getStatus: (poll: TPoll) => string | null | undefined;
  /** Read the success payload out of a poll response (null until ready). */
  getResult: (poll: TPoll) => TResult | null;
  /** Read an error message out of a poll response (null unless failed/cancelled). */
  getError: (poll: TPoll) => string | null;
  /** Base poll interval; the hook doubles it after the 3rd attempt. */
  pollIntervalMs: number;
  /** Query-key segment that scopes the poll (defaults to "job-poll"). */
  queryKey?: string;
}

export interface UseJobPollReturn<TResult> {
  /** Latest success payload from the poll, or null while pending/failed. */
  result: TResult | null;
  /** Error message if the job failed/cancelled or the poll threw, else null. */
  error: string | null;
  /** True while a non-terminal job is being polled and no result/error yet. */
  isPolling: boolean;
}

export function useJobPoll<TPoll, TResult>({
  job,
  pollFn,
  getStatus,
  getResult,
  getError,
  pollIntervalMs,
  queryKey = "job-poll",
}: UseJobPollParams<TPoll, TResult>): UseJobPollReturn<TResult> {
  // Only poll when there is a job that has not already reached a terminal state
  // in the start response.
  const enabled = job != null && !isTerminalJobStatus(job.status);

  const poll = useQuery({
    // job is non-null whenever enabled is true; the queryFn only runs then.
    queryKey: [queryKey, job?.id],
    queryFn: () => pollFn((job as { id: string }).id),
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      // Stop on a terminal status or any reported error (e.g. a defensive
      // "job not found"); otherwise the poll would spin forever.
      if (data && (isTerminalJobStatus(getStatus(data)) || getError(data) != null)) {
        return false;
      }
      // dataUpdateCount counts successful fetches; reproduces the prior
      // `attempts < 3 ? base : base*2` backoff after the third poll.
      return query.state.dataUpdateCount < 3 ? pollIntervalMs : pollIntervalMs * 2;
    },
    staleTime: 0,
    gcTime: 0,
  });

  const data = poll.data;
  const status = data ? getStatus(data) : job?.status;
  const result = data ? getResult(data) : null;

  let error: string | null = null;
  if (poll.error) {
    error = String(poll.error);
  } else if (data) {
    error = getError(data);
  }

  const isPolling = enabled && !isTerminalJobStatus(status) && result === null && error === null;

  return { result, error, isPolling };
}
