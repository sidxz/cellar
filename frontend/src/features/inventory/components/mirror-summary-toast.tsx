import { showMessage } from "@/shared/lib/toast";

export type MirrorSummary = {
  created: number;
  skipped: Array<{
    batch_number: string;
    mirror_string: string;
    reason: string;
  }>;
};

const reasonLabels = {
  already_mapped: "already exists as manual identifier",
  workspace_conflict: "already exists on another batch",
  malformed_batch_number: "batch number has no -NNN suffix",
} as const;

export function renderToast(summary: MirrorSummary): void {
  const { created, skipped } = summary;
  if (skipped.length === 0) return;

  const itemLines = skipped
    .map(
      (s) =>
        `${s.mirror_string} → ${reasonLabels[s.reason as keyof typeof reasonLabels] ?? s.reason}`,
    )
    .join("\n");
  const description = `${skipped.length} skipped\n${itemLines}`;
  showMessage(`${created} created · ${skipped.length} skipped`, {
    description,
    duration: 8000,
  });
}
