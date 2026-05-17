"use client";
import { useEffect } from "react";
import { toast } from "sonner";
import type { ExportJob } from "./types";

interface Props {
  job: ExportJob | null;
  error: string | null;
  onCancel: () => void;
  onDownload: () => void;
  onDismiss: () => void;
}

export function ExportJobToast({
  job,
  error,
  onCancel,
  onDownload,
  onDismiss,
}: Props) {
  useEffect(() => {
    if (!job && !error) return;
    if (error) {
      toast.error(`Export failed: ${error}`, {
        id: "export-job",
        action: undefined,
        cancel: undefined,
        closeButton: true,
        onDismiss,
      });
      return;
    }
    if (!job) return;
    const pct = job.progress != null ? Math.round(job.progress * 100) : null;
    const label = pct != null ? ` (${pct}%)` : "";
    if (job.status === "ready") {
      // The auto-download has fired by the time we're here; the toast
      // gives the chemist a way to re-download if they missed it and a
      // close icon to dismiss. The Cancel button used to live on this
      // toast and would 409 the BE — we explicitly clear `cancel` so
      // sonner doesn't carry it across from the loading toast.
      toast.success(`Exported ${formatBytes(job.byte_size)} — ${job.filename}`, {
        id: "export-job",
        duration: 30_000,
        action: { label: "Download", onClick: onDownload },
        cancel: undefined,
        closeButton: true,
        onDismiss,
      });
    } else if (["pending", "running"].includes(job.status)) {
      toast.loading(`Exporting${label}…`, {
        id: "export-job",
        duration: Infinity,
        action: { label: "Cancel", onClick: onCancel },
        cancel: undefined,
        closeButton: false,
      });
    } else if (job.status === "cancelled") {
      toast(`Export cancelled`, {
        id: "export-job",
        action: undefined,
        cancel: undefined,
        closeButton: true,
        onDismiss,
      });
    }
  }, [job, error, onCancel, onDownload, onDismiss]);
  return null;
}

function formatBytes(n: number | null): string {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${u[i]}`;
}
