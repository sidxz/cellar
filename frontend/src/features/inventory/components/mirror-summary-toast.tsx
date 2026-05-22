import { toast } from "sonner"

export type MirrorSummary = {
  created: number
  skipped: Array<{
    batch_number: string
    mirror_string: string
    reason: "already_mapped" | "workspace_conflict" | "malformed_batch_number"
  }>
}

const reasonLabels = {
  already_mapped: "already exists as manual identifier",
  workspace_conflict: "already exists on another batch",
  malformed_batch_number: "batch number has no -NNN suffix",
} as const

export function renderToast(summary: MirrorSummary): void {
  const { created, skipped } = summary
  if (created === 0 && skipped.length === 0) return

  if (skipped.length === 0) {
    toast.success(
      `${created} batch mirror${created === 1 ? "" : "s"} created`,
      { duration: 4000 },
    )
    return
  }

  const itemLines = skipped
    .map((s) => `${s.mirror_string} → ${reasonLabels[s.reason]}`)
    .join("\n")
  const description = `${skipped.length} skipped\n${itemLines}`
  toast.message(
    `${created} created · ${skipped.length} skipped`,
    {
      description,
      duration: 8000,
    },
  )
}
