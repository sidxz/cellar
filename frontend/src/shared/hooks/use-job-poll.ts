import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { jobPollBackoffMs } from "@/shared/lib/timing";

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

/** Default job statuses that stop the poll (SAR vocabulary). */
const TERMINAL_STATUSES = new Set(["ready", "failed", "cancelled"]);

export function isTerminalJobStatus(
  status: string | null | undefined,
  terminalStatuses: ReadonlySet<string> = TERMINAL_STATUSES,
): boolean {
  return status != null && terminalStatuses.has(status);
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
  /**
   * Statuses that stop the poll. Defaults to the SAR set
   * (`ready`/`failed`/`cancelled`); callers with a different vocabulary
   * (e.g. exports add `expired`) supply their own.
   */
  terminalStatuses?: ReadonlySet<string>;
  /**
   * Override the poll cadence given the number of completed polls (0-based).
   * Defaults to the flat step backoff ({@link pollIntervalMs} for the first
   * {@link JOB_POLL_BACKOFF_AFTER} attempts, then double it). Callers with a
   * different ramp (e.g. exports: fast warm phase, then slow) supply their own.
   */
  backoffMs?: (attempt: number) => number;
  /**
   * Side effect fired once when a poll response first reaches a terminal
   * status (e.g. export's auto-download on `ready`). Runs after the cache
   * updates and before the poll stops.
   */
  onTerminal?: (poll: TPoll) => void;
}

export interface UseJobPollReturn<TPoll, TResult> {
  /** Latest success payload from the poll, or null while pending/failed. */
  result: TResult | null;
  /** Error message if the job failed/cancelled or the poll threw, else null. */
  error: string | null;
  /** True while a non-terminal job is being polled and no result/error yet. */
  isPolling: boolean;
  /** Latest raw poll response, or null before the first poll resolves. */
  data: TPoll | null;
}

export function useJobPoll<TPoll, TResult>({
  job,
  pollFn,
  getStatus,
  getResult,
  getError,
  pollIntervalMs,
  queryKey = "job-poll",
  terminalStatuses,
  backoffMs,
  onTerminal,
}: UseJobPollParams<TPoll, TResult>): UseJobPollReturn<TPoll, TResult> {
  // Only poll when there is a job that has not already reached a terminal state
  // in the start response.
  const enabled = job != null && !isTerminalJobStatus(job.status, terminalStatuses);

  const poll = useQuery({
    // job is non-null whenever enabled is true; the queryFn only runs then.
    queryKey: [queryKey, job?.id],
    queryFn: () => pollFn((job as { id: string }).id),
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      // Stop on a terminal status or any reported error (e.g. a defensive
      // "job not found"); otherwise the poll would spin forever.
      if (
        data &&
        (isTerminalJobStatus(getStatus(data), terminalStatuses) || getError(data) != null)
      ) {
        return false;
      }
      // dataUpdateCount counts successful fetches; the default reproduces the
      // prior `attempts < 3 ? base : base*2` step backoff. Callers may override
      // the ramp (e.g. exports: a fast warm phase, then slow).
      const attempt = query.state.dataUpdateCount;
      return backoffMs ? backoffMs(attempt) : jobPollBackoffMs(attempt, pollIntervalMs);
    },
    staleTime: 0,
    gcTime: 0,
  });

  const data = poll.data ?? null;
  const status = data ? getStatus(data) : job?.status;
  const result = data ? getResult(data) : null;

  // Fire the terminal side effect once, when a poll response first reaches a
  // terminal status (e.g. export's auto-download on `ready`). Keyed on the job
  // id + status so re-renders with the same terminal data don't re-fire it.
  const firedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!onTerminal || !data) return;
    const s = getStatus(data);
    if (!isTerminalJobStatus(s, terminalStatuses)) return;
    const key = `${job?.id ?? ""}:${s}`;
    if (firedFor.current === key) return;
    firedFor.current = key;
    onTerminal(data);
  });

  let error: string | null = null;
  if (poll.error) {
    error = String(poll.error);
  } else if (data) {
    error = getError(data);
  }

  const isPolling =
    enabled && !isTerminalJobStatus(status, terminalStatuses) && result === null && error === null;

  return { result, error, isPolling, data };
}
