"use client";
import { useJobPoll } from "@/shared/hooks/use-job-poll";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { downloadFile } from "@/shared/lib/api/download";
import {
  JOB_POLL_FAST_ATTEMPTS,
  JOB_POLL_FAST_INTERVAL_MS,
  JOB_POLL_INTERVAL_MS,
} from "@/shared/lib/timing";
import { useCallback, useEffect, useState } from "react";
import type { ExportJob, ExportRequest } from "./types";

/** Export-job statuses that stop the poll (adds `expired` to the SAR set). */
const TERMINAL_STATUSES: ReadonlySet<string> = new Set(["ready", "failed", "cancelled", "expired"]);

/**
 * Export poll cadence: a fast warm phase for the first
 * {@link JOB_POLL_FAST_ATTEMPTS} polls (small exports finish quickly), then
 * settle to the slower shared interval.
 */
function exportBackoffMs(attempt: number): number {
  return attempt < JOB_POLL_FAST_ATTEMPTS ? JOB_POLL_FAST_INTERVAL_MS : JOB_POLL_INTERVAL_MS;
}

interface UseExportReturn {
  start: (req: ExportRequest) => Promise<string>;
  cancel: () => Promise<void>;
  download: () => Promise<void>;
  reset: () => void;
  job: ExportJob | null;
  isPending: boolean;
  error: string | null;
}

export function useExport(): UseExportReturn {
  // Seed job ({id, status}) set by start(); drives useJobPoll's enabled flag.
  // Cleared on cancel/reset to stop polling.
  const [seed, setSeed] = useState<{ id: string; status: string } | null>(null);
  // Latest full job snapshot, mirrored from the poll so it survives the seed
  // being cleared (the toast keeps showing the last-known job after cancel).
  const [job, setJob] = useState<ExportJob | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  const { data, error: pollError } = useJobPoll<ExportJob, ExportJob>({
    job: seed,
    pollFn: (jobId) =>
      customInstance<ExportJob>({ url: `${API_V1}/exports/${jobId}`, method: "GET" }),
    getStatus: (j) => j.status,
    getResult: (j) => (j.status === "ready" ? j : null),
    // Any non-ready terminal status is surfaced as an error (matching the
    // prior `setError(error_message ?? status)` on failed/cancelled/expired).
    getError: (j) =>
      j.status !== "ready" && TERMINAL_STATUSES.has(j.status)
        ? (j.error_message ?? j.status)
        : null,
    pollIntervalMs: JOB_POLL_INTERVAL_MS,
    queryKey: "export-poll",
    terminalStatuses: TERMINAL_STATUSES,
    backoffMs: exportBackoffMs,
    onTerminal: (j) => {
      if (j.status === "ready") void triggerDownload(j);
    },
  });

  // Mirror the latest polled job into local state so it persists after the
  // seed is cleared (cancel/reset) and drives the toast/isPending.
  useEffect(() => {
    if (data) setJob(data);
  }, [data]);

  const start = useCallback(async (req: ExportRequest) => {
    setStartError(null);
    setJob(null);
    setSeed(null);
    const resp = await customInstance<{ job_id: string }>({
      url: `${API_V1}/exports`,
      method: "POST",
      data: req,
    });
    setSeed({ id: resp.job_id, status: "pending" });
    return resp.job_id;
  }, []);

  const cancel = useCallback(async () => {
    if (!job?.id) return;
    // Once the job has reached a terminal state the BE will 409 a cancel
    // request — short-circuit so the toast doesn't surface "API error: 409"
    // when the user clicks a stale Cancel button.
    if (TERMINAL_STATUSES.has(job.status)) {
      setSeed(null);
      return;
    }
    setSeed(null);
    await customInstance<void>({
      url: `${API_V1}/exports/${job.id}/cancel`,
      method: "POST",
    });
  }, [job]);

  const download = useCallback(async () => {
    if (!job) return;
    await triggerDownload(job);
  }, [job]);

  const reset = useCallback(() => {
    setSeed(null);
    setJob(null);
    setStartError(null);
  }, []);

  const error = startError ?? pollError;

  return {
    start,
    cancel,
    download,
    reset,
    job,
    isPending: !!job && !TERMINAL_STATUSES.has(job.status),
    error,
  };
}

async function triggerDownload(job: ExportJob) {
  if (!job.download_url || !job.filename) return;
  await downloadFile({ url: job.download_url, method: "GET", filename: job.filename });
}
