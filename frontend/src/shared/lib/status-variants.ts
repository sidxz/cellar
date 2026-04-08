type StatusCategory = "active" | "success" | "warning" | "error" | "neutral" | "info";

const STATUS_CATEGORIES: Record<string, StatusCategory> = {
  // Active / in-progress
  active: "active",
  in_progress: "active",
  preparing: "active",
  screening: "active",
  in_transit: "active",
  assigned: "active",
  processing: "active",
  sourcing: "active",
  shipped: "active",

  // Success / completed
  approved: "success",
  completed: "success",
  delivered: "success",
  fulfilled: "success",
  available: "success",
  synthesis_complete: "success",

  // Warning / pending
  draft: "warning",
  pending: "warning",
  pending_review: "warning",
  submitted: "warning",
  quarantined: "warning",

  // Error / terminal-bad
  rejected: "error",
  failed: "error",
  cancelled: "error",
  returned: "error",

  // Neutral end-states (routine, NOT red)
  archived: "neutral",
  retired: "neutral",
  depleted: "neutral",
  disposed: "neutral",
  expired: "neutral",
  tombstone: "neutral",
  deprioritized: "neutral",

  // Info
  undisclosed: "info",
  disclosed: "info",
  registered: "info",
  hit: "info",
  lead: "info",
};

type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning";

const CATEGORY_TO_VARIANT: Record<StatusCategory, BadgeVariant> = {
  active: "default",
  success: "success",
  warning: "warning",
  error: "destructive",
  neutral: "outline",
  info: "secondary",
};

export function getStatusVariant(status: string): BadgeVariant {
  const category = STATUS_CATEGORIES[status.toLowerCase()];
  return category ? CATEGORY_TO_VARIANT[category] : "secondary";
}

/** Converts "in_progress" to "In Progress", "draft" to "Draft" */
export function formatStatusLabel(status: string): string {
  return status
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const PRIORITY_CATEGORIES: Record<string, StatusCategory> = {
  critical: "error",
  urgent: "warning",
  high: "warning",
  routine: "neutral",
  low: "neutral",
};

export function getPriorityVariant(priority: string): BadgeVariant {
  const category = PRIORITY_CATEGORIES[priority.toLowerCase()];
  return category ? CATEGORY_TO_VARIANT[category] : "outline";
}
