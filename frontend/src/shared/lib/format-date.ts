function toDate(input: string | Date | null | undefined): Date | null {
  if (input == null) return null;
  if (input instanceof Date) return input;
  const d = new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "May 12, 2026" */
export function formatDate(input: string | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(d);
}

/** "May 12, 2026, 3:42 PM" */
export function formatDateTime(input: string | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(d);
}

/**
 * Human-relative date:
 *   < 60 s   → "just now"
 *   < 60 m   → "Xm ago"
 *   < 24 h   → "Xh ago"
 *   < 48 h   → "yesterday"
 *   < 14 d   → "Xd ago"
 *   < 8 w    → "Xw ago"
 *   else     → formatDate()
 */
export function formatRelativeDate(input: string | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return "";

  const deltaMs = Date.now() - d.getTime();
  const secs = Math.floor(deltaMs / 1000);
  const mins = Math.floor(secs / 60);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  const weeks = Math.floor(days / 7);

  if (secs < 60) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (hours < 48) return "yesterday";
  if (days < 14) return `${days}d ago`;
  if (weeks < 8) return `${weeks}w ago`;
  return formatDate(d);
}
