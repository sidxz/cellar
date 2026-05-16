"use client";
import { useEffect } from "react";
import { toast } from "sonner";
import type { ExportJob } from "./types";

interface Props {
  job: ExportJob | null;
  error: string | null;
  onCancel: () => void;
  onDismiss: () => void;
}

export function ExportJobToast({ job, error, onCancel, onDismiss }: Props) {
  useEffect(() => {
    if (!job && !error) return;
    if (error) {
      toast.error(`Export failed: ${error}`, { id: "export-job", onDismiss });
      return;
    }
    if (!job) return;
    const pct = job.progress != null ? Math.round(job.progress * 100) : null;
    const label = pct != null ? ` (${pct}%)` : "";
    if (job.status === "ready") {
      toast.success(`Exported ${formatBytes(job.byte_size)} — ${job.filename}`, {
        id: "export-job",
        duration: 30_000,
        onDismiss,
      });
    } else if (["pending", "running"].includes(job.status)) {
      toast.loading(`Exporting${label}…`, {
        id: "export-job",
        duration: Infinity,
        action: { label: "Cancel", onClick: onCancel },
      });
    } else if (job.status === "cancelled") {
      toast(`Export cancelled`, { id: "export-job", onDismiss });
    }
  }, [job, error, onCancel, onDismiss]);
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
