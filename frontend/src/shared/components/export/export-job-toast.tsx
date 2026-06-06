"use client";
import { formatFileSize } from "@/shared/lib/format-number";
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

export function ExportJobToast({ job, error, onCancel, onDownload, onDismiss }: Props) {
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
      const sizeLabel = job.byte_size != null ? formatFileSize(job.byte_size) : "—";
      toast.success(`Exported ${sizeLabel} — ${job.filename}`, {
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
        duration: Number.POSITIVE_INFINITY,
        action: { label: "Cancel", onClick: onCancel },
        cancel: undefined,
        closeButton: false,
      });
    } else if (job.status === "cancelled") {
      toast("Export cancelled", {
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
