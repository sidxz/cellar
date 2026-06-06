"use client";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { downloadFile } from "@/shared/lib/api/download";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ExportJob, ExportRequest } from "./types";

const TERMINAL_STATUSES = new Set(["ready", "failed", "cancelled", "expired"]);

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
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelled = useRef(false);

  const stop = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: poll recurses on itself (can't list itself as a dep); triggerDownload is a module-level fn and the setters are stable, so the dep array stays minimal.
  const poll = useCallback(
    async (jobId: string, attempt = 0) => {
      if (cancelled.current) return;
      try {
        const next = await customInstance<ExportJob>({
          url: `/api/v1/exports/${jobId}`,
          method: "GET",
        });
        setJob(next);
        if (next.status === "ready") {
          await triggerDownload(next);
          return;
        }
        if (TERMINAL_STATUSES.has(next.status)) {
          setError(next.error_message ?? next.status);
          return;
        }
        // Back-off: fast polls for the first few attempts, then slow down.
        const delay = attempt < 6 ? 500 : 2000;
        pollTimer.current = setTimeout(() => void poll(jobId, attempt + 1), delay);
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [stop],
  );

  const start = useCallback(
    async (req: ExportRequest) => {
      setError(null);
      setJob(null);
      cancelled.current = false;
      const resp = await customInstance<{ job_id: string }>({
        url: "/api/v1/exports",
        method: "POST",
        data: req,
      });
      void poll(resp.job_id);
      return resp.job_id;
    },
    [poll],
  );

  const cancel = useCallback(async () => {
    if (!job?.id) return;
    // Once the job has reached a terminal state the BE will 409 a cancel
    // request — short-circuit so the toast doesn't surface "API error: 409"
    // when the user clicks a stale Cancel button.
    if (TERMINAL_STATUSES.has(job.status)) {
      cancelled.current = true;
      stop();
      return;
    }
    cancelled.current = true;
    stop();
    await customInstance<void>({
      url: `/api/v1/exports/${job.id}/cancel`,
      method: "POST",
    });
  }, [job, stop]);

  const download = useCallback(async () => {
    if (!job) return;
    await triggerDownload(job);
  }, [job]);

  const reset = useCallback(() => {
    cancelled.current = true;
    stop();
    setJob(null);
    setError(null);
  }, [stop]);

  // Clean up any pending timer on unmount.
  useEffect(() => () => stop(), [stop]);

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
