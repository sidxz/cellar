import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import { useJobPoll } from "@/shared/hooks/use-job-poll";
import type { DecompositionRunResponse } from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";

type StartInput = { collection_id?: string; molecule_ids?: string[]; core_smiles: string };

export type UseDecompositionRunParams = {
  collectionId?: string;
  moleculeIds?: string[];
  coreSmiles: string | null;
  startFn?: (input: StartInput) => Promise<DecompositionRunResponse>;
  pollFn?: (runId: string) => Promise<DecompositionRunResponse>;
  cancelFn?: (runId: string) => Promise<DecompositionRunResponse>;
  pollIntervalMs?: number;
  enabled?: boolean;
};

export type UseDecompositionRunReturn = {
  runId: string | null;
  labels: string[];
  counts: { matched: number; unmatched: number; total: number } | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  isCancelled: boolean;
  error: Error | null;
  cancel: () => void;
  runAgain: () => void;
};

const DEFAULT_POLL_MS = 1500;

function sortedKey(ids: string[]): string {
  return [...ids].sort().join(",");
}

export function useDecompositionRun(params: UseDecompositionRunParams): UseDecompositionRunReturn {
  const {
    collectionId,
    moleculeIds,
    coreSmiles,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    cancelFn = defaultCancelFn,
    pollIntervalMs = DEFAULT_POLL_MS,
    enabled = true,
  } = params;

  const [runNonce, setRunNonce] = useState(0);
  const [cancelledRunId, setCancelledRunId] = useState<string | null>(null);

  const sourceKey = collectionId ? `coll:${collectionId}` : `ids:${sortedKey(moleculeIds ?? [])}`;
  const key = `${sourceKey}|core:${coreSmiles ?? ""}|n:${runNonce}`;
  const queryEnabled =
    enabled && !!coreSmiles && (collectionId !== undefined || (moleculeIds ?? []).length > 0);

  const start = useQuery({
    queryKey: ["decomposition-run", "start", key],
    queryFn: () =>
      startFn(
        collectionId
          ? { collection_id: collectionId, core_smiles: coreSmiles as string }
          : { molecule_ids: moleculeIds ?? [], core_smiles: coreSmiles as string },
      ),
    enabled: queryEnabled,
    staleTime: STALE_TIME.MEDIUM,
  });

  const startRun = start.data ?? null;
  const job = useMemo(
    () => (startRun ? { id: startRun.run_id, status: startRun.status } : null),
    [startRun],
  );

  const {
    result: polled,
    error: pollError,
    data: polledData,
  } = useJobPoll<DecompositionRunResponse, DecompositionRunResponse>({
    job,
    pollFn,
    getStatus: (j) => j.status,
    getResult: (j) => (j.status === "ready" ? j : null),
    getError: (j) => (j.status === "failed" ? (j.error_message ?? "decomposition failed") : null),
    pollIntervalMs,
    queryKey: "decomposition-run-poll",
  });

  // The freshest known header: the polled ready run, else the inline-ready start,
  // else the (pending) start header.
  const ready = polled ?? (startRun?.status === "ready" ? startRun : null);
  const current = ready ?? startRun;

  const runId = startRun?.run_id ?? null;
  const serverCancelled = polledData?.status === "cancelled" || startRun?.status === "cancelled";
  const isCancelled = serverCancelled || (cancelledRunId != null && cancelledRunId === runId);

  const cancel = useCallback(() => {
    if (!runId) return;
    setCancelledRunId(runId);
    // Optimistic: the flag drives the UI now; the poll confirms the cancel, and
    // a failed cancel POST resolves itself on the next poll — nothing to surface.
    void cancelFn(runId).catch(() => {});
  }, [runId, cancelFn]);

  const runAgain = useCallback(() => {
    setCancelledRunId(null);
    setRunNonce((n) => n + 1);
  }, []);

  return {
    runId,
    labels: current?.rgroup_labels ?? [],
    counts: current
      ? {
          matched: current.matched_count,
          unmatched: current.unmatched_count,
          total: current.total_count,
        }
      : null,
    status: current?.status ?? null,
    isStarting: start.isPending && queryEnabled,
    isPolling: job != null && ready === null && pollError === null && !isCancelled,
    isCancelled,
    error: (pollError ? new Error(pollError) : null) ?? (start.error as Error | null) ?? null,
    cancel,
    runAgain,
  };
}

async function defaultStartFn(input: StartInput): Promise<DecompositionRunResponse> {
  const { startDecompositionApiV1SarDecompositionPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return startDecompositionApiV1SarDecompositionPost(input) as unknown as DecompositionRunResponse;
}

async function defaultPollFn(runId: string): Promise<DecompositionRunResponse> {
  const { getDecompositionRunApiV1SarDecompositionJobsRunIdGet } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return getDecompositionRunApiV1SarDecompositionJobsRunIdGet(
    runId,
  ) as unknown as DecompositionRunResponse;
}

async function defaultCancelFn(runId: string): Promise<DecompositionRunResponse> {
  const { cancelDecompositionRunApiV1SarDecompositionJobsRunIdCancelPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return cancelDecompositionRunApiV1SarDecompositionJobsRunIdCancelPost(
    runId,
  ) as unknown as DecompositionRunResponse;
}
