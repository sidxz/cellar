function toDate(input: string | Date | null | undefined): Date | null {
  if (input == null) return null;
  if (input instanceof Date) return input;
  // A bare YYYY-MM-DD is a calendar date, not an instant: anchor it at LOCAL
  // midnight so formatting never shifts the day. new Date("2026-07-01") is UTC
  // midnight, which a local-time formatter renders as Jun 30 west of UTC.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(input) ? new Date(`${input}T00:00:00`) : new Date(input);
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

/**
 * Day-granular relative date for *date-only* values (no time component), e.g.
 * a "last run on" calendar date. Unlike {@link formatRelativeDate} this has no
 * sub-day buckets and labels the current day "today" rather than "Xh ago":
 *   same day → "today"
 *   1 day    → "yesterday"
 *   < 14 d   → "Xd ago"
 *   < 60 d   → "Xw ago"
 *   else     → calendar date, omitting the year when it's the current year
 *
 * A bare `YYYY-MM-DD` string is interpreted at local midnight so the day
 * arithmetic doesn't drift across the UTC boundary.
 */
export function formatRelativeDay(input: string | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return "";

  const startOfDay = new Date(d);
  startOfDay.setHours(0, 0, 0, 0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const diffDays = Math.floor((today.getTime() - startOfDay.getTime()) / 86_400_000);
  if (diffDays <= 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 14) return `${diffDays}d ago`;
  if (diffDays < 60) return `${Math.floor(diffDays / 7)}w ago`;
  return startOfDay.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: today.getFullYear() === startOfDay.getFullYear() ? undefined : "numeric",
  });
}
